# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
"""Monta el sitio de Pages en _site/ a partir de datos.json, fuentes.yaml y los informes de la rama archivo.
Es el ÚNICO sitio que se publica: así ningún despliegue borra lo del otro.

  uv run montar_sitio.py [--datos datos.json] [--archivo .archivo] [--salida _site]
                         [--publicado URL]   # URL base del sitio publicado: respaldo de semana/ y control de versión

Archivos públicos:
  ultimas24h.json   lo que necesita Directo (24 h, sin cuerpos de artículos)
  version.json      marca pequeña: la página solo descarga ultimas24h.json si cambia
  fuentes.json      estado de las fuentes y titulares excluidos (vista Fuentes)
  datos.json        archivo móvil de 7 días (compatibilidad)
  semana/           catálogo e informes semanales
"""
import hashlib
import json
import shutil
import sys
import urllib.request
from datetime import timedelta
from pathlib import Path

import yaml

from archivo import hora_utc

ESTATICOS = ["index.html", "estilo.css", "app.js", "semana.js"]
HORAS_DIRECTO = 24
CAMPOS_DIRECTO = ("id", "titulo", "enlace", "fuente", "zona", "muro", "hora", "grupo")
CAMPOS_FUENTE = ("id", "nombre", "zona", "pais", "idioma")


def directo(datos, fuentes, semana_idx):
    """Contenido de ultimas24h.json. Las horas futuras ya vienen recortadas por recoger.py; aquí se
    descarta además lo que quede fuera de [actualizado - 24 h, actualizado + 5 min]."""
    por_nombre = {f["nombre"]: f["id"] for f in fuentes}  # datos de versiones anteriores, sin "fuente"
    for n in datos["noticias"]:
        n.setdefault("fuente", por_nombre.get(n.get("medio")))
        n.setdefault("id", hashlib.sha1(n["enlace"].encode()).hexdigest()[:12])
    fin = hora_utc(datos["actualizado"])
    ini = fin - timedelta(hours=HORAS_DIRECTO)
    noticias = [{k: n[k] for k in CAMPOS_DIRECTO if n.get(k) is not None}
                for n in datos["noticias"]
                if ini <= hora_utc(n["hora"]) <= fin + timedelta(minutes=5) and n["enlace"].startswith(("http://", "https://"))]
    # Enlace Directo -> Semana: solo por artículo exacto (id), nunca por parecido
    comparar = {}
    for inf in semana_idx.get("informes", [])[:2]:
        for aid, ev in (inf.get("articulos") or {}).items():
            comparar.setdefault(aid, f"{inf['week_id']}/{ev}")
    cuerpo = {
        "actualizado": datos["actualizado"],
        "ventana_horas": HORAS_DIRECTO,
        "fuentes_caidas": datos.get("fuentes_caidas", []),
        "fuentes": [{k: f.get(k) for k in CAMPOS_FUENTE} for f in fuentes],
        "comparar": comparar,
        "noticias": noticias,
    }
    version = hashlib.sha256(json.dumps(cuerpo, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    return {"version": version, **cuerpo}


def estado_fuentes(datos, fuentes):
    estado = datos.get("fuentes_estado", {})
    campos = ("id", "nombre", "zona", "pais", "idioma", "rss", "muro", "nota", "sustituye")
    return {
        "actualizado": datos["actualizado"],
        "fuentes": [{**{k: f.get(k) for k in campos if f.get(k) is not None}, "muro": str(f.get("muro", "no")),
                     "estado": estado.get(f["id"], {})} for f in fuentes],
        "excluidas": datos.get("excluidas", []),
    }


def descargar(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "talaia-montar"}), timeout=30) as r:
        return r.read()


def semana_desde(archivo, publicado):
    """Carpeta semana/ de la rama archivo; si no está disponible, la copia publicada (nunca se publica sin ella
    si el sitio ya tenía informes). Devuelve {ruta relativa: bytes}."""
    carpeta = Path(archivo) / "semana" if archivo else None
    if carpeta and carpeta.is_dir():
        return {p.relative_to(carpeta).as_posix(): p.read_bytes() for p in carpeta.rglob("*") if p.is_file() and not p.name.endswith(".tmp")}
    if not publicado:
        return {}
    try:
        idx = descargar(f"{publicado}/semana/index.json")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        raise
    archivos = {"index.json": idx}
    for inf in json.loads(idx).get("informes", []):
        for ext in ("json", "md"):
            nombre = f"{inf['week_id']}.{ext}"
            archivos[nombre] = descargar(f"{publicado}/semana/{nombre}")
    print("montar: semana/ tomada de la copia publicada (archivo no disponible)", file=sys.stderr)
    return archivos


def validar_semana(archivos):
    for nombre, contenido in archivos.items():
        if nombre.endswith(".json"):
            json.loads(contenido)  # lanza si está corrupto: mejor no publicar que publicar roto
    idx = json.loads(archivos.get("index.json", b'{"informes": []}'))
    for inf in idx.get("informes", []):
        if f"{inf['week_id']}.json" not in archivos:
            raise ValueError(f"semana/index.json cita {inf['week_id']} pero falta el archivo")
    return idx


def comprobar_publicado(publicado, actualizado):
    """Una actualización antigua no debe pisar otra más reciente."""
    try:
        v = json.loads(descargar(f"{publicado}/version.json"))
    except Exception:
        return
    if v.get("actualizado", "") > actualizado:
        sys.exit(f"montar: lo publicado ({v['actualizado']}) es más reciente que estos datos ({actualizado}); no se publica")


def montar(datos_ruta="datos.json", archivo=".archivo", salida="_site", publicado=None, raiz="."):
    raiz = Path(raiz)
    datos = json.loads(Path(datos_ruta).read_text(encoding="utf-8"))
    fuentes = yaml.safe_load((raiz / "fuentes.yaml").read_text(encoding="utf-8"))["fuentes"]
    if publicado:
        comprobar_publicado(publicado, datos["actualizado"])
    semana = semana_desde(archivo, publicado)
    idx = validar_semana(semana)
    d24 = directo(datos, fuentes, idx)

    salida = Path(salida)
    tmp = salida.with_name(salida.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / "semana").mkdir(parents=True)
    for f in ESTATICOS:
        shutil.copy(raiz / f, tmp / f)
    compacto = lambda o: json.dumps(o, ensure_ascii=False, separators=(",", ":"))
    (tmp / "ultimas24h.json").write_text(compacto(d24), encoding="utf-8")
    (tmp / "version.json").write_text(compacto({"version": d24["version"], "actualizado": datos["actualizado"],
                                                 "semana": hashlib.sha256(semana.get("index.json", b"")).hexdigest()[:16]}), encoding="utf-8")
    (tmp / "fuentes.json").write_text(compacto(estado_fuentes(datos, fuentes)), encoding="utf-8")
    (tmp / "datos.json").write_text(compacto(datos), encoding="utf-8")
    if "index.json" not in semana:
        semana["index.json"] = compacto({"schema_version": "1.0", "informes": []}).encode()
    for nombre, contenido in semana.items():
        (tmp / "semana" / nombre).parent.mkdir(parents=True, exist_ok=True)
        (tmp / "semana" / nombre).write_bytes(contenido)
    shutil.rmtree(salida, ignore_errors=True)
    tmp.rename(salida)
    print(f"montar: {len(d24['noticias'])} noticias en ultimas24h.json, {len(idx.get('informes', []))} informes semanales", file=sys.stderr)
    return salida


if __name__ == "__main__":
    a = sys.argv[1:]
    op = lambda k, d: a[a.index(k) + 1] if k in a else d
    montar(op("--datos", "datos.json"), op("--archivo", ".archivo"), op("--salida", "_site"), op("--publicado", None))
