"""Validación de evidencias: ninguna afirmación del informe sin una cita literal comprobada.

Normalizaciones permitidas al comparar una cita con el texto (y solo estas):
  1. Unicode NFKC (p. ej. «…» = «...», ligaduras)
  2. comillas tipográficas y angulares unificadas (“ ” « » „ → ", ‘ ’ ‚ → ')
  3. caracteres invisibles eliminados y espacios colapsados
La cita que se muestra es el fragmento tal cual aparece en el texto del artículo, no la versión del modelo.
Se rechazan: citas que no están en el artículo indicado, fragmentos unidos, puntos suspensivos inventados
(no aparecerían en el texto), citas demasiado cortas o largas y atribuciones que no se pueden comprobar.
"""
import re
import unicodedata

COMILLAS = {ord(c): '"' for c in "“”„‟«»″"} | {ord(c): "'" for c in "‘’‚‛′"}
INVISIBLES = dict.fromkeys(map(ord, "­​‌‍⁠﻿"))
HABLANTES = {"periodista", "entrevistado", "comunicado", "fuente_citada", "desconocido"}


def _canon_char(c):
    return unicodedata.normalize("NFKC", c).translate(COMILLAS).translate(INVISIBLES)


def canon(s):
    return " ".join("".join(map(_canon_char, unicodedata.normalize("NFC", s))).split())


def _mapa(texto):
    """Texto canónico y, para cada carácter suyo, su posición en `texto`."""
    salida, pos, espacio = [], [], False
    for i, c in enumerate(texto):
        for d in _canon_char(c):
            if d.isspace():
                espacio = bool(salida)
                continue
            if espacio:
                salida.append(" "); pos.append(i); espacio = False
            salida.append(d); pos.append(i)
    return "".join(salida), pos


def localizar(cita, texto):
    """(inicio, fin) de la cita en `texto` según las normalizaciones documentadas, o None."""
    q = canon(cita).strip(" \"'")
    if not q:
        return None
    c, pos = _mapa(texto)
    i = c.find(q)
    if i < 0:
        return None
    return pos[i], pos[i + len(q) - 1] + 1


def sin_acentos(s):
    return "".join(ch for ch in unicodedata.normalize("NFKD", canon(s).casefold()) if not unicodedata.combining(ch))


def _texto(x, maximo):
    return x.strip()[:maximo] if isinstance(x, str) and x.strip() else None


def validar_articulo(salida, articulo, texto, lim):
    """Valida la respuesta del modelo para un artículo. Devuelve (resultado, rechazos).
    resultado: {"evidence": [...], "framing_claims": [...], ...} con ids estables; rechazos: motivos."""
    if not isinstance(salida, dict):
        return None, ["la respuesta no es un objeto JSON"]
    rechazos, evidencias, por_ref, ocupado = [], [], {}, []
    max_total = max(lim["cita_max_caracteres"], int(lim["citas_max_proporcion"] * len(texto)))
    total = 0
    for e in salida.get("evidencias") or []:
        if not isinstance(e, dict) or not isinstance(e.get("cita"), str):
            rechazos.append("evidencia sin cita"); continue
        ref = str(e.get("ref") or "")
        lugar = localizar(e["cita"], texto)
        cita = texto[lugar[0]:lugar[1]] if lugar else None
        if not lugar:
            rechazos.append(f"{ref}: la cita no aparece en el texto de este artículo"); continue
        if len(cita) > lim["cita_max_caracteres"]:
            rechazos.append(f"{ref}: cita demasiado larga ({len(cita)})"); continue
        if len(cita.split()) < 3:
            rechazos.append(f"{ref}: cita demasiado corta"); continue
        if any(a < lugar[1] and lugar[0] < b for a, b in ocupado):
            rechazos.append(f"{ref}: se solapa con otra cita"); continue
        if len(evidencias) >= lim["citas_max_por_articulo"] or total + len(cita) > max_total:
            rechazos.append(f"{ref}: supera el límite de citas por artículo"); continue
        tipo = e.get("hablante_tipo") if e.get("hablante_tipo") in HABLANTES else "desconocido"
        nombre = _texto(e.get("hablante"), 120)
        if nombre and tipo != "periodista":
            # La atribución se comprueba: el nombre (alguna palabra de 4+ letras) debe estar cerca de la cita
            cerca = sin_acentos(texto[max(0, lugar[0] - 400):lugar[1] + 400])
            partes = [p for p in re.findall(r"\w{4,}", sin_acentos(nombre))]
            if partes and not any(p in cerca for p in partes):
                rechazos.append(f"{ref}: la atribución a «{nombre}» no se encuentra junto a la cita"); continue
        if tipo == "periodista":
            nombre = None
        ocupado.append(lugar)
        total += len(cita)
        ev = {"id": f"e-{articulo['id']}-{len(evidencias) + 1}", "article_id": articulo["id"], "exact_quote": cita,
              "language": articulo.get("language") or "und",
              "translation_es": None if (articulo.get("language") or "").startswith("es") else _texto(e.get("traduccion_es"), 600),
              "speaker": {"type": tipo, "name": nombre}, "text_hash": articulo["text_hash"], "extraction_scope": articulo["extraction_scope"]}
        evidencias.append(ev)
        por_ref[ref] = ev["id"]

    def refs(c):
        return list(dict.fromkeys(por_ref[r] for r in (c.get("evidencias") or []) if isinstance(r, str) and r in por_ref))

    def afirmaciones(clave, campos, max_items=6):
        salida_ok = []
        for c in salida.get(clave) or []:
            if not isinstance(c, dict):
                continue
            ids = refs(c)
            valores = {k: _texto(c.get(k), m) for k, m in campos.items()}
            if not ids:
                rechazos.append(f"{clave}: afirmación sin evidencia válida"); continue
            if any(v is None for k, v in valores.items() if k in REQUERIDOS):
                continue
            salida_ok.append({**valores, "evidence_ids": ids})
        return salida_ok[:max_items]

    REQUERIDOS = {"texto", "termino", "alternativa_descriptiva", "actor", "fuente", "tema", "valor"}
    hechos = []
    for h in afirmaciones("hechos", {"texto": 300}):
        orig = next((x for x in salida.get("hechos") or [] if isinstance(x, dict) and _texto(x.get("texto"), 300) == h["texto"]), {})
        citas = " ".join(sin_acentos(ev["exact_quote"]) for ev in evidencias if ev["id"] in h["evidence_ids"])
        claves = [k for k in (orig.get("claves") or []) if isinstance(k, str) and k.strip() and sin_acentos(k) in citas][:4]
        if claves:
            hechos.append({**h, "claves": claves})
        else:
            rechazos.append("hecho sin palabras clave presentes en su evidencia")
    cifras = []
    for c in afirmaciones("cifras", {"tema": 120, "valor": 60}):
        citas = " ".join(canon(ev["exact_quote"]) for ev in evidencias if ev["id"] in c["evidence_ids"])
        if canon(c["valor"]) in citas:
            cifras.append(c)
        else:
            rechazos.append(f"cifra «{c['valor']}» no aparece en su evidencia")
    usados = set()
    resultado = {
        "evidence": evidencias,
        "framing_claims": [{"text": c["texto"], "evidence_ids": c["evidence_ids"]} for c in afirmaciones("encuadre", {"texto": 300})],
        "language_claims": [{"term": c["termino"], "descriptive_alternative": c["alternativa_descriptiva"], "evidence_ids": c["evidence_ids"]}
                            for c in afirmaciones("lenguaje", {"termino": 80, "alternativa_descriptiva": 120})],
        "actor_claims": [{"actor": c["actor"], "role": c.get("papel"), "evidence_ids": c["evidence_ids"]} for c in afirmaciones("actores", {"actor": 100, "papel": 120})],
        "cited_source_claims": [{"source": c["fuente"], "evidence_ids": c["evidence_ids"]} for c in afirmaciones("fuentes_citadas", {"fuente": 120})],
        "facts": hechos,
        "figures": cifras,
    }
    # El término cargado tiene que estar literalmente en su cita
    buenos = []
    for c in resultado["language_claims"]:
        citas = " ".join(sin_acentos(ev["exact_quote"]) for ev in evidencias if ev["id"] in c["evidence_ids"])
        (buenos.append(c) if sin_acentos(c["term"]) in citas else rechazos.append(f"término «{c['term']}» no está en su cita"))
    resultado["language_claims"] = buenos
    # Solo se publican las evidencias que sostienen alguna afirmación
    for k in ("framing_claims", "language_claims", "actor_claims", "cited_source_claims", "facts", "figures"):
        for c in resultado[k]:
            usados |= set(c["evidence_ids"])
    resultado["evidence"] = [e for e in evidencias if e["id"] in usados]
    return resultado, rechazos


def omision_valida(hecho, articulo_hecho, comparado, texto_comparado):
    """Una omisión solo se afirma con evidencia positiva en un artículo y texto COMPLETO del comparado,
    publicado después (podía conocer el hecho) y sin ninguna de las palabras clave del hecho."""
    if comparado["access_status"] != "completo" or comparado["extraction_scope"] != "cuerpo_completo" or not texto_comparado:
        return False
    if comparado["source_id"] == articulo_hecho["source_id"] or comparado["published_at"] < articulo_hecho["published_at"]:
        return False
    claves = hecho["claves"]
    if (comparado.get("language") or "")[:2] != (articulo_hecho.get("language") or "")[:2]:
        # entre idiomas solo valen cifras y nombres propios, que no se traducen
        claves = [k for k in claves if re.search(r"\d", k) or k[:1].isupper()]
        if not claves:
            return False
    t = sin_acentos(texto_comparado)
    return not any(sin_acentos(k) in t for k in claves)
