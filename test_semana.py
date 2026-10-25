# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "pyyaml", "jsonschema", "feedparser"]
# ///
"""Pruebas del informe semanal con datos SINTÉTICOS (medios reales de fuentes.yaml, textos y hechos inventados).
Sin red, sin modelo de embeddings y sin IA real: el cliente de Groq se simula. Ejecutar: uv run test_semana.py"""
import copy
import json
import re
import tempfile
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

import archivo
import montar_sitio
import semana
from evidencias import localizar, omision_valida, validar_articulo
from extraer import extraer
from ia import Cliente, SinIA

M, U = ZoneInfo("Europe/Madrid"), timezone.utc
conf, fuentes = semana.cargar_config()
conf = copy.deepcopy(conf)
conf["semana"]["min_caracteres_completo"] = 80
conf["ia"]["pausa_minima_s"] = 0
LIM = conf["semana"]

# --- Evidencias: unidad ---
texto = 'El ministro Juan Pérez afirmó que «la cumbre fue un éxito rotundo» ante la prensa. Murieron 12 personas en los disturbios.'
assert localizar('la cumbre fue un "éxito rotundo"', texto) is None                 # comillas en otro sitio: no es literal
assert texto[slice(*localizar("la cumbre fue un éxito rotundo", texto))] == "la cumbre fue un éxito rotundo"
assert localizar("«la cumbre fue un éxito rotundo»", texto)                          # comillas angulares = rectas
assert localizar("la cumbre fue un éxito ... ante la prensa", texto) is None        # puntos suspensivos inventados
assert localizar("la cumbre fue un éxito rotundo. Murieron 12", texto) is None      # fragmentos unidos
assert localizar("la  cumbre\nfue un éxito", texto)                                  # espacios: normalización documentada
art = {"id": "a1", "language": "es", "text_hash": "sha256:" + "0" * 64, "extraction_scope": "cuerpo_completo"}
r, rech = validar_articulo({"evidencias": [
    {"ref": "e1", "cita": "la cumbre fue un éxito rotundo", "hablante_tipo": "entrevistado", "hablante": "Juan Pérez", "traduccion_es": "x"},
    {"ref": "e2", "cita": "la cumbre fue un fracaso total", "hablante_tipo": "periodista"},              # inventada
    {"ref": "e3", "cita": "Murieron 12 personas en los disturbios", "hablante_tipo": "entrevistado", "hablante": "Ana López"},  # atribución falsa
], "encuadre": [{"texto": "Presenta la cumbre como un éxito", "evidencias": ["e1"]}, {"texto": "Sin evidencia", "evidencias": ["e2"]}],
   "lenguaje": [{"termino": "rotundo", "alternativa_descriptiva": "claro", "evidencias": ["e1"]}, {"termino": "masacre", "alternativa_descriptiva": "x", "evidencias": ["e1"]}]},
    art, texto, LIM)
assert [e["exact_quote"] for e in r["evidence"]] == ["la cumbre fue un éxito rotundo"], r
assert r["evidence"][0]["translation_es"] is None                                     # artículo en español: sin traducción
assert len(r["framing_claims"]) == 1 and [c["term"] for c in r["language_claims"]] == ["rotundo"]
assert any("no aparece" in x for x in rech) and any("Ana López" in x for x in rech) and any("masacre" in x for x in rech)
assert validar_articulo("no es un objeto", art, texto, LIM)[0] is None

# Omisión: solo con texto completo del comparado, publicado después y sin las claves
hecho = {"claves": ["12"], "texto": "12 muertos"}
A = {"source_id": "el-pais", "published_at": "2026-10-20T10:00:00+00:00", "language": "es"}
B = {"source_id": "tass", "published_at": "2026-10-20T12:00:00+00:00", "language": "en", "access_status": "completo", "extraction_scope": "cuerpo_completo"}
assert omision_valida(hecho, A, B, "The summit ended with no deaths reported.")
assert not omision_valida(hecho, A, {**B, "access_status": "parcial", "extraction_scope": "cuerpo_parcial"}, "The summit ended.")  # parcial: no
assert not omision_valida(hecho, A, {**B, "extraction_scope": "recortado"}, "The summit ended.")
assert not omision_valida(hecho, A, {**B, "published_at": "2026-10-20T08:00:00+00:00"}, "The summit ended.")                   # anterior: no comparable
assert not omision_valida(hecho, A, B, "Officials said 12 people died.")                                                          # sí lo contiene
assert not omision_valida({"claves": ["muertos"], "texto": "x"}, A, B, "The summit ended.")  # entre idiomas, una palabra común no vale

# --- Escenario sintético completo ---
SINT = "TEXTO SINTÉTICO DE PRUEBA. "
TEXTOS = {
    "https://elpais.com/a": SINT + 'El ministro Juan Pérez afirmó que «la cumbre fue un éxito rotundo» ante la prensa en Bruselas. Murieron 12 personas en los disturbios posteriores, según la policía local.',
    "https://bbc.co.uk/a": SINT + 'Prime minister Ana Smith said the summit "delivered a fragile compromise" on Tuesday evening in Brussels. Police said 12 people died in clashes after the meeting.',
    "https://tass.com/a": SINT + 'Foreign Minister Ivan Petrov said the summit was "a provocation organised by the West" and called the protests legitimate. Officials reported 15 deaths in the unrest.',
    "https://aljazeera.com/a": SINT + 'Analysts told Al Jazeera that the summit "changed little for ordinary people" across the region. Protesters gathered in the capital for a second day.',
    "https://elmundo.es/b": SINT + 'El Gobierno aprobó el plan de vivienda en el Consejo de Ministros de este martes con el voto en contra de la oposición.',
    "https://dw.com/b": SINT + 'The Spanish government approved the housing plan on Tuesday, according to an official statement released in Madrid.',
}
ini, fin = archivo.limites("2026-W43")
def hora(d, h):
    return (ini + timedelta(days=d, hours=h)).astimezone(U).isoformat()
def n(id_, fuente, titulo, url, h, muro=False):
    f = next(x for x in fuentes if x["id"] == fuente)
    return {"id": id_, "fuente": fuente, "medio": f["nombre"], "zona": f["zona"], "titulo": titulo, "enlace": url, "hora": h, "visto": h, "muro": muro}
NOTICIAS = [
    n("a1", "el-pais", "Cumbre en Bruselas termina con acuerdo", "https://elpais.com/a", hora(1, 10)),
    n("a1b", "el-pais", "Cumbre en Bruselas: última hora", "https://elpais.com/a2", hora(1, 8)),   # mismo medio, mismo suceso: cuenta una vez
    n("a2", "bbc-news", "Brussels summit ends in compromise", "https://bbc.co.uk/a", hora(1, 11)),
    n("a3", "tass", "Brussels summit a provocation, says Petrov", "https://tass.com/a", hora(1, 14)),
    n("a4", "al-jazeera", "Brussels summit changes little", "https://aljazeera.com/a", hora(2, 1)),
    n("a5", "haaretz", "Brussels summit protests", "https://haaretz.com/a", hora(1, 12), muro=True),
    n("b1", "el-mundo", "El Gobierno aprueba el plan de vivienda", "https://elmundo.es/b", hora(2, 9)),
    n("b2", "dw", "Spain approves housing plan", "https://dw.com/b", hora(2, 10)),
    n("c1", "abc", "Polémica local en Madrid", "https://abc.es/c", hora(3, 9)),
    n("c2", "rtve", "Polémica local en Madrid continúa", "https://rtve.es/c", hora(3, 10)),
    n("x0", "npr", "Something unrelated", "https://npr.org/x", hora(0, 3)),
    n("x9", "npr", "Another unrelated story", "https://npr.org/y", hora(5, 3)),   # NPR tiene titulares antes y después: su silencio es observable
    n("fuera", "dw", "Artículo de la semana anterior", "https://dw.com/old", (ini - timedelta(hours=2)).astimezone(U).isoformat()),
]

def vectorizar(titulos):  # embeddings falsos: mismo suceso = mismo vector
    clave = lambda t: 0 if re.search(r"Brussels|Bruselas", t) else 1 if re.search(r"vivienda|housing", t) else 2 if "Madrid" in t else 3
    v = np.zeros((len(titulos), 5), dtype=np.float32)
    for i, t in enumerate(titulos):
        v[i, clave(t)] = 1
        if clave(t) == 3:
            v[i, 4] = i  # cada titular suelto, distinto
    return v / np.linalg.norm(v, axis=1, keepdims=True)

class LectorFalso:
    def __init__(self): self.pedidas = []
    def permitido(self, url): return "aljazeera" not in url        # Al Jazeera: robots.txt lo prohíbe en esta prueba
    def descargar(self, url):
        self.pedidas.append(url)
        if "haaretz" in url:
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        ld = ('{"@type":"NewsArticle","isAccessibleForFree":false,"hasPart":{"isAccessibleForFree":false,"cssSelector":".x"}}' if "dw.com" in url
              else '{"@type":"NewsArticle","isAccessibleForFree":%s}' % ("false" if "bbc" in url else "true"))  # BBC: marca genérica, no cuenta como pago
        html = f'<html lang="x"><script type="application/ld+json">{ld}</script><nav><p>Menú</p></nav><article><p>{TEXTOS[url]}</p></article></html>'
        return 200, url, html.encode(), False

def respuestas(texto):
    """Respuesta simulada del modelo para cada artículo: incluye a propósito una cita inventada y otra de otro artículo."""
    if "elpais" in texto or "Juan Pérez" in texto:
        return {"evidencias": [{"ref": "e1", "cita": "la cumbre fue un éxito rotundo", "hablante_tipo": "entrevistado", "hablante": "Juan Pérez"},
                               {"ref": "e2", "cita": "Murieron 12 personas en los disturbios posteriores", "hablante_tipo": "periodista"},
                               {"ref": "e3", "cita": "a provocation organised by the West", "hablante_tipo": "entrevistado", "hablante": "Ivan Petrov"}],  # de TASS
                "encuadre": [{"texto": "Presenta la cumbre como un éxito del Gobierno", "evidencias": ["e1"]}, {"texto": "Habla de provocación", "evidencias": ["e3"]}],
                "hechos": [{"texto": "Murieron 12 personas", "claves": ["12"], "evidencias": ["e2"]}],
                "cifras": [{"tema": "muertos", "valor": "12", "evidencias": ["e2"]}]}
    if "Ana Smith" in texto:
        return {"evidencias": [{"ref": "e1", "cita": "delivered a fragile compromise", "hablante_tipo": "entrevistado", "hablante": "Ana Smith", "traduccion_es": "logró un compromiso frágil"},
                               {"ref": "e2", "cita": "Police said 12 people died in clashes", "hablante_tipo": "fuente_citada", "hablante": "Police", "traduccion_es": "La policía dijo que 12 personas murieron"}],
                "encuadre": [{"texto": "Destaca la fragilidad del acuerdo", "evidencias": ["e1"]}],
                "fuentes_citadas": [{"fuente": "Policía", "evidencias": ["e2"]}],
                "cifras": [{"tema": "muertos", "valor": "12", "evidencias": ["e2"]}]}
    if "Ivan Petrov" in texto:
        return {"evidencias": [{"ref": "e1", "cita": "a provocation organised by the West", "hablante_tipo": "entrevistado", "hablante": "Ivan Petrov", "traduccion_es": "una provocación organizada por Occidente"},
                               {"ref": "e2", "cita": "Officials reported 15 deaths in the unrest", "hablante_tipo": "fuente_citada", "hablante": None, "traduccion_es": "Las autoridades informaron de 15 muertes"},
                               {"ref": "e3", "cita": "the summit was a total disaster", "hablante_tipo": "periodista"}],  # inventada
                "encuadre": [{"texto": "Presenta la cumbre como una provocación occidental", "evidencias": ["e1"]}],
                "lenguaje": [{"termino": "provocation", "alternativa_descriptiva": "reunión criticada por Rusia", "evidencias": ["e1"]}],
                "cifras": [{"tema": "muertos", "valor": "15", "evidencias": ["e2"]}]}
    return {"evidencias": [], "encuadre": []}

class GroqFalso:
    def __init__(self, fallos=()):
        self.peticiones, self.fallos = 0, list(fallos)
    def __call__(self, metodo, url, cab, cuerpo, timeout):
        assert "Bearer clave-de-prueba" == cab["Authorization"]
        if metodo == "GET":
            return 200, {}, json.dumps({"data": [{"id": conf["ia"]["modelo"]}]}).encode()
        self.peticiones += 1
        if self.fallos:
            f = self.fallos.pop(0)
            if f == 429:
                return 429, {"retry-after": "1"}, b"{}"
            if f == "basura":
                return 200, {}, json.dumps({"choices": [{"message": {"content": "esto no es JSON"}}], "usage": {"total_tokens": 50}}).encode()
        msgs = json.loads(cuerpo)["messages"]
        u = msgs[1]["content"]  # el mensaje original; tras una reparación hay más mensajes detrás
        if "Material validado" in msgs[1]["content"]:
            mat = json.loads(msgs[1]["content"].split("(JSON):\n", 1)[1].split("\nDevuelve:")[0])
            ev = {e["cita"]: e["id"] for e in mat["evidencias"]}
            hechos = [h["id"] for h in mat["hechos"]]
            arts = {a["medio"]: a["id"] for a in mat["articulos"]}
            if "TASS" not in arts:  # otro suceso: sin nada que destacar
                out = {"titulo": "Plan de vivienda en España", "resumen": [], "llamativo": [], "omisiones": [], "cifras": []}
                return 200, {}, json.dumps({"choices": [{"message": {"content": json.dumps(out)}}], "usage": {"total_tokens": 300}}).encode()
            out = {"titulo": "Cumbre de Bruselas y disturbios posteriores",
                   "resumen": [{"texto": "Se celebró una cumbre en Bruselas seguida de disturbios.", "evidencias": [ev["Murieron 12 personas en los disturbios posteriores"]]},
                               {"texto": "Frase sin evidencia", "evidencias": ["e-inventada-1"]}],
                   "llamativo": [{"texto": "TASS la llama provocación; El País, éxito.", "evidencias": [ev["a provocation organised by the West"], ev["la cumbre fue un éxito rotundo"]]}],
                   "omisiones": [{"hecho": hechos[0], "articulos_sin_hecho": [arts["TASS"], arts["BBC News"]]}],
                   "cifras": [{"tema": "muertos", "evidencias": [ev["Murieron 12 personas en los disturbios posteriores"], ev["Officials reported 15 deaths in the unrest"]]}]}
        else:
            texto = u.split("<articulo>\n", 1)[1].split("\n</articulo>")[0]
            out = respuestas(texto)
        return 200, {"x-ratelimit-remaining-tokens": "5000"}, json.dumps({"choices": [{"message": {"content": json.dumps(out, ensure_ascii=False)}}], "usage": {"total_tokens": 900}}).encode()

def preparar_archivo(d, noticias=NOTICIAS, horas=None):
    datos = {"actualizado": (fin - timedelta(hours=1)).astimezone(U).isoformat(), "noticias": noticias, "fuentes_estado": {}}
    archivo.capturar(datos, d)
    ej = Path(d) / "capturas" / "2026-W43.ejecuciones.json"
    todas = [(ini + timedelta(hours=h)).astimezone(U).strftime("%Y-%m-%dT%H") for h in range(169)]
    j = json.loads(ej.read_text())
    j["horas"] = horas if horas is not None else todas
    j["fuentes"] = {f["id"]: {"ok": todas, "error": {}} for f in fuentes if f["id"] != "rt"}
    j["fuentes"]["rt"] = {"ok": [], "error": {todas[5]: "Connection refused"}}
    ej.write_text(json.dumps(j))

import os
os.environ[conf["ia"]["secreto"]] = "clave-de-prueba"
lector_falso = LectorFalso()
lector = lambda a: extraer(lector_falso, a["enlace"], muro=a.get("muro"), min_completo=LIM["min_caracteres_completo"])

with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as trabajo:
    preparar_archivo(d)
    # 1) Domingo 09:00: provisional, con corte visible, sin datos posteriores al corte
    domingo = datetime(2026, 10, 25, 9, 0, tzinfo=M).astimezone(U)
    groq = GroqFalso()
    cli = Cliente(conf["ia"], trabajo, "t1", transporte=groq, dormir=lambda s: None)
    inf = semana.generar("2026-W43", domingo, d, conf, fuentes, {}, lector=lector, cliente=cli, vectorizar=vectorizar)
    semana.validar_informe(inf)
    assert inf["status"] == "provisional" and inf["cutoff_at"] == domingo.isoformat() and inf["analysis_note"] is None, inf["analysis_note"]
    malo = copy.deepcopy(inf); malo["status"] = "cerrado"
    try:
        semana.validar_informe(malo); raise AssertionError("un provisional no puede validarse como cerrado")
    except ValueError:
        pass
    # 2) Selección: suceso de Bruselas con 5 medios (El País una sola vez) y 5 países; vivienda con 2; Madrid (solo ES) fuera
    evs = {e["title"]: e for e in inf["events"]}
    assert len(inf["events"]) == 2, list(evs)
    bru = inf["events"][0]
    assert bru["source_ids"] == sorted(["el-pais", "bbc-news", "tass", "al-jazeera", "haaretz"]) and bru["country_ids"] == ["ES", "GB", "IL", "QA", "RU"]
    assert [a["id"] for a in bru["articles"] if a["source_id"] == "el-pais"] == ["a1"]                     # el más reciente del medio
    assert "fuera" not in json.dumps(inf) and inf["selection"]["reason_fewer"]                             # nada de otras semanas; se explica por qué hay menos de 5
    # 3) Acceso: robots, 403 sin sortear, pago declarado
    acc = {a["source_id"]: a["access_status"] for a in bru["articles"]}
    assert acc == {"el-pais": "completo", "bbc-news": "completo", "tass": "completo", "al-jazeera": "solo_titular", "haaretz": "inaccesible"}, acc
    assert inf["events"][1]["matrix"]["dw"] == "parcial"                                                    # DW declara pago en la prueba
    assert bru["matrix"]["haaretz"] == "parcial" and bru["matrix"]["npr"] == "sin_coincidencias" and bru["matrix"]["rt"] == "no_evaluable"
    assert not any(TEXTOS["https://elpais.com/a"] in json.dumps(inf, ensure_ascii=False) for _ in [0])     # el cuerpo no se publica
    # 4) Evidencias: la cita inventada y la de otro artículo no pasan; las afirmaciones apuntan a citas reales
    citas = {e["exact_quote"]: e for e in bru["evidence"]}
    assert "the summit was a total disaster" not in citas
    assert all(e["article_id"] == "a3" for q, e in citas.items() if q == "a provocation organised by the West")
    pais_comp = next(c for c in bru["comparisons"] if c["source_id"] == "el-pais")
    assert [c["text"] for c in pais_comp["framing_claims"]] == ["Presenta la cumbre como un éxito del Gobierno"]
    assert len(bru["summary_claims"]) == 1 and bru["title"] == "Cumbre de Bruselas y disturbios posteriores"
    # 5) Omisión: TASS (completo, posterior, sin «12») sí; la BBC lo menciona: no
    assert len(bru["omissions"]) == 1 and [a for a in bru["omissions"][0]["compared_article_ids"]] == ["a3"]
    assert bru["figure_differences"][0]["topic"] == "muertos" and {v["value"] for v in bru["figure_differences"][0]["values"]} == {"12", "15"}
    assert any("h de diferencia" in t for t in bru["temporal_notes"])
    assert bru["analysis_status"] == "completo"
    # 6) Silencios: solo ausencias observadas de medios internacionales con ventana
    assert any("NPR" in s["description"] for s in inf["silences"]) and not any("ABC" in s["description"] for s in inf["silences"])
    # 7) Repetir la misma entrada: todo sale de la caché, ni una petición más
    antes = groq.peticiones
    cli2 = Cliente(conf["ia"], trabajo, "t2", transporte=groq, dormir=lambda s: None)
    inf2 = semana.generar("2026-W43", domingo, d, conf, fuentes, {}, lector=lector, cliente=cli2, vectorizar=vectorizar)
    assert groq.peticiones == antes and cli2.de_cache > 0 and inf2["events"] == inf["events"]
    # 8) Guardar: JSON + Markdown + índice; repetir no duplica
    semana.guardar(d, inf); semana.guardar(d, inf)
    idx = semana.leer_indice(d)
    assert [i["week_id"] for i in idx["informes"]] == ["2026-W43"] and idx["informes"][0]["articulos"]["a3"] == bru["id"]
    md = (Path(d) / "semana" / "2026-W43.md").read_text()
    assert md.startswith("# Talaia · Semana 2026-W43") and "provisional" in md and "a provocation organised by the West" in md
    assert "Traducción: una provocación organizada por Occidente" in md

    # 9) Calendario automático (hora de Madrid)
    t = lambda y, mo, da, h, mi: datetime(y, mo, da, h, mi, tzinfo=M).astimezone(U)
    tar = lambda ahora: semana.tareas_auto(ahora, d, conf, fuentes)
    assert tar(t(2026, 10, 25, 8, 59)) == [("2026-W42", "cierre")]           # W42 tiene capturas (el artículo «fuera») y no está cerrada
    (Path(d) / "capturas" / "2026-W42.jsonl").unlink()                         # el resto, solo con W43
    assert tar(t(2026, 10, 25, 8, 59)) == []
    assert tar(t(2026, 10, 25, 10, 0)) == []                                     # ya hay provisional de hoy 09:00
    assert tar(t(2026, 10, 26, 0, 29)) == []                                     # lunes antes de las 00:30: aún no se cierra
    assert tar(t(2026, 10, 26, 0, 30)) == [("2026-W43", "cierre")]
    lunes = t(2026, 10, 26, 0, 30)
    cerrado = semana.generar("2026-W43", lunes, d, conf, fuentes, {}, lector=lector, cliente=Cliente(conf["ia"], trabajo, "t3", transporte=groq, dormir=lambda s: None), vectorizar=vectorizar)
    assert cerrado["status"] == "cerrado" and cerrado["cutoff_at"] == fin.astimezone(U).isoformat()
    semana.guardar(d, cerrado)
    assert tar(t(2026, 10, 26, 1, 30)) == []                                     # idempotente: segunda franja del cambio de hora, nada
    # Datos tardíos de la semana cerrada: se actualiza
    archivo.capturar({"actualizado": lunes.isoformat(), "noticias": [n("tarde", "npr", "Late story", "https://npr.org/late", hora(6, 20))]}, d)
    assert tar(t(2026, 10, 26, 9, 0)) == [("2026-W43", "datos tardíos")]

with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as trabajo:
    preparar_archivo(d, horas=[])
    lunes = datetime(2026, 10, 26, 1, 0, tzinfo=M).astimezone(U)
    # 10) Sin clave: Directo no se entera; el informe dice que no hay IA y no se llama "completo"
    del os.environ[conf["ia"]["secreto"]]
    inf = semana.generar("2026-W43", lunes, d, conf, fuentes, {}, lector=lector, cliente=Cliente(conf["ia"], trabajo, "t4", transporte=GroqFalso(), dormir=lambda s: None), vectorizar=vectorizar)
    semana.validar_informe(inf)
    assert inf["analysis_status"] == "sin_ia" and "falta la clave" in inf["analysis_note"] and inf["model_id"] is None
    assert inf["status"] == "parcial" and any(w["code"] == "capturas_incompletas" for w in inf["coverage_warnings"])  # sin capturas registradas: cierre parcial
    os.environ[conf["ia"]["secreto"]] = "clave-de-prueba"
    # 11) 429 con espera corta y JSON basura: reintentos acotados; luego bien
    groq = GroqFalso(fallos=[429, "basura"])
    inf = semana.generar("2026-W43", lunes, d, conf, fuentes, {}, lector=lector, cliente=Cliente(conf["ia"], trabajo, "t5", transporte=groq, dormir=lambda s: None), vectorizar=vectorizar)
    assert inf["events"][0]["analysis_status"] == "completo", inf["analysis_note"]
    # 12) Presupuesto de 24 h: se para antes del límite y lo pendiente queda marcado
    c2 = copy.deepcopy(conf); c2["ia"]["limites"]["tokens_24h"] = 4000
    with tempfile.TemporaryDirectory() as t2:
        cli = Cliente(c2["ia"], t2, "t6", transporte=GroqFalso(), dormir=lambda s: None)
        inf = semana.generar("2026-W43", lunes, d, c2, fuentes, {}, lector=lector, cliente=cli, vectorizar=vectorizar)
        semana.validar_informe(inf)
        assert "tope de tokens de 24 h" in inf["analysis_note"] and inf["analysis_status"] in ("parcial", "sin_ia") and cli.uso.en_24h(datetime.now(U)) <= 4000
    # 13) Sin cuota (429 largo): no hay respaldo de pago, se para
    with tempfile.TemporaryDirectory() as t3:
        class Agotado(GroqFalso):
            def __call__(self, m, u, c, b, t):
                return (200, {}, json.dumps({"data": [{"id": conf["ia"]["modelo"]}]}).encode()) if m == "GET" else (429, {"retry-after": "3600"}, b"{}")
        inf = semana.generar("2026-W43", lunes, d, conf, fuentes, {}, lector=lector, cliente=Cliente(conf["ia"], t3, "t7", transporte=Agotado(), dormir=lambda s: None), vectorizar=vectorizar)
        assert "cuota de Groq agotada" in inf["analysis_note"] and inf["analysis_status"] == "sin_ia"
    # 14) Modelo no disponible para la cuenta
    with tempfile.TemporaryDirectory() as t4:
        c3 = copy.deepcopy(conf); c3["ia"]["modelo"] = "modelo-retirado"
        inf = semana.generar("2026-W43", lunes, d, c3, fuentes, {}, lector=lector, cliente=Cliente(c3["ia"], t4, "t8", transporte=GroqFalso(), dormir=lambda s: None), vectorizar=vectorizar)
        assert "no está disponible" in inf["analysis_note"]
    # 15) Semana sin datos: no disponible, válida
    vacio = semana.generar("2026-W40", lunes, d, conf, fuentes, {"no_llm": True}, vectorizar=vectorizar)
    semana.validar_informe(vacio)
    assert vacio["status"] == "no_disponible"
    # 16) Fallo de generación: se conserva el último informe válido y el error va aparte
    semana.guardar(d, inf)
    semana.anotar_error(d, "2026-W43", "RuntimeError: prueba", lunes, conf)
    e = semana.leer_indice(d)["informes"][0]
    assert e["ultimo_error"]["message"] == "RuntimeError: prueba" and (Path(d) / "semana" / "2026-W43.json").exists()

    # 17) Sitio: la recogida conserva semana/ y la semana conserva Directo, en cualquier orden
    with tempfile.TemporaryDirectory() as s:
        datos = {"actualizado": "2026-10-26T10:00:00+00:00", "fuentes_caidas": [],
                 "noticias": [n("hoy", "bbc-news", "Hoy", "https://bbc.co.uk/hoy", "2026-10-26T09:00:00+00:00"),
                              n("ayer", "bbc-news", "Viejo", "https://bbc.co.uk/viejo", "2026-10-25T08:00:00+00:00"),
                              n("malo", "bbc-news", "Enlace raro", "javascript:alert(1)", "2026-10-26T09:00:00+00:00"),
                              {**n("futuro", "bbc-news", "Futuro", "https://bbc.co.uk/f", "2026-10-26T12:00:00+00:00")}]}
        Path(s, "datos.json").write_text(json.dumps(datos))
        sitio = montar_sitio.montar(Path(s, "datos.json"), d, Path(s, "_site"))
        d24 = json.loads((sitio / "ultimas24h.json").read_text())
        assert [x["id"] for x in d24["noticias"]] == ["hoy"]                    # 24 h, sin enlaces raros ni fechas futuras
        assert all(set(x) <= set(montar_sitio.CAMPOS_DIRECTO) for x in d24["noticias"])  # sin cuerpos ni entradillas
        assert (sitio / "semana" / "2026-W43.json").exists() and (sitio / "semana" / "2026-W43.md").exists()
        assert d24["comparar"]["a3"].startswith("2026-W43/ev-")
        archivo.capturar(datos, d)                                               # recogida después de la semanal
        semana.guardar(d, inf)                                                   # semanal después de la recogida
        sitio = montar_sitio.montar(Path(s, "datos.json"), d, Path(s, "_site"))
        assert (sitio / "semana" / "2026-W43.json").exists() and (sitio / "ultimas24h.json").exists() and (sitio / "app.js").exists()
        # semana/ corrupta: no se publica
        (Path(d) / "semana" / "2026-W43.json").write_text("{roto")
        try:
            montar_sitio.montar(Path(s, "datos.json"), d, Path(s, "_site")); raise AssertionError("no debía publicar")
        except ValueError:
            assert (Path(s) / "_site" / "semana" / "2026-W43.json").read_text().startswith("{")  # el sitio anterior sigue intacto
print("OK")
