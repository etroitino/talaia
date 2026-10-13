# /// script
# requires-python = ">=3.12"
# dependencies = ["fastembed", "numpy"]
# ///
"""F2: agrupa en datos.json las noticias que cuentan el mismo hecho (campo "grupo").

  uv run agrupar.py            -> agrupa y guarda
  uv run agrupar.py --revisar  -> genera revisar_grupos.html para ajustar UMBRAL a ojo
"""
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
# Ajustado a mano con --revisar (oct. 2026). Un solo umbral no sirve: el modelo junta titulares que
# solo comparten tema o lugar ("Girona"). Por eso dos niveles:
ALTO = 0.85     # parecido (coseno) con el centro del grupo: se une siempre
BAJO = 0.72     # parecido medio: se une solo si comparte una palabra poco frecuente (un nombre propio raro)
RARO = 12       # "poco frecuente" = sale en como mucho estos titulares de la ventana
HORAS = 48      # ventana que se reagrupa en cada ejecución
CACHE = os.environ.get("TALAIA_MODELOS", ".modelos")


def vectores(titulos):
    from fastembed import TextEmbedding  # import aquí: los tests no necesitan el modelo
    v = np.array(list(TextEmbedding(MODELO, cache_dir=CACHE).embed(titulos)), dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def palabras(titulo):
    """Palabras de 4+ letras, sin mayúsculas ni acentos (así 'Lleó' y 'Lleo' coinciden)."""
    t = unicodedata.normalize("NFKD", titulo.lower())
    return set(re.findall(r"[a-z0-9]{4,}", "".join(c for c in t if not unicodedata.combining(c))))


def agrupar(v, titulos, alto=ALTO, bajo=BAJO, raro=RARO):
    """v: vectores normalizados, de la noticia más antigua a la más reciente.
    Cada noticia se une al grupo más parecido que cumpla la regla de dos niveles; si ninguno, abre uno.
    Comparar con el centro del grupo (no con un solo miembro) evita encadenar hechos distintos.
    Devuelve, para cada noticia, el índice de la noticia que abrió su grupo."""
    P = [palabras(t) for t in titulos]
    df = Counter(w for p in P for w in p)
    raras = [{w for w in p if df[w] <= raro} for p in P]
    sumas = np.zeros_like(v)        # suma de vectores de cada grupo
    centros = np.zeros_like(v)      # sumas normalizadas
    primero, grupo_de, raras_grupo = [], [], []
    for i, x in enumerate(v):
        g, elegido = len(primero), None
        if g:
            sims = centros[:g] @ x
            for k in np.argsort(-sims)[:5]:  # los 5 más parecidos bastan: el resto queda por debajo de BAJO
                if sims[k] >= alto or (sims[k] >= bajo and raras[i] & raras_grupo[k]):
                    elegido = k
                    break
        if elegido is None:
            sumas[g] = centros[g] = x
            primero.append(i)
            raras_grupo.append(set(raras[i]))
            grupo_de.append(i)
        else:
            sumas[elegido] += x
            centros[elegido] = sumas[elegido] / np.linalg.norm(sumas[elegido])
            raras_grupo[elegido] |= raras[i]
            grupo_de.append(primero[elegido])
    return grupo_de


def ventana(noticias, ahora):
    """Noticias a agrupar (sin verificadores), de la más antigua a la más reciente."""
    limite = (ahora - timedelta(hours=HORAS)).isoformat(timespec="seconds")
    return sorted((n for n in noticias if n["zona"] != "verificadores" and n["hora"] >= limite), key=lambda n: n["hora"])


def id_grupo(enlace):
    return hashlib.sha1(enlace.encode()).hexdigest()[:10]


def main(ruta="datos.json"):
    p = Path(ruta)
    datos = json.loads(p.read_text(encoding="utf-8"))
    N = ventana(datos["noticias"], datetime.now(timezone.utc))
    titulos = [n["titulo"] for n in N]
    grupo_de = agrupar(vectores(titulos), titulos)
    for n, g in zip(N, grupo_de):
        n["grupo"] = id_grupo(N[g]["enlace"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
    tamanos = np.bincount(grupo_de)
    print(f"{len(N)} noticias en {len(set(grupo_de))} grupos; {int((tamanos >= 2).sum())} con 2+ noticias", file=sys.stderr)


def revisar(ruta="datos.json"):
    """Página local para revisar a ojo: grupos actuales y parejas en la franja dudosa (BAJO-ALTO)."""
    import html
    N = ventana(json.loads(Path(ruta).read_text(encoding="utf-8"))["noticias"], datetime.now(timezone.utc))
    titulos = [n["titulo"] for n in N]
    v = vectores(titulos)
    g = agrupar(v, titulos)
    grupos = {}
    for i, k in enumerate(g):
        grupos.setdefault(k, []).append(N[i])
    multi = sorted((m for m in grupos.values() if len(m) > 1), key=len, reverse=True)
    e = lambda n: f'<li><b>{html.escape(n["medio"])}</b> · {html.escape(n["titulo"])}</li>'
    cuerpo = "".join(f'<details><summary>{len(m)} noticias · {len({x["medio"] for x in m})} medios · {html.escape(m[-1]["titulo"])}</summary><ul>{"".join(map(e, m))}</ul></details>' for m in multi)
    s = v @ v.T
    i, j = np.triu_indices(len(N), 1)
    dudosas = sorted(((s[a, b], a, b) for a, b in zip(i, j) if BAJO <= s[a, b] < ALTO and N[a]["medio"] != N[b]["medio"]), reverse=True)[:200]
    filas = "".join(f'<tr><td>{x:.2f}</td><td>{"✔ juntas" if g[a] == g[b] else "✘ separadas"}</td><td>{html.escape(N[a]["medio"])}: {html.escape(N[a]["titulo"])}</td><td>{html.escape(N[b]["medio"])}: {html.escape(N[b]["titulo"])}</td></tr>' for x, a, b in dudosas)
    Path("revisar_grupos.html").write_text(
        f'<!doctype html><meta charset="utf-8"><title>Revisar grupos</title>'
        f'<style>body{{font:14px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}}td{{border-top:1px solid #ddd;padding:.3rem;vertical-align:top}}summary{{cursor:pointer;padding:.2rem 0}}</style>'
        f'<h1>Revisar grupos ({len(N)} noticias, últimas {HORAS} h)</h1><p>ALTO={ALTO} · BAJO={BAJO} · RARO={RARO}</p>'
        f'<h2>{len(multi)} grupos con 2+ noticias</h2>{cuerpo}'
        f'<h2>Parejas dudosas ({BAJO}–{ALTO})</h2><table>{filas}</table>', encoding="utf-8")
    print("revisar_grupos.html generado", file=sys.stderr)


if __name__ == "__main__":
    revisar() if "--revisar" in sys.argv else main(*sys.argv[1:])
