# /// script
# requires-python = ">=3.12"
# dependencies = ["feedparser", "pyyaml"]
# ///
"""Prueba de fusionar() y a_noticias(): repetidas, borrado a 7 días, orden, enlaces raros. Ejecutar: uv run test_recoger.py"""
import time
from datetime import datetime, timezone

from recoger import a_noticias, fusionar

ahora = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
n = lambda enlace, hora, titulo="t": {"enlace": enlace, "hora": hora, "titulo": titulo}

viejas = [n("a", "2026-10-09T10:00:00+00:00", "viejo"), n("b", "2026-10-01T10:00:00+00:00")]
nuevas = [n("a", "2026-10-09T10:00:00+00:00", "nuevo"), n("c", "2026-10-10T11:00:00+00:00")]
r = fusionar(viejas, nuevas, ahora)
assert [x["enlace"] for x in r] == ["c", "a"], r  # sin repetidas, b (>7 días) fuera, ordenado
assert r[1]["titulo"] == "viejo"  # se queda la primera vista

class Feed:
    entries = [
        {"link": "javascript:alert(1)", "title": "malo"},
        {"link": "https://x/1", "title": "  dos\n espacios ", "published_parsed": time.gmtime(2_000_000_000)},  # 2033
        {"link": "https://x/2", "title": ""},
    ]
r = a_noticias({"nombre": "M", "zona": "girona"}, Feed, ahora)
assert len(r) == 1 and r[0]["titulo"] == "dos espacios", r
assert r[0]["hora"] == ahora.isoformat(timespec="seconds")  # fecha futura recortada a ahora

class FeedTz:  # Girona Notícies: "14:00 -0300" es en realidad 14:00 de Madrid (12:00 UTC en octubre)
    entries = [{"link": "https://x/3", "title": "t", "published": "Sat, 10 Oct 2026 11:00:00 -0300",
                "published_parsed": time.gmtime(0)}]
r = a_noticias({"nombre": "M", "zona": "girona", "tz": "Europe/Madrid"}, FeedTz, ahora)
assert r[0]["hora"] == "2026-10-10T09:00:00+00:00", r
print("OK")
