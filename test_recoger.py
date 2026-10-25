# /// script
# requires-python = ">=3.12"
# dependencies = ["feedparser", "pyyaml"]
# ///
"""Prueba de fusionar() y a_noticias(): repetidas, borrado a 7 días, orden, enlaces raros. Ejecutar: uv run test_recoger.py"""
import time
from datetime import datetime, timezone

from pathlib import Path

import yaml

from recoger import a_noticias, actualizar_estado, fusionar, limpiar_enlace, regla_excluir, tiene_muro

assert limpiar_enlace("https://b.co/a?at_medium=RSS&at_campaign=rss") == "https://b.co/a"
assert limpiar_enlace("https://e.com/x.html?utm_source=rss&id=7#top") == "https://e.com/x.html?id=7"

ahora = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
n = lambda enlace, hora, titulo="t": {"enlace": enlace, "hora": hora, "titulo": titulo}

viejas = [{**n("a", "2026-10-09T10:00:00+00:00", "viejo"), "muro": True}, n("b", "2026-10-01T10:00:00+00:00")]
nuevas = [{**n("a", "2026-10-10T09:00:00+00:00", "corregido"), "muro": None}, n("c", "2026-10-10T11:00:00+00:00")]
r = fusionar(viejas, nuevas, ahora)
assert [x["enlace"] for x in r] == ["c", "a"], r  # sin repetidas, b (>7 días) fuera, ordenado
assert r[1] == {"enlace": "a", "hora": "2026-10-09T10:00:00+00:00", "titulo": "corregido", "muro": True}  # titular nuevo, hora y muro de antes

class Feed:
    entries = [
        {"link": "javascript:alert(1)", "title": "malo"},
        {"link": "https://x/1", "title": "  dos\n espacios ", "published_parsed": time.gmtime(2_000_000_000)},  # 2033
        {"link": "https://x/2", "title": ""},
        {"link": "https://g.com/noticia/1-https://otra.com/x", "title": "roto"},
    ]
r = a_noticias({"nombre": "M", "zona": "girona"}, Feed, ahora)
assert len(r) == 1 and r[0]["titulo"] == "dos espacios", r
assert r[0]["hora"] == ahora.isoformat(timespec="seconds")  # fecha futura recortada a ahora...
assert r[0]["hora_rss_futura"].startswith("2033")              # ...y marcada, no escondida
assert r[0]["id"] == a_noticias({"nombre": "M", "zona": "mundo"}, Feed, ahora)[0]["id"]  # id estable por enlace

# Muro por artículo
class FeedRss:
    entries = [{"link": "https://m/1", "title": "a", "tags": [{"term": "NLPremium"}]}, {"link": "https://m/2", "title": "b", "tags": []}]
r = a_noticias({"nombre": "M", "zona": "espana", "muro": "rss:NLPremium"}, FeedRss, ahora)
assert [x["muro"] for x in r] == [True, False], r
assert a_noticias({"nombre": "M", "zona": "espana", "muro": "ld"}, FeedRss, ahora)[0]["muro"] is None  # pendiente de mirar
assert a_noticias({"nombre": "M", "zona": "espana"}, FeedRss, ahora)[0]["muro"] is False

cerrado = '{"isAccessibleForFree":false,"hasPart":{"@type":"WebPageElement","isAccessibleForFree":false,"cssSelector":".x"}}'
cerrado_al_reves = '"hasPart": [{"cssSelector": ".x", "isAccessibleForFree": "False"}]'
abierto = '{"isAccessibleForFree":true,"hasPart":{"@type":"WebPageElement","isAccessibleForFree":true}}'
medido = '{"isAccessibleForFree":false}'  # sin sección oculta: muro medido o marca genérica, no cuenta
assert tiene_muro(cerrado, "ld") and tiene_muro(cerrado_al_reves, "ld")
assert not tiene_muro(abierto, "ld") and not tiene_muro(medido, "ld")
assert tiene_muro(medido + "Exclusiva para socios", "texto:exclusiva para socios")
assert not tiene_muro(medido, "texto:exclusiva para socios")
assert not tiene_muro(abierto + "exclusiva para socios", "texto:exclusiva para socios")

# Reglas de exclusión reales de fuentes.yaml: positivos y negativos
F = {f["id"]: f for f in yaml.safe_load(Path("fuentes.yaml").read_text(encoding="utf-8"))["fuentes"]}
fuera = [("euronews", "Últimas noticias | 25 octubre 2026 - Mañana"), ("euronews", "Últimas noticias | 3 marzo 2027"),
         ("ara", "A la contra"), ("ara", "De fit a fit"), ("el-pais", "‘El Pulso’ de ‘Hoy por Hoy’, en directo, en EL PAÍS"),
         ("el-pais", "‘La Mesa de Hora 25’ | Programa del 22 de octubre de 2026"), ("tehran-times", "15455")]
dentro = [("euronews", "EURONEWS HOY | Las noticias del 23 de octubre de 2026: Francia se prepara para otro fin de semana de protestas"),
          ("euronews", "Últimas noticias sobre la DANA: tres muertos en Valencia"),
          ("el-pais", "Última hora de la actualidad política, en directo | Feijóo advierte al PSOE"),
          ("ara", "A la contra de tothom, el Govern aprova el pressupost"), ("tehran-times", "15 killed in Gaza strike"),
          ("la-vanguardia", "Última hora de los disturbios en Barcelona, en directo | 100 detenidos")]
for fid, t in fuera:
    assert regla_excluir(F[fid], t), (fid, t)
for fid, t in dentro:
    assert not regla_excluir(F[fid], t), (fid, t)
class FeedEx:
    entries = [{"link": "https://e/1", "title": "Últimas noticias | 25 octubre 2026 - Mañana"}, {"link": "https://e/2", "title": "Otra"}]
ex = []
assert [x["titulo"] for x in a_noticias(F["euronews"], FeedEx, ahora, ex)] == ["Otra"]
assert ex[0]["fuente"] == "euronews" and ex[0]["regla"]  # la exclusión queda registrada para revisarla

# Estado de fuente: el error no borra el último éxito
e = actualizar_estado(None, {}, FeedRss, None, ahora)
e = actualizar_estado(e, {}, None, "HTTP 403", ahora)
assert e["exito"] == ahora.isoformat(timespec="seconds") and e["error"] == "HTTP 403" and e["entradas"] == 2
assert "error" not in actualizar_estado(e, {}, FeedRss, None, ahora)
print("OK")
