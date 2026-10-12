# /// script
# requires-python = ">=3.12"
# dependencies = ["feedparser", "pyyaml"]
# ///
"""F1: lee los RSS de fuentes.yaml y actualiza datos.json (sin repetidas, últimos 7 días)."""
import calendar
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import yaml

UA = "Mozilla/5.0 (Talaia; lector RSS personal) feedparser"
UA_NAVEGADOR = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
DIAS = 7


def descargar(fuente):
    """Devuelve el feed parseado o lanza excepción con el motivo."""
    ua = UA_NAVEGADOR if fuente.get("ua_navegador") else UA
    req = urllib.request.Request(fuente["rss"], headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=20) as r:
        feed = feedparser.parse(r.read())
    if not feed.entries:
        raise ValueError(f"sin entradas ({feed.get('bozo_exception', 'no es RSS')})")
    return feed


def limpiar_enlace(url):
    """Quita parámetros de seguimiento (utm_*, at_*) y el #fragmento, para no duplicar la misma noticia."""
    p = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith(("utm_", "at_"))]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))


def a_noticias(fuente, feed, ahora):
    # ponytail: no se guarda la entradilla — datos.json es público y sería copiar texto del medio.
    # La fase 3 la leerá del RSS al vuelo para la IA.
    noticias = []
    for e in feed.entries:
        enlace, titulo = e.get("link", "").strip(), " ".join(e.get("title", "").split())
        # "://" repetido: enlace roto con otra URL dentro (p. ej. notas de prensa sindicadas)
        if not enlace.startswith(("http://", "https://")) or "://" in enlace[8:] or not titulo:
            continue
        enlace = limpiar_enlace(enlace)
        metodo = str(fuente.get("muro", "no"))
        if metodo.startswith("rss:"):
            muro = any(t.get("term") == metodo[4:] for t in e.get("tags", []))
        else:
            muro = False if metodo == "no" else None  # None: hay que mirar la página del artículo
        t = e.get("published_parsed") or e.get("updated_parsed")
        hora = datetime.fromtimestamp(calendar.timegm(t), timezone.utc) if t else ahora
        noticias.append({
            "titulo": titulo,
            "enlace": enlace,
            "medio": fuente["nombre"],
            "zona": fuente["zona"],
            "muro": muro,
            "hora": min(hora, ahora).isoformat(timespec="seconds"),  # algunos RSS fechan en el futuro
        })
    return noticias


def tiene_muro(html, metodo):
    """Lee solo los metadatos de la página; no se guarda nada de su texto."""
    secciones = re.findall(r'"hasPart"\s*:\s*\[?\s*\{([^{}]*)\}', html)
    oculta = any(re.search(r'"isAccessibleForFree"\s*:\s*"?false', s, re.I) and '"cssSelector"' in s for s in secciones)
    if metodo == "ld":
        return oculta
    if metodo.startswith("texto:"):
        cerrada = re.search(r'"isAccessibleForFree"\s*:\s*"?false', html, re.I)
        return bool(cerrada) and metodo[6:].lower() in html.lower()
    raise ValueError(f"método de muro desconocido: {metodo}")


def comprobar_muros(noticias, fuentes):
    """Rellena muro=True/False en las noticias pendientes. Si la página falla, queda None y se reintenta la próxima vez."""
    por_medio = {f["nombre"]: f for f in fuentes}
    pendientes = [n for n in noticias if n["muro"] is None and n["medio"] in por_medio]

    def mirar(n):
        f = por_medio[n["medio"]]
        ua = UA_NAVEGADOR if f.get("ua_navegador") else UA
        try:
            with urllib.request.urlopen(urllib.request.Request(n["enlace"], headers={"User-Agent": ua}), timeout=20) as r:
                n["muro"] = tiene_muro(r.read().decode("utf-8", "replace"), str(f["muro"]))
        except Exception:
            pass

    with ThreadPoolExecutor(8) as ex:
        list(ex.map(mirar, pendientes))
    return sum(n["muro"] is None for n in pendientes)


def fusionar(viejas, nuevas, ahora):
    """Une por enlace, quita lo de hace más de DIAS y ordena de nueva a vieja.
    Si una noticia ya estaba, se actualiza su titular (los medios los corrigen) pero se conservan su hora y su muro."""
    limite = (ahora - timedelta(days=DIAS)).isoformat(timespec="seconds")
    por_enlace = {n["enlace"]: n for n in viejas}
    for n in nuevas:
        if n["enlace"] in por_enlace:
            por_enlace[n["enlace"]]["titulo"] = n["titulo"]
        else:
            por_enlace[n["enlace"]] = n
    # ISO en UTC con el mismo formato: se compara como texto
    return sorted((n for n in por_enlace.values() if n["hora"] >= limite), key=lambda n: n["hora"], reverse=True)


def main(ruta_fuentes="fuentes.yaml", ruta_datos="datos.json"):
    fuentes = yaml.safe_load(Path(ruta_fuentes).read_text(encoding="utf-8"))["fuentes"]
    ahora = datetime.now(timezone.utc).replace(microsecond=0)

    def leer(f):
        try:
            return f, descargar(f), None
        except Exception as e:
            return f, None, str(e)

    nuevas, caidas = [], []
    with ThreadPoolExecutor(8) as ex:
        for f, feed, error in ex.map(leer, fuentes):
            if error:
                caidas.append({"medio": f["nombre"], "error": error})
            else:
                nuevas += a_noticias(f, feed, ahora)

    datos = Path(ruta_datos)
    viejas = json.loads(datos.read_text(encoding="utf-8"))["noticias"] if datos.exists() else []
    noticias = fusionar(viejas, nuevas, ahora)
    sin_mirar = comprobar_muros(noticias, fuentes)
    tmp = datos.with_suffix(".tmp")  # escribir aparte y sustituir: nunca queda un datos.json a medias
    tmp.write_text(json.dumps({
        "actualizado": ahora.isoformat(timespec="seconds"),
        "fuentes_caidas": caidas,
        "noticias": noticias,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(datos)
    print(f"{len(noticias)} noticias ({sum(n['muro'] is True for n in noticias)} con muro, {sin_mirar} sin poder mirar), "
          f"{len(fuentes) - len(caidas)}/{len(fuentes)} fuentes OK", file=sys.stderr)
    for c in caidas:
        print(f"  caída: {c['medio']}: {c['error']}", file=sys.stderr)


if __name__ == "__main__":
    main(*sys.argv[1:])
