# /// script
# requires-python = ">=3.12"
# dependencies = ["feedparser", "pyyaml"]
# ///
"""Prueba del lote RSS (capturar_rss.py) y su importación (importar_capturas.py). Ejecutar: uv run test_capturas.py

Fuentes caídas, lotes repetidos y fuera de orden, ventana de 7 días, lagunas frente a falta de noticias,
lotes inválidos y campos no admitidos (cuerpos)."""
import copy
import random
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from capturar_rss import construir, huella
from importar_capturas import abrir, importar, lagunas, validar

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
H = lambda h: T0 + timedelta(hours=h)
FUENTES = [{"id": "a", "nombre": "A", "zona": "espana"}, {"id": "b", "nombre": "B", "zona": "mundo", "muro": "ld"}]


class Feed:
    def __init__(self, *entradas):  # (enlace, titulo, hora)
        self.entries = [{"link": e, "title": t, "published_parsed": h.timetuple()} for e, t, h in entradas]


def lote(t, a=(), b=(), b_cae=False):
    leidos = [(FUENTES[0], Feed(*a), None) if a else (FUENTES[0], None, "sin entradas"),
              (FUENTES[1], None, "HTTP Error 503") if b_cae else (FUENTES[1], Feed(*b), None)]
    return construir(FUENTES, leidos, t, t + timedelta(seconds=20), {"run_id": str(int(t.timestamp())), "intento": "1"})


def db():
    return abrir(Path(tempfile.mkdtemp()) / "t.db")


def volcado(con):
    return (sorted(con.execute("SELECT * FROM articulos")),
            sorted(con.execute("SELECT lote, corte, estado, articulos FROM lotes")), sorted(con.execute("SELECT * FROM cobertura")))


# --- Lote: contrato, fuente caída, sin cuerpos ---
l1 = lote(H(0), a=[("https://a/1?utm_source=rss", "Uno", H(-1)), ("https://a/2", "Dos", H(-3))], b=[("https://b/1", "B uno", H(-2))])
assert l1["esquema"] == 1 and l1["lote"] and l1["corte"] == H(0).isoformat()
assert validar(l1) == [], validar(l1)
assert {a["enlace"] for a in l1["articulos"]} == {"https://a/1", "https://a/2", "https://b/1"}  # enlaces limpios (recoger)
assert set().union(*(a.keys() for a in l1["articulos"])) <= {"id", "titulo", "enlace", "fuente", "hora", "muro"}
assert l1["fuentes"]["a"]["desde"] == H(-3).isoformat() and l1["fuentes"]["b"]["desde"] == H(-2).isoformat()
assert next(a for a in l1["articulos"] if a["fuente"] == "b")["muro"] is None  # muro "ld": pendiente, no se adivina
caida = lote(H(0.25), a=[("https://a/1", "Uno", H(-1))], b_cae=True)
assert caida["fuentes"]["b"] == {"estado": "error", "error": "HTTP Error 503"} and validar(caida) == []

# --- Validación: todo o nada ---
def roto(cambio):
    l = copy.deepcopy(l1); cambio(l); return l
casos = {
    "huella": roto(lambda l: l["articulos"][0].update(titulo="otro")),
    "cuerpo": roto(lambda l: (l["articulos"][0].update(texto="párrafo completo…"), l.update(huella=huella(l["articulos"])))),
    "id": roto(lambda l: (l["articulos"][0].update(id="000000000000"), l.update(huella=huella(l["articulos"])))),
    "esquema": roto(lambda l: l.update(esquema=2)),
    "zona": roto(lambda l: l.update(corte="2026-11-10T12:00:00")),
    "futuro": roto(lambda l: (l["articulos"][0].update(hora=H(2).isoformat()), l.update(huella=huella(l["articulos"])))),
    "fuente caída con artículos": roto(lambda l: l["fuentes"]["b"].update(estado="error")),
}
for nombre, l in casos.items():
    assert validar(l), nombre
con = db()
r = importar(con, casos["cuerpo"], H(1))
assert r.startswith("rechazado") and "campos no admitidos" in r, r
assert con.execute("SELECT COUNT(*) FROM articulos").fetchone()[0] == 0  # nada entra de un lote inválido
assert con.execute("SELECT estado FROM lotes").fetchone()[0] == "rechazado"

# --- Repetidos y fuera de orden: mismo estado final ---
l2 = lote(H(1), a=[("https://a/1", "Uno corregido", H(-1)), ("https://a/3", "Tres", H(0.5))], b=[("https://b/1", "B uno", H(-2))])
l3 = lote(H(2), a=[("https://a/3", "Tres", H(0.5))], b=[("https://b/2", "B dos", H(1.5)), ("https://b/1", "B uno", H(-2))])
ahora = H(3)
estados = []
for orden in ([l1, l2, l3], [l3, l1, l2], [l2, l3, l1, l3, l2]):
    con = db()
    res = [importar(con, l, ahora) for l in orden]
    assert res.count("importado") == 3 and set(res) <= {"importado", "repetido"}, res
    estados.append(volcado(con))
assert estados[0] == estados[1] == estados[2]
arts = {r[0]: r for r in estados[0][0]}
assert len(arts) == 5  # a/1 a/2 a/3 b/1 b/2, sin duplicados
uno = next(r for r in arts.values() if r[2] == "https://a/1")
assert uno[1] == "Uno corregido" and uno[6] == H(0).isoformat() and uno[7] == H(1).isoformat()  # titular del último lote; visto 1º y último

# --- Lagunas frente a falta de noticias ---
con = db()
for l in (l1, l2, l3):
    importar(con, l, ahora)
lag, huecos = lagunas(con, ["a", "b"], H(2.25))
# a y b cubren desde antes de cada captura anterior; de 12:00 a 14:00 b no publicó nada nuevo en una hora: no es laguna
assert all(m == "antes de la primera captura" for f in lag for _, _, m in lag[f]), lag
# Lotes cada hora (> 45 min): son huecos sin lote, pero no lagunas, porque el RSS de cada fuente los cubre
assert huecos == [(H(2.25) - timedelta(days=7), H(0)), (H(0), H(1)), (H(1), H(2))], huecos

# RSS corto: a la 1:00 el RSS de b solo llega a las 0:30 (> corte anterior 0:00): laguna 0:00–0:30
con = db()
importar(con, lote(H(0), a=[("https://a/1", "Uno", H(-5))], b=[("https://b/1", "B", H(-5))]), H(1.1))
importar(con, lote(H(1), a=[("https://a/1", "Uno", H(-5))], b=[("https://b/9", "B nueve", H(0.5))]), H(1.1))
lag, _ = lagunas(con, ["a", "b"], H(1.1))
assert [(x, y) for x, y, m in lag["b"] if m.startswith("el RSS")] == [(H(0), H(0.5))], lag
assert all(m == "antes de la primera captura" for _, _, m in lag["a"]), lag["a"]

# Fuente caída: su captura no cuenta, aunque el lote exista
con = db()
importar(con, lote(H(0), a=[("https://a/1", "Uno", H(-5))], b=[("https://b/1", "B", H(-5))]), H(3))
importar(con, lote(H(1), a=[("https://a/1", "Uno", H(-5))], b_cae=True), H(3))
importar(con, lote(H(2), a=[("https://a/1", "Uno", H(-5))], b=[("https://b/2", "B dos", H(1.5))]), H(3))
lag, _ = lagunas(con, ["a", "b"], H(2.1))
assert (H(0), H(1.5), "el RSS no llega hasta la captura anterior") in lag["b"], lag

# Intervalo sin lotes (Actions sin ejecutar o artefactos caducados) y sin capturas recientes
con = db()
importar(con, lote(H(0), a=[("https://a/1", "Uno", H(-1))], b=[("https://b/1", "B", H(-1))]), H(5))
importar(con, lote(H(4), a=[("https://a/2", "Dos", H(3.5))], b=[("https://b/1", "B", H(-1))]), H(5))
lag, huecos = lagunas(con, ["a", "b"], H(5))
assert (H(0), H(4)) in huecos and (H(4), H(5)) in huecos, huecos
assert (H(0), H(3.5), "el RSS no llega hasta la captura anterior") in lag["a"], lag["a"]
assert not any(m.startswith("el RSS") for _, _, m in lag["b"])  # el RSS de b llega a la captura anterior: cubierto

# --- Ventana de 7 días por la hora de cada entrada ---
con = db()
viejo = lote(H(0), a=[("https://a/viejo", "Viejo", H(-24 * 8)), ("https://a/1", "Uno", H(-1))], b=[("https://b/1", "B", H(-1))])
assert importar(con, viejo, H(1)) == "importado"
assert {r[0] for r in con.execute("SELECT enlace FROM articulos")} == {"https://a/1", "https://b/1"}  # 8 días: fuera al importar
importar(con, lote(H(24 * 7 + 2), a=[("https://a/2", "Dos", H(24 * 7 + 1))], b=[("https://b/2", "B", H(24 * 7 + 1))]), H(24 * 7 + 2))
assert {r[0] for r in con.execute("SELECT enlace FROM articulos")} == {"https://a/2", "https://b/2"}  # lo de hace >7 días, purgado
assert con.execute("SELECT COUNT(*) FROM lotes").fetchone()[0] == 1 and con.execute("SELECT COUNT(*) FROM cobertura").fetchone()[0] == 2

# --- Barajado: 30 lotes en cualquier orden, con repeticiones, dan el mismo estado ---
random.seed(1)
serie = [lote(H(i * 0.25), a=[(f"https://a/{j}", f"t{j}-{i}", H(j * 0.25 - 1)) for j in range(i, i + 5)],
              b=[(f"https://b/{j}", "B", H(j * 0.25 - 1)) for j in range(i, i + 3)], b_cae=(i % 7 == 3)) for i in range(30)]
ref = db()
for l in serie:
    importar(ref, l, H(9))
for _ in range(3):
    con = db()
    for l in random.sample(serie, len(serie)) + random.sample(serie, 10):
        importar(con, l, H(9))
    assert volcado(con) == volcado(ref)
    assert lagunas(con, ["a", "b"], H(9)) == lagunas(ref, ["a", "b"], H(9))

print("OK")
