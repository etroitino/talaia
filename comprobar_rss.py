# /// script
# requires-python = ">=3.12"
# dependencies = ["feedparser", "pyyaml"]
# ///
"""Comprueba cada RSS de fuentes.yaml: si responde, si se puede leer y cuántas entradas trae."""
import calendar
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import yaml

from recoger import descargar


DIAS_ANTIGUO = 7


def comprobar(fuente):
    try:
        f = descargar(fuente)
    except Exception as e:
        return fuente, f"ERROR {e}", 0
    fechas = [calendar.timegm(t) for e in f.entries if (t := e.get("published_parsed") or e.get("updated_parsed"))]
    if fechas and time.time() - max(fechas) > DIAS_ANTIGUO * 86400:  # responde, pero no se actualiza
        return fuente, f"ANTIGUO: última entrada {time.strftime('%Y-%m-%d', time.gmtime(max(fechas)))}", len(f.entries)
    return fuente, "OK", len(f.entries)


def main(ruta="fuentes.yaml"):
    fuentes = yaml.safe_load(open(ruta, encoding="utf-8"))["fuentes"]
    with ThreadPoolExecutor(8) as ex:
        resultados = list(ex.map(comprobar, fuentes))
    fallos = 0
    for f, estado, n in resultados:
        fallos += estado != "OK"
        print(f"{'✔' if estado == 'OK' else '✘'} {f['zona']:<13} {f['nombre']:<24} {n:>4}  {estado if estado != 'OK' else ''}")
    print(f"\n{len(fuentes) - fallos}/{len(fuentes)} OK")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
