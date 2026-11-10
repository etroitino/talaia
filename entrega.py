# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Fase 0: ensayo de entrega de un candidato con datos SINTÉTICOS (no es el publicador de la fase 4).

  uv run fase0/entrega.py candidato DIR --base ID [--corromper]   -> lote sintético con manifiesto y huellas
  uv run fase0/entrega.py validar DIR --confirmado ESTADO.json      -> sale con 1 si el lote no es válido
  uv run fase0/entrega.py montar DIR SALIDA                         -> sitio mínimo con su identificador de publicación
  uv run fase0/entrega.py reconciliar --preparado ID --conclusion success|failure|unknown --publicado ID|-
  uv run fase0/entrega.py                                           -> autocomprobación
"""
import hashlib
import json
import sys
from pathlib import Path

ESQUEMA = 0


def huella(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def candidato(dir_, base, corromper=False):
    d = Path(dir_); d.mkdir(parents=True, exist_ok=True)
    edicion = {"synthetic": True, "fecha": "2026-11-10", "acontecimientos": [
        {"id": f"2026-11-10-{i}", "titular": f"Acontecimiento sintético {i}", "resumen": "Texto de prueba, no es una noticia real.",
         "evidencias": [{"id": f"ev-{i}", "url": "https://example.org/", "fuente": "sintética"}]} for i in range(1, 6)]}
    (d / "edicion.json").write_text(json.dumps(edicion, ensure_ascii=False, indent=1))
    archivos = {"edicion.json": huella(d / "edicion.json")}
    lote = hashlib.sha256(json.dumps([base, archivos], sort_keys=True).encode()).hexdigest()[:16]
    man = {"esquema": ESQUEMA, "lote": lote, "base": base, "fecha_editorial": "2026-11-10",
           "corte": "2026-11-10T06:00:00+00:00", "synthetic": True, "archivos": archivos}
    (d / "manifiesto.json").write_text(json.dumps(man, indent=1))
    if corromper:  # el contenido cambia después de calcular la huella
        (d / "edicion.json").write_text((d / "edicion.json").read_text().replace("sintético 1", "alterado 1"))
    return lote


def validar(dir_, confirmado):
    d, errores = Path(dir_), []
    man = json.loads((d / "manifiesto.json").read_text())
    if man.get("esquema") != ESQUEMA:
        errores.append(f"esquema {man.get('esquema')} no admitido")
    if man.get("synthetic") is not True:
        errores.append("el ensayo solo admite datos marcados synthetic")
    if man.get("base") != confirmado.get("publicacion"):
        errores.append(f"base obsoleta: {man.get('base')} != {confirmado.get('publicacion')}")
    for nombre, h in man.get("archivos", {}).items():
        if not (d / nombre).is_file() or huella(d / nombre) != h:
            errores.append(f"huella no coincide: {nombre}")
    ed = json.loads((d / "edicion.json").read_text()) if (d / "edicion.json").is_file() else {}
    if not 5 <= len(ed.get("acontecimientos", [])) <= 7:
        errores.append("la edición no tiene 5–7 acontecimientos")
    return errores


def montar(dir_, salida, revision_codigo="local"):
    man = json.loads((Path(dir_) / "manifiesto.json").read_text())
    pub = hashlib.sha256(f"{man['lote']}:{revision_codigo}".encode()).hexdigest()[:16]
    s = Path(salida); s.mkdir(parents=True, exist_ok=True)
    (s / "publicacion.json").write_text(json.dumps({"publicacion": pub, "lote": man["lote"], "base": man["base"],
                                                     "revision_codigo": revision_codigo, "synthetic": True}, indent=1))
    (s / "index.html").write_text(f'<!doctype html><meta charset="utf-8"><title>Ensayo V1</title><p>Datos sintéticos · publicación {pub}</p>')
    return pub


def reconciliar(preparado, conclusion, publicado):
    """Tras un corte entre despliegue y confirmación: confirmar solo si Actions terminó bien y el identificador
    servido coincide con el preparado; reintentar si falló antes de servir; bloquear si es incierto."""
    if conclusion == "success" and publicado == preparado:
        return "confirmar"
    if conclusion == "failure" and publicado != preparado:
        return "reintentar"
    return "bloquear"


def demo():
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        ok, mal, viejo = Path(t, "ok"), Path(t, "mal"), Path(t, "viejo")
        a = candidato(ok, "pub-0")
        assert candidato(ok, "pub-0") == a  # repetir el mismo candidato da el mismo lote (idempotente)
        candidato(mal, "pub-0", corromper=True)
        candidato(viejo, "pub-anterior")
        conf = {"publicacion": "pub-0"}
        assert validar(ok, conf) == []
        assert any("huella" in e for e in validar(mal, conf))
        assert any("obsoleta" in e for e in validar(viejo, conf))
        p = montar(ok, Path(t, "sitio"), "abc")
        assert p == montar(ok, Path(t, "sitio2"), "abc")  # mismo lote y código -> misma publicación
    assert reconciliar("p1", "success", "p1") == "confirmar"
    assert reconciliar("p1", "failure", "p0") == "reintentar"
    assert reconciliar("p1", "success", "p0") == "bloquear"
    assert reconciliar("p1", "unknown", "p1") == "bloquear"
    print("OK")


if __name__ == "__main__":
    a = sys.argv[1:]
    arg = lambda k: a[a.index(k) + 1]
    if not a:
        demo()
    elif a[0] == "candidato":
        print(candidato(a[1], arg("--base"), "--corromper" in a))
    elif a[0] == "validar":
        errores = validar(a[1], json.loads(Path(arg("--confirmado")).read_text()))
        print("\n".join(errores) or "válido")
        sys.exit(1 if errores else 0)
    elif a[0] == "montar":
        print(montar(a[1], a[2], arg("--revision") if "--revision" in a else "local"))
    elif a[0] == "reconciliar":
        print(reconciliar(arg("--preparado"), arg("--conclusion"), arg("--publicado")))
