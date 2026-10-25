# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
"""Pruebas de archivo.py: semanas ISO de Madrid, capturas incrementales y push concurrente. Ejecutar: uv run test_archivo.py"""
import json
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from archivo import articulos_semana, capturar, ejecuciones_semana, limites, restaurar, semana_anterior, semana_de, sincronizar

M = ZoneInfo("Europe/Madrid")
U = timezone.utc

# Semana ISO con la hora de Madrid, no la de UTC ni el año natural
assert semana_de(datetime(2026, 10, 25, 21, 30, tzinfo=U)) == "2026-W43"   # domingo 22:30 (CET) en Madrid
assert semana_de(datetime(2026, 10, 25, 23, 30, tzinfo=U)) == "2026-W44"   # lunes 00:30 en Madrid
assert semana_de(datetime(2027, 1, 1, 12, tzinfo=M)) == "2026-W53"         # 2026 tiene 53 semanas ISO
assert semana_de(datetime(2027, 1, 4, 0, 0, tzinfo=M)) == "2027-W01"
assert semana_de(datetime(2024, 12, 30, 9, tzinfo=M)) == "2025-W01"        # el lunes 30/12/2024 ya es 2025
assert semana_anterior("2027-W01") == "2026-W53" and semana_anterior("2025-W01") == "2024-W52"
# Cambio de hora: la semana del 25/10/2026 dura 169 h y la del 29/03/2026, 167 h
i, f = limites("2026-W43")
assert i.isoformat() == "2026-10-19T00:00:00+02:00" and f.isoformat() == "2026-10-26T00:00:00+01:00"
assert f.astimezone(U) - i.astimezone(U) == timedelta(hours=169)  # en UTC: restar con la misma tzinfo usa la hora de pared
i, f = limites("2026-W13")
assert f.astimezone(U) - i.astimezone(U) == timedelta(hours=167)

n = lambda i, hora, titulo="t", muro=False: {"id": i, "fuente": "f", "medio": "F", "zona": "mundo", "titulo": titulo,
                                              "enlace": f"https://x/{i}", "hora": hora, "visto": hora, "muro": muro}
with tempfile.TemporaryDirectory() as d:
    # Lunes 19/10 00:10 Madrid: la ventana móvil de 7 días ya no lo tendrá el lunes 26 a las 00:30
    lunes = datetime(2026, 10, 19, 0, 10, tzinfo=M).astimezone(U).isoformat()
    d1 = {"actualizado": "2026-10-19T06:00:00+00:00", "noticias": [n("a", lunes)],
          "fuentes_estado": {"f": {"comprobado": "2026-10-19T06:00:00+00:00", "exito": "2026-10-19T06:00:00+00:00"}}}
    assert capturar(d1, d) == ["2026-W43"]
    d2 = {"actualizado": "2026-10-25T23:30:00+00:00", "noticias": [n("b", "2026-10-25T20:00:00+00:00", muro=None)],
          "fuentes_estado": {"f": {"comprobado": "2026-10-25T23:30:00+00:00", "error": "HTTP 500", "error_hora": "2026-10-25T23:30:00+00:00"}}}
    capturar(d2, d)
    assert {a["id"] for a in articulos_semana(d, "2026-W43")} == {"a", "b"}  # el lunes sigue ahí
    assert capturar(d1, d) == []                                            # repetir no cambia nada
    ej = ejecuciones_semana(d, "2026-W43")
    assert ej["horas"] == ["2026-10-19T06"] and ej["fuentes"]["f"]["ok"] == ["2026-10-19T06"]
    assert ejecuciones_semana(d, "2026-W44")["fuentes"]["f"]["error"] == {"2026-10-25T23": "HTTP 500"}
    # Titular corregido y muro comprobado más tarde: se fusionan sin perder el primer "visto"
    d3 = {"actualizado": "2026-10-25T23:45:00+00:00", "noticias": [{**n("b", "2026-10-25T20:00:00+00:00", "corregido", True), "visto": "2026-10-25T23:45:00+00:00"}]}
    capturar(d3, d)
    b = next(a for a in articulos_semana(d, "2026-W43") if a["id"] == "b")
    assert b["titulo"] == "corregido" and b["muro"] is True and b["visto"] == "2026-10-25T20:00:00+00:00"
    assert [x["id"] for x in restaurar(d, datetime(2026, 10, 25, 20, tzinfo=U))] == ["b", "a"]
    # Retención: una semana muy antigua no se escribe y las viejas se purgan
    viejo = {"actualizado": "2026-10-25T23:45:00+00:00", "noticias": [n("z", "2026-01-05T10:00:00+00:00")]}
    capturar(viejo, d, retener_semanas=12)
    assert not (Path(d) / "capturas" / "2026-W02.jsonl").exists()


# Concurrencia real con git: dos ejecuciones leen la misma versión; la segunda ve su push rechazado,
# vuelve a leer, fusiona y sube. No se pierde ninguna de las dos capturas, y los informes se conservan.
def sh(*a, cwd):
    subprocess.run(a, cwd=cwd, check=True, capture_output=True)

with tempfile.TemporaryDirectory() as t:
    t = Path(t)
    sh("git", "init", "-q", "--bare", "remoto.git", cwd=t)
    for c in ("a", "b"):
        sh("git", "clone", "-q", str(t / "remoto.git"), c, cwd=t)
        sh("git", "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-q", "--allow-empty", "-m", "main", cwd=t / c)
    sh("git", "push", "-q", "origin", "HEAD:refs/heads/main", cwd=t / "a")

    datos = lambda i, h: {"actualizado": h, "noticias": [n(i, h)]}
    import os
    cwd = os.getcwd()
    try:
        os.chdir(t / "b")
        # B prepara su cambio; justo antes de subir, A sube el suyo (y un informe semanal)
        def a_sube_antes(intento):
            if intento == 0:
                os.chdir(t / "a")
                def cambio_a(c):
                    capturar(datos("de-a", "2026-10-21T10:00:00+00:00"), c)
                    (Path(c) / "semana").mkdir(exist_ok=True)
                    (Path(c) / "semana" / "2026-W42.json").write_text("{}")
                assert sincronizar(cambio_a, "a", carpeta=str(t / "a" / ".archivo"))
                os.chdir(t / "b")
        subio = sincronizar(lambda c: capturar(datos("de-b", "2026-10-21T10:05:00+00:00"), c), "b",
                            carpeta=str(t / "b" / ".archivo"), antes_de_subir=a_sube_antes)
        assert subio
        sh("git", "clone", "-q", "-b", "archivo", str(t / "remoto.git"), "comprobar", cwd=t)
        ids = {a["id"] for a in articulos_semana(t / "comprobar", "2026-W43")}
        assert ids == {"de-a", "de-b"}, ids
        assert (t / "comprobar" / "semana" / "2026-W42.json").exists()   # la captura diaria conserva el informe
        # Una actualización antigua no pisa una más reciente: repetir la de A no cambia nada ni sube
        os.chdir(t / "a")
        assert not sincronizar(lambda c: capturar(datos("de-a", "2026-10-21T10:00:00+00:00"), c), "a", carpeta=str(t / "a" / ".archivo"))
    finally:
        os.chdir(cwd)
print("OK")
