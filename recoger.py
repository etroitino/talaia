# /// script
# requires-python = ">=3.12"
# dependencies = ["feedparser", "pyyaml"]
# ///
"""F1: lee los RSS de fuentes.yaml y actualiza datos.json (sin repetidas, últimos 7 días)."""
import calendar
import email.utils
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import feedparser
import yaml

UA = "Mozilla/5.0 (Mirador; lector RSS personal) feedparser"
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


def a_noticias(fuente, feed, ahora):
    # ponytail: no se guarda la entradilla — datos.json es público y sería copiar texto del medio.
    # La fase 3 la leerá del RSS al vuelo para la IA.
    noticias = []
    for e in feed.entries:
        enlace, titulo = e.get("link", "").strip(), " ".join(e.get("title", "").split())
        if not enlace.startswith(("http://", "https://")) or not titulo:
            continue
        t = e.get("published_parsed") or e.get("updated_parsed")
        hora = datetime.fromtimestamp(calendar.timegm(t), timezone.utc) if t else ahora
        if t and fuente.get("tz"):  # el RSS pone un desfase falso: su hora es de reloj en esta zona
            local = email.utils.parsedate_tz(e.get("published") or e.get("updated"))
            if local:
                hora = datetime(*local[:6], tzinfo=ZoneInfo(fuente["tz"])).astimezone(timezone.utc)
        noticias.append({
            "titulo": titulo,
            "enlace": enlace,
            "medio": fuente["nombre"],
            "zona": fuente["zona"],
            "muro": fuente.get("muro", "no"),
            "hora": min(hora, ahora).isoformat(timespec="seconds"),  # algunos RSS fechan en el futuro
        })
    return noticias


def fusionar(viejas, nuevas, ahora):
    """Une por enlace (se queda la primera vista), quita lo de hace más de DIAS y ordena de nueva a vieja."""
    limite = (ahora - timedelta(days=DIAS)).isoformat(timespec="seconds")
    por_enlace = {}
    for n in viejas + nuevas:
        por_enlace.setdefault(n["enlace"], n)
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
    datos.write_text(json.dumps({
        "actualizado": ahora.isoformat(timespec="seconds"),
        "fuentes_caidas": caidas,
        "noticias": noticias,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(noticias)} noticias, {len(fuentes) - len(caidas)}/{len(fuentes)} fuentes OK", file=sys.stderr)
    for c in caidas:
        print(f"  caída: {c['medio']}: {c['error']}", file=sys.stderr)


if __name__ == "__main__":
    main(*sys.argv[1:])
