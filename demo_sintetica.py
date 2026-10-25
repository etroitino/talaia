"""Escenario SINTÉTICO para pruebas y demostraciones: medios reales de fuentes.yaml, pero textos, hechos y
citas inventados. Nada de esto es una noticia real ni un fixture «verificado»: todo lo que se genera con él
se marca como sintético. Lo usan test_semana.py y test_navegador.py."""
import copy
import json
import re
import urllib.error
from datetime import timedelta, timezone
from pathlib import Path

import numpy as np

import archivo
import semana

U = timezone.utc
conf, fuentes = semana.cargar_config()
conf = copy.deepcopy(conf)
conf["semana"]["min_caracteres_completo"] = 80
conf["ia"]["pausa_minima_s"] = 0
LIM = conf["semana"]
TODAS = semana.yaml.safe_load(Path("fuentes.yaml").read_text(encoding="utf-8"))["fuentes"]  # con verificadores

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
    f = next(x for x in TODAS if x["id"] == fuente)
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
            if f == "cortado":
                return 400, {}, json.dumps({"error": {"message": "Failed to generate JSON", "code": "json_validate_failed", "failed_generation": '{"evidencias": ['}}).encode()
            if f == "malformada":
                return 400, {}, json.dumps({"error": {"message": "parámetro desconocido", "type": "invalid_request_error"}}).encode()
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


def informe_demo(carpeta, trabajo):
    """Informe sintético de 2026-W43 con análisis simulado, marcado synthetic=True, guardado en `carpeta`."""
    import os
    from datetime import datetime
    from extraer import extraer
    from ia import Cliente
    os.environ.setdefault(conf["ia"]["secreto"], "clave-de-prueba")
    preparar_archivo(carpeta)
    lf = LectorFalso()
    lector = lambda a: extraer(lf, a["enlace"], muro=a.get("muro"), min_completo=LIM["min_caracteres_completo"])
    cli = Cliente(conf["ia"], trabajo, "demo", transporte=GroqFalso(), dormir=lambda s: None)
    inf = semana.generar("2026-W43", datetime(2026, 10, 26, 1, 0, tzinfo=U), carpeta, conf, fuentes, {}, lector=lector, cliente=cli, vectorizar=vectorizar)
    inf["synthetic"] = True
    inf["model_id"] = "simulado (sin IA real)"
    semana.guardar(carpeta, inf)
    return inf


def datos_directo(ahora, por_zona=70):
    """datos.json sintético de las últimas horas: ráfagas, grupos entre zonas, premium con y sin alternativa."""
    noticias = []
    zonas = {"girona": ["diari-de-girona", "el-punt-avui-girona"], "cataluna": ["la-vanguardia", "ara", "el-nacional"],
             "espana": ["el-pais", "el-mundo", "eldiario-es", "abc"], "europa": ["euronews", "politico-europe"],
             "mundo": ["bbc-news", "the-guardian", "france-24"], "miradas": ["tass", "al-jazeera", "dw"], "verificadores": ["maldita", "newtral"]}
    k = 0
    for zona, ids in zonas.items():
        for i in range(por_zona if zona not in ("verificadores", "miradas") else 12):
            fid = ids[0] if i < 15 else ids[i % len(ids)]  # ráfaga inicial del primer medio
            k += 1
            h = (ahora - timedelta(minutes=7 * i + 3)).isoformat(timespec="seconds")
            noticias.append({**n(f"s{k:04d}", fid, f"[SINTÉTICO] {zona} titular {i} número {k}", f"https://example.org/{zona}/{i}", h),
                             "muro": fid == "el-pais" and i % 2 == 0})
    # Un mismo hecho en varias zonas y medios; su representante en España es premium y hay alternativas abiertas
    grupo = [("el-pais", "espana", True), ("eldiario-es", "espana", False), ("bbc-news", "mundo", False), ("la-vanguardia", "cataluna", False), ("tass", "miradas", False)]
    for j, (fid, zona, muro) in enumerate(grupo):
        noticias.append({**n(f"g{j}", fid, f"[SINTÉTICO] Hecho compartido contado por {fid}", f"https://example.org/g/{j}", (ahora - timedelta(minutes=1 + j)).isoformat(timespec="seconds")),
                         "muro": muro, "grupo": "grupo-demo"})
    noticias.append({**n("a3", "tass", "[SINTÉTICO] Artículo enlazado al informe semanal", "https://tass.com/a", (ahora - timedelta(minutes=2)).isoformat(timespec="seconds")), "grupo": "grupo-semana"})
    noticias.append({**n("a2", "bbc-news", "[SINTÉTICO] Otro medio del mismo hecho semanal", "https://bbc.co.uk/a", (ahora - timedelta(minutes=4)).isoformat(timespec="seconds")), "grupo": "grupo-semana"})
    noticias.sort(key=lambda x: x["hora"], reverse=True)
    return {"actualizado": ahora.isoformat(timespec="seconds"), "fuentes_caidas": [{"medio": "RT", "fuente": "rt", "error": "Connection refused (sintético)"}],
            "fuentes_estado": {}, "excluidas": [], "noticias": noticias}
