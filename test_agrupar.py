# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy"]
# ///
"""Prueba de agrupar() con vectores 2D inventados (el coseno entre dos es el coseno del ángulo). Ejecutar: uv run test_agrupar.py"""
import numpy as np

from agrupar import agrupar, palabras

def vec(*grados):
    r = np.radians(grados)
    return np.stack([np.cos(r), np.sin(r)], axis=1).astype(np.float32)

# Muy parecidos (cos 10° = 0,98): juntos sin mirar palabras
assert agrupar(vec(0, 10), ["a b", "c d"]) == [0, 0]

# Parecido medio (cos 39° = 0,78): juntos solo si comparten una palabra poco frecuente
assert agrupar(vec(0, 39), ["Aizpurua deja Bildu", "Bildu sin Aizpurua"]) == [0, 0]
assert agrupar(vec(0, 39), ["Algo pasa hoy", "Otra cosa distinta"]) == [0, 1]
# ...y si esa palabra es frecuente (sale en más de `raro` titulares) no cuenta
assert agrupar(vec(0, 39, 90, 180), ["Girona hoy", "Girona mañana", "Girona y más", "Girona otra"], raro=2)[:2] == [0, 1]

# Sin encadenar: B se une a A (cos 31° = 0,86), pero C, a 31° de B, queda lejos del centro de A+B
assert agrupar(vec(0, 31, 62), ["x", "y", "z"]) == [0, 0, 2]

assert palabras("Lleó XIV, operat") == {"lleo", "operat"}
print("OK")
