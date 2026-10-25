# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
"""Archivo duradero en la rama huérfana `archivo` (nunca en main).

  capturas/AAAA-Www.jsonl          metadatos de cada artículo de esa semana ISO (hora de Madrid), uno por línea
  capturas/AAAA-Www.ejecuciones.json  horas con recogida correcta y estado de cada fuente por hora
  semana/                           informes semanales (los escribe semana.py)
  uso/ia.json                       consumo de IA de las últimas 48 h, compartido por todas las ejecuciones

Fusionar es una unión por id: repetirla o hacerla en otro orden da lo mismo, así que dos ejecuciones
a la vez no pierden datos; el push rechazado (no fast-forward) se resuelve volviendo a leer y fusionar.

  uv run archivo.py capturar [datos.json]   -> añade la recogida actual y la sube (con reintentos)
  uv run archivo.py preparar                -> solo descarga la rama en .archivo/
  uv run archivo.py restaurar [datos.json]  -> reconstruye datos.json (7 días) desde las capturas
Opciones: --dir DIR (por defecto .archivo), --local (sin git: solo el directorio).
"""
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

TZ = ZoneInfo("Europe/Madrid")
RAMA = "archivo"
CAMPOS = ("id", "fuente", "medio", "zona", "titulo", "enlace", "hora", "visto", "muro")


# --- Semanas ISO en hora de Madrid ---

def semana_de(momento):
    """Id ISO ("2026-W43") de la semana de Madrid que contiene `momento` (aware)."""
    a, s, _ = momento.astimezone(TZ).isocalendar()
    return f"{a}-W{s:02d}"


def limites(semana):
    """(inicio, fin_exclusivo) de la semana: lunes 00:00 a lunes 00:00 de Madrid, con su desfase real."""
    a, s = semana.split("-W")
    lunes = date.fromisocalendar(int(a), int(s), 1)
    inicio = datetime.combine(lunes, datetime.min.time(), TZ)
    fin = datetime.combine(lunes + timedelta(days=7), datetime.min.time(), TZ)
    return inicio, fin


def semana_anterior(semana):
    return semana_de(limites(semana)[0] - timedelta(hours=1))


def hora_utc(iso):
    return datetime.fromisoformat(iso).astimezone(timezone.utc)


# --- Lectura y escritura atómica ---

def escribir(ruta, texto):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(ruta)


def leer_jsonl(ruta):
    if not ruta.exists():
        return {}
    return {a["id"]: a for a in map(json.loads, ruta.read_text(encoding="utf-8").splitlines()) if a}


def escribir_jsonl(ruta, articulos):
    # ordenado por id y una línea por artículo: diffs pequeños en git
    escribir(ruta, "".join(json.dumps(articulos[k], ensure_ascii=False, sort_keys=True) + "\n" for k in sorted(articulos)))


def leer_json(ruta, defecto):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else defecto


# --- Capturas ---

def fusionar_articulo(viejo, nuevo):
    """Unión conmutativa: se queda el primer `visto`, el titular más reciente y el muro ya comprobado."""
    if not viejo:
        return nuevo
    r = dict(viejo)
    if nuevo.get("visto", "") >= viejo.get("visto", ""):
        r["titulo"] = nuevo["titulo"]
    else:
        r["titulo"] = viejo["titulo"]
    r["visto"] = min(viejo.get("visto") or nuevo["visto"], nuevo.get("visto") or viejo["visto"])
    if r.get("muro") is None:
        r["muro"] = nuevo.get("muro")
    return r


def capturar(datos, carpeta, retener_semanas=12):
    """Añade a capturas/ las noticias de datos.json y la ejecución actual. Devuelve las semanas tocadas."""
    carpeta = Path(carpeta)
    actualizado = hora_utc(datos["actualizado"])
    hora_ejec = actualizado.strftime("%Y-%m-%dT%H")
    por_semana = {}
    for n in datos["noticias"]:
        por_semana.setdefault(semana_de(hora_utc(n["hora"])), []).append({k: n.get(k) for k in CAMPOS})
    semana_actual = semana_de(actualizado)
    por_semana.setdefault(semana_actual, [])
    # no se reescriben semanas ya fuera de la retención
    minima = semana_de(actualizado - timedelta(weeks=retener_semanas))
    tocadas = []
    for semana, nuevas in sorted(por_semana.items()):
        if semana < minima:
            continue
        ruta = carpeta / "capturas" / f"{semana}.jsonl"
        articulos = leer_jsonl(ruta)
        antes = json.dumps(articulos, sort_keys=True)
        for a in nuevas:
            articulos[a["id"]] = fusionar_articulo(articulos.get(a["id"]), a)
        if json.dumps(articulos, sort_keys=True) != antes:
            escribir_jsonl(ruta, articulos)
            tocadas.append(semana)
    # Ejecuciones: en la semana de la recogida, la hora y el resultado de cada fuente
    ruta = carpeta / "capturas" / f"{semana_actual}.ejecuciones.json"
    ej = leer_json(ruta, {"horas": [], "fuentes": {}})
    ej["horas"] = sorted(set(ej["horas"]) | {hora_ejec})
    for fid, e in (datos.get("fuentes_estado") or {}).items():
        if e.get("comprobado") != datos["actualizado"]:
            continue
        f = ej["fuentes"].setdefault(fid, {"ok": [], "error": {}})
        if e.get("error") and e.get("error_hora") == datos["actualizado"]:
            f["error"][hora_ejec] = e["error"][:200]
        else:
            f["ok"] = sorted(set(f["ok"]) | {hora_ejec})
            if e.get("entrada_mas_antigua"):
                f["rss_desde"] = min(f.get("rss_desde") or e["entrada_mas_antigua"], e["entrada_mas_antigua"])
            if e.get("entrada_mas_reciente"):
                f["rss_hasta"] = max(f.get("rss_hasta") or "", e["entrada_mas_reciente"])
    escribir(ruta, json.dumps(ej, ensure_ascii=False, sort_keys=True, indent=0))
    purgar(carpeta, minima)
    return tocadas


def purgar(carpeta, minima):
    for p in (Path(carpeta) / "capturas").glob("*-W*.*"):
        if p.name.split(".")[0] < minima:
            p.unlink()


def articulos_semana(carpeta, semana):
    return list(leer_jsonl(Path(carpeta) / "capturas" / f"{semana}.jsonl").values())


def ejecuciones_semana(carpeta, semana):
    return leer_json(Path(carpeta) / "capturas" / f"{semana}.ejecuciones.json", {"horas": [], "fuentes": {}})


def restaurar(carpeta, ahora, dias=7):
    """Noticias de los últimos `dias` desde las capturas (para cuando falta el datos.json publicado)."""
    desde = ahora - timedelta(days=dias)
    semanas = {semana_de(desde + timedelta(days=d)) for d in range(dias + 1)}
    noticias = [a for s in semanas for a in articulos_semana(carpeta, s) if hora_utc(a["hora"]) >= desde]
    return sorted(noticias, key=lambda n: n["hora"], reverse=True)


# --- Git: rama huérfana en un worktree, con push optimista ---

def git(*args, cwd=".", check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def preparar(carpeta=".archivo", remoto="origin"):
    """Deja en `carpeta` un worktree de la rama archivo al día con el remoto (o una huérfana vacía si aún no existe)."""
    carpeta = Path(carpeta)
    existe = git("ls-remote", "--exit-code", "--heads", remoto, RAMA, check=False).returncode == 0
    if existe:
        git("fetch", "--depth=50", remoto, f"+refs/heads/{RAMA}:refs/remotes/{remoto}/{RAMA}")
    if not (carpeta / ".git").exists():
        git("worktree", "prune", check=False)
        git("worktree", "add", "--detach", "-f", str(carpeta), "HEAD")
        if existe:
            git("checkout", "-B", RAMA, f"{remoto}/{RAMA}", cwd=carpeta)
        else:
            git("checkout", "--orphan", RAMA, cwd=carpeta)
            git("rm", "-rfq", "--ignore-unmatch", ".", cwd=carpeta)
            for p in carpeta.iterdir():  # quedan archivos sin seguimiento del checkout de main
                if p.name != ".git":
                    subprocess.run(["rm", "-rf", str(p)], check=True)
    elif existe:
        git("checkout", "-B", RAMA, f"{remoto}/{RAMA}", cwd=carpeta)
        git("reset", "--hard", f"{remoto}/{RAMA}", cwd=carpeta)
        git("clean", "-fdq", cwd=carpeta)
    return existe


def sincronizar(cambio, mensaje, carpeta=".archivo", remoto="origin", intentos=5, antes_de_subir=None):
    """Aplica `cambio(carpeta)` sobre la última versión remota y la sube. Si otro proceso subió antes,
    se descarta lo local, se vuelve a leer y se aplica de nuevo (el cambio debe ser una fusión idempotente).
    Devuelve True si subió algo."""
    for intento in range(intentos):
        preparar(carpeta, remoto)
        cambio(carpeta)
        git("add", "-A", cwd=carpeta)
        if git("diff", "--cached", "--quiet", cwd=carpeta, check=False).returncode == 0:
            return False
        git("-c", "user.name=talaia-bot", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-qm", mensaje, cwd=carpeta)
        if antes_de_subir:
            antes_de_subir(intento)  # solo para las pruebas de concurrencia
        if git("push", remoto, f"HEAD:refs/heads/{RAMA}", cwd=carpeta, check=False).returncode == 0:
            return True
        print(f"archivo: push rechazado (intento {intento + 1}); se vuelve a leer y fusionar", file=sys.stderr)
    raise RuntimeError("archivo: no se pudo subir tras varios intentos")


def main(argv):
    orden = argv[0] if argv else "capturar"
    carpeta = argv[argv.index("--dir") + 1] if "--dir" in argv else ".archivo"
    local = "--local" in argv
    resto = [a for a in argv[1:] if not a.startswith("--") and a != carpeta]
    ruta_datos = Path(resto[0] if resto else "datos.json")
    config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    retener = config["semana"]["retener_semanas_capturas"]
    if orden == "preparar":
        preparar(carpeta)
    elif orden == "capturar":
        datos = json.loads(ruta_datos.read_text(encoding="utf-8"))
        cambio = lambda c: print(f"archivo: semanas actualizadas {capturar(datos, c, retener) or '—'}", file=sys.stderr)
        if local:
            cambio(carpeta)
        else:
            sincronizar(cambio, f"capturas {datos['actualizado']}", carpeta)
    elif orden == "restaurar":
        if not local:
            preparar(carpeta)
        ahora = datetime.now(timezone.utc).replace(microsecond=0)
        noticias = restaurar(carpeta, ahora)
        escribir(ruta_datos, json.dumps({"actualizado": ahora.isoformat(timespec="seconds"), "fuentes_caidas": [],
                                         "restaurado_de_archivo": True, "noticias": noticias}, ensure_ascii=False, separators=(",", ":")))
        print(f"archivo: {len(noticias)} noticias restauradas en {ruta_datos}", file=sys.stderr)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
