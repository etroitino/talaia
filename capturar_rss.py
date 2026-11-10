# /// script
# requires-python = ">=3.12"
# dependencies = ["feedparser", "pyyaml"]
# ///
"""V1 · lote RSS: lee fuentes.yaml y escribe un lote comprimido con manifiesto (sin IA, sin Pages, sin estado previo).

  uv run capturar_rss.py DIR      -> DIR/lote.json.gz

Contrato (esquema 1). Un lote es una foto de los RSS en un instante, no un incremento: dos lotes se solapan y
el importador deduplica por id. Solo metadatos mínimos; nunca entradillas ni cuerpos.
  esquema, lote (id único por ejecución e intento), origen (repositorio, workflow, run_id, intento, sha, evento),
  corte (instante de lectura, UTC), fin, huella (sha256 de `articulos`),
  fuentes: {id: {estado: ok|error, error, entradas, articulos, desde, hasta}}  (desde/hasta: fechas extremas del RSS)
  articulos: [{id, titulo, enlace, fuente, hora, muro[, hora_rss_futura]}]  (id = recoger.id_articulo(enlace))
"""
import gzip
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import yaml

from recoger import a_noticias, actualizar_estado, descargar

ESQUEMA = 1
CAMPOS = ("id", "titulo", "enlace", "fuente", "hora", "muro", "hora_rss_futura")


def huella(articulos):
    return hashlib.sha256(json.dumps(articulos, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def construir(fuentes, leidos, corte, fin, origen):
    """leidos: [(fuente, feed | None, error | None)]. El fallo de una fuente queda en su estado; el lote sigue."""
    arts, estado = {}, {}
    for f, feed, error in leidos:
        if error:
            estado[f["id"]] = {"estado": "error", "error": error[:200]}
            continue
        e = actualizar_estado(None, f, feed, None, corte)
        ns = a_noticias(f, feed, corte)
        for n in ns:
            arts.setdefault(n["id"], {k: n[k] for k in CAMPOS if k in n})
        estado[f["id"]] = {"estado": "ok", "error": None, "entradas": e["entradas"], "articulos": len(ns),
                           "desde": e.get("entrada_mas_antigua"), "hasta": e.get("entrada_mas_reciente")}
    articulos = sorted(arts.values(), key=lambda a: a["id"])
    iso = lambda d: d.isoformat(timespec="seconds")
    return {"esquema": ESQUEMA, "lote": f'{origen["run_id"]}-{origen["intento"]}' if origen.get("run_id") else f"local-{iso(corte)}",
            "origen": origen, "corte": iso(corte), "fin": iso(fin), "huella": huella(articulos),
            "fuentes": estado, "articulos": articulos}


def main(salida):
    fuentes = yaml.safe_load(Path("fuentes.yaml").read_text(encoding="utf-8"))["fuentes"]
    corte = datetime.now(timezone.utc).replace(microsecond=0)

    def leer(f):
        try:
            return f, descargar(f), None
        except Exception as e:
            return f, None, str(e) or type(e).__name__

    with ThreadPoolExecutor(8) as ex:
        leidos = list(ex.map(leer, fuentes))
    env = os.environ.get
    origen = {"repositorio": env("GITHUB_REPOSITORY"), "workflow": env("GITHUB_WORKFLOW_REF"), "run_id": env("GITHUB_RUN_ID"),
              "intento": env("GITHUB_RUN_ATTEMPT"), "sha": env("GITHUB_SHA"), "evento": env("GITHUB_EVENT_NAME")}
    lote = construir(fuentes, leidos, corte, datetime.now(timezone.utc).replace(microsecond=0), origen)
    Path(salida).mkdir(parents=True, exist_ok=True)
    with gzip.open(Path(salida) / "lote.json.gz", "wt", encoding="utf-8") as f:
        json.dump(lote, f, ensure_ascii=False, separators=(",", ":"))
    caidas = [k for k, e in lote["fuentes"].items() if e["estado"] == "error"]
    print(f"lote {lote['lote']}: {len(lote['articulos'])} artículos, {len(fuentes) - len(caidas)}/{len(fuentes)} fuentes OK"
          + (f"; caídas: {', '.join(caidas)}" if caidas else ""), file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "lote")
