# /// script
# requires-python = ">=3.12"
# dependencies = ["feedparser", "pyyaml"]
# ///
"""V1 · importación de lotes RSS en el Mac (SQLite local, un solo escritor).

  uv run importar_capturas.py descargar [--rama main] [--db RUTA]   -> baja de Actions los lotes vigentes aún no importados
  uv run importar_capturas.py importar LOTE.json.gz... [--db RUTA]
  uv run importar_capturas.py estado [--db RUTA]                    -> artículos, lotes y lagunas de la ventana

Reglas:
- Un lote se valida entero (esquema, huella, campos y tipos); si no es válido, se registra como rechazado y no entra nada.
- Deduplicación por id de artículo: repetir un lote o importarlo fuera de orden deja el mismo estado.
- Ventana lógica de 7 días por la hora de cada entrada (no por la fecha del artefacto); lo anterior se purga.
- Laguna = intervalo en el que una fuente pudo publicar sin que ningún lote lo cubra: entre dos capturas correctas,
  si el RSS de la segunda no llega hasta la primera. Un intervalo cubierto sin artículos no es laguna; una fuente
  caída sí puede producirla. El RSS sin fechas no cubre nada anterior a su propia captura.
La descarga usa `gh` (credencial del usuario, nunca guardada aquí).
"""
import gzip
import io
import json
import sqlite3
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from capturar_rss import CAMPOS, ESQUEMA, huella
from recoger import id_articulo

VENTANA = timedelta(days=7)
TOLERANCIA = timedelta(minutes=5)      # desfase de relojes entre RSS y corte
SIN_CAPTURA = timedelta(minutes=45)    # sin lotes más tiempo que esto: hueco (3 ciclos de 15 min)
MAX_TITULO = 500
DB = Path.home() / ".talaia" / "talaia.db"
REPO = "etroitino/talaia"

ESQUEMA_SQL = """
CREATE TABLE IF NOT EXISTS lotes (lote TEXT PRIMARY KEY, corte TEXT NOT NULL, estado TEXT NOT NULL, motivo TEXT,
    articulos INTEGER, origen TEXT, importado TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cobertura (lote TEXT NOT NULL, fuente TEXT NOT NULL, estado TEXT NOT NULL, desde TEXT, error TEXT,
    PRIMARY KEY (lote, fuente));
CREATE TABLE IF NOT EXISTS articulos (id TEXT PRIMARY KEY, titulo TEXT NOT NULL, enlace TEXT NOT NULL, fuente TEXT NOT NULL,
    hora TEXT NOT NULL, muro INTEGER, visto_primero TEXT NOT NULL, visto_ultimo TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS artefactos (id INTEGER PRIMARY KEY, lote TEXT, descargado TEXT NOT NULL);
"""


def utc(iso):
    d = datetime.fromisoformat(iso)
    if d.tzinfo is None:
        raise ValueError(f"fecha sin zona: {iso}")
    return d.astimezone(timezone.utc)


def iso(d):
    return d.astimezone(timezone.utc).isoformat(timespec="seconds")


def abrir(ruta=DB):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta)
    con.executescript(ESQUEMA_SQL)
    return con


def validar(l):
    """Lista de errores; vacía si el lote cumple el contrato."""
    if not isinstance(l, dict):
        return ["no es un objeto"]
    if l.get("esquema") != ESQUEMA:
        return [f"esquema {l.get('esquema')!r} no admitido"]
    err = []
    try:
        corte = utc(l["corte"])
    except Exception:
        return ["corte ausente o sin zona"]
    if not isinstance(l.get("lote"), str) or not l["lote"]:
        err.append("lote sin id")
    fuentes, arts = l.get("fuentes"), l.get("articulos")
    if not isinstance(fuentes, dict) or not isinstance(arts, list):
        return err + ["fuentes o articulos con tipo incorrecto"]
    for fid, e in fuentes.items():
        if e.get("estado") not in ("ok", "error"):
            err.append(f"fuente {fid}: estado {e.get('estado')!r}")
        elif e["estado"] == "ok" and e.get("desde"):
            try:
                utc(e["desde"])
            except Exception:
                err.append(f"fuente {fid}: desde inválido")
    if huella(arts) != l.get("huella"):
        err.append("huella no coincide")
    for a in arts:
        extra = set(a) - set(CAMPOS)
        if extra:  # p. ej. entradilla o cuerpo: el contrato no los admite
            err.append(f"artículo {a.get('id')}: campos no admitidos {sorted(extra)}")
            continue
        try:
            ok = (a["id"] == id_articulo(a["enlace"]) and a["enlace"].startswith(("http://", "https://"))
                  and isinstance(a["titulo"], str) and 0 < len(a["titulo"]) <= MAX_TITULO
                  and fuentes.get(a["fuente"], {}).get("estado") == "ok"
                  and a.get("muro") in (True, False, None) and utc(a["hora"]) <= corte + TOLERANCIA)
        except Exception:
            ok = False
        if not ok:
            err.append(f"artículo {a.get('id')}: campos o tipos inválidos")
    return err[:20]


def importar(con, l, ahora):
    """Devuelve 'importado', 'repetido' o 'rechazado: motivo'. Todo o nada, en una transacción."""
    lid = l.get("lote") if isinstance(l, dict) else None
    if lid and con.execute("SELECT 1 FROM lotes WHERE lote = ?", (lid,)).fetchone():
        return "repetido"
    errores = validar(l)
    with con:
        if errores:
            # corte = hora de importación: el registro del rechazo dura lo mismo que la ventana
            con.execute("INSERT OR REPLACE INTO lotes VALUES (?, ?, 'rechazado', ?, NULL, NULL, ?)",
                        (lid or f"sin-id-{iso(ahora)}", iso(ahora), "; ".join(errores), iso(ahora)))
            return "rechazado: " + "; ".join(errores)
        corte = iso(utc(l["corte"]))
        con.execute("INSERT INTO lotes VALUES (?, ?, 'ok', NULL, ?, ?, ?)",
                    (lid, corte, len(l["articulos"]), json.dumps(l.get("origen"), ensure_ascii=False), iso(ahora)))
        con.executemany("INSERT INTO cobertura VALUES (?, ?, ?, ?, ?)",
                        [(lid, f, e["estado"], iso(utc(e["desde"])) if e.get("desde") else None, e.get("error")) for f, e in l["fuentes"].items()])
        # El titular se corrige con el lote más reciente; la hora es la más antigua vista (como recoger.fusionar)
        con.executemany("""
            INSERT INTO articulos VALUES (:id, :titulo, :enlace, :fuente, :hora, :muro, :corte, :corte)
            ON CONFLICT(id) DO UPDATE SET
                titulo = CASE WHEN excluded.visto_ultimo > articulos.visto_ultimo THEN excluded.titulo ELSE articulos.titulo END,
                muro = CASE WHEN excluded.visto_ultimo > articulos.visto_ultimo THEN COALESCE(excluded.muro, articulos.muro)
                            ELSE COALESCE(articulos.muro, excluded.muro) END,
                hora = MIN(articulos.hora, excluded.hora),
                visto_primero = MIN(articulos.visto_primero, excluded.visto_primero),
                visto_ultimo = MAX(articulos.visto_ultimo, excluded.visto_ultimo)""",
            [{**a, "hora": iso(utc(a["hora"])), "muro": a.get("muro"), "corte": corte} for a in l["articulos"]])
        purgar(con, ahora)  # aplica la ventana de 7 días también a lo recién importado
    return "importado"


def purgar(con, ahora):
    limite = iso(ahora - VENTANA)
    con.execute("DELETE FROM articulos WHERE hora < ?", (limite,))
    viejos = [r[0] for r in con.execute("SELECT lote FROM lotes WHERE corte < ?", (limite,))]
    con.executemany("DELETE FROM cobertura WHERE lote = ?", [(x,) for x in viejos])
    con.executemany("DELETE FROM lotes WHERE lote = ?", [(x,) for x in viejos])


def unir(tramos):
    out = []
    for a, b, m in sorted(tramos):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b), out[-1][2])
        else:
            out.append((a, b, m))
    return out


def lagunas(con, fuentes, ahora):
    """{fuente: [(desde, hasta, motivo)]} dentro de la ventana, y los huecos sin ningún lote."""
    limite = ahora - VENTANA
    cortes = [utc(c) for (c,) in con.execute("SELECT corte FROM lotes WHERE estado = 'ok' ORDER BY corte")]
    huecos = [(a, b) for a, b in zip([limite] + cortes, cortes + [ahora]) if b - a > SIN_CAPTURA]
    res = {}
    for f in fuentes:
        caps = [(utc(c), utc(d) if d else utc(c)) for c, d in con.execute(
            "SELECT l.corte, c.desde FROM cobertura c JOIN lotes l USING (lote) WHERE c.fuente = ? AND c.estado = 'ok' ORDER BY l.corte", (f,))]
        t = []
        if not caps:
            t.append((limite, ahora, "sin ninguna captura correcta"))
        else:
            if caps[0][1] > limite + TOLERANCIA:
                t.append((limite, caps[0][1], "antes de la primera captura"))
            for (c1, _), (c2, d2) in zip(caps, caps[1:]):
                if d2 > c1 + TOLERANCIA:
                    t.append((c1, d2, "el RSS no llega hasta la captura anterior"))
            if ahora - caps[-1][0] > SIN_CAPTURA:
                t.append((caps[-1][0], ahora, "sin capturas recientes"))
        if t:
            res[f] = unir(t)
    return res, huecos


def descargar(con, rama, ahora, repo=REPO):
    """Lotes de Actions aún vigentes (los caducados ya no existen: quedarán como lagunas)."""
    gh = lambda *a: subprocess.run(["gh", "api", *a], check=True, capture_output=True).stdout
    lineas = gh("--paginate", f"repos/{repo}/actions/artifacts?name=captura-rss&per_page=100",
                "--jq", f'.artifacts[] | select(.expired | not) | select(.workflow_run.head_branch == "{rama}") | .id').decode().split()
    hechos = {r[0] for r in con.execute("SELECT id FROM artefactos")}
    resultado = {}
    for aid in sorted(set(map(int, lineas)) - hechos):
        z = zipfile.ZipFile(io.BytesIO(gh(f"repos/{repo}/actions/artifacts/{aid}/zip")))
        l = json.loads(gzip.decompress(z.read("lote.json.gz")))
        r = resultado[aid] = importar(con, l, ahora)
        with con:
            con.execute("INSERT INTO artefactos VALUES (?, ?, ?)", (aid, l.get("lote"), iso(ahora)))
        print(f"artefacto {aid} ({l.get('lote')}): {r}", file=sys.stderr)
    return resultado


def estado(con, fuentes, ahora):
    n = con.execute("SELECT COUNT(*) FROM articulos").fetchone()[0]
    lotes = con.execute("SELECT COUNT(*), MIN(corte), MAX(corte) FROM lotes WHERE estado = 'ok'").fetchone()
    rech = con.execute("SELECT lote, motivo FROM lotes WHERE estado = 'rechazado'").fetchall()
    lag, huecos = lagunas(con, fuentes, ahora)
    print(f"{n} artículos en la ventana; {lotes[0]} lotes ({lotes[1]} → {lotes[2]}); {len(rech)} rechazados")
    for a, b in huecos:
        print(f"  sin lotes: {iso(a)} → {iso(b)}")
    for f, ts in sorted(lag.items()):
        for a, b, m in ts:
            print(f"  laguna {f}: {iso(a)} → {iso(b)} ({m})")
    return lag, huecos


def main(argv):
    op = lambda k, d: argv[argv.index(k) + 1] if k in argv else d
    con = abrir(op("--db", DB))
    ahora = datetime.now(timezone.utc).replace(microsecond=0)
    fuentes = [f["id"] for f in yaml.safe_load(Path("fuentes.yaml").read_text(encoding="utf-8"))["fuentes"]]
    orden = argv[0] if argv else "estado"
    if orden == "descargar":
        descargar(con, op("--rama", "main"), ahora)
    elif orden == "importar":
        for p in [a for a in argv[1:] if a.endswith(".gz")]:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                print(f"{p}: {importar(con, json.load(f), ahora)}", file=sys.stderr)
    elif orden != "estado":
        sys.exit(__doc__)
    estado(con, fuentes, ahora)


if __name__ == "__main__":
    main(sys.argv[1:])
