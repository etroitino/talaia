"""Extracción legítima del texto de un artículo, para el análisis semanal.

Solo se lee lo que la página sirve a cualquier visitante: sin cookies, sin cuentas, sin sortear muros,
CAPTCHA ni controles de acceso, y respetando robots.txt. El texto vive en memoria durante la ejecución:
no se guarda en el repositorio, ni en logs, ni en artifacts. Lo que se guarda es su hash y su alcance.

Estados de acceso:
  completo      texto del cuerpo, sin marca de pago y con longitud suficiente
  parcial       el medio declara contenido de pago, o el texto es corto o se recortó
  solo_titular  no se pudo leer el cuerpo (robots.txt lo prohíbe o no hay texto)
  inaccesible   error HTTP, CAPTCHA o control de acceso (no se reintenta ni se sortea)
"""
import hashlib
import ipaddress
import json
import re
import socket
import time
import unicodedata
import urllib.error
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit

from recoger import tiene_muro


class Bloqueado(Exception):
    """URL no permitida: esquema, credenciales, puerto o destino no público."""


def validar_url(url):
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise Bloqueado(f"esquema o host no permitido: {url[:80]}")
    if p.username or p.password:
        raise Bloqueado("URL con credenciales")
    if p.port not in (None, 80, 443):
        raise Bloqueado(f"puerto no permitido: {p.port}")
    try:
        direcciones = {i[4][0] for i in socket.getaddrinfo(p.hostname, None)}
    except socket.gaierror as e:
        raise Bloqueado(f"no se resuelve {p.hostname}: {e}")
    for d in direcciones:
        ip = ipaddress.ip_address(d.split("%")[0])
        if not ip.is_global or ip.is_multicast:
            raise Bloqueado(f"destino no público: {p.hostname} -> {ip}")
    # ponytail: se comprueba antes de conectar; un DNS que cambie entre comprobación y conexión
    # (rebinding) no se cubre. Suficiente para leer medios conocidos de fuentes.yaml.
    return url


class _Redirecciones(urllib.request.HTTPRedirectHandler):
    max_redirections = 5

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validar_url(newurl)  # cada salto se valida igual que el primero
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Lector:
    """Descargas con límites de tiempo, tamaño, redirecciones, reintentos y ritmo por dominio."""

    def __init__(self, conf):
        self.conf = conf
        r = _Redirecciones()
        r.max_redirections = conf["max_redirecciones"]
        self.opener = urllib.request.build_opener(r)  # sin cookies: no hay HTTPCookieProcessor
        self.ultimo = {}
        self.robots = {}

    def _esperar(self, host):
        falta = self.ultimo.get(host, 0) + self.conf["intervalo_dominio_s"] - time.monotonic()
        if falta > 0:
            time.sleep(falta)
        self.ultimo[host] = time.monotonic()

    def descargar(self, url):
        """Devuelve (estado_http, url_final, bytes, recortado). Lanza Bloqueado o urllib.error.*"""
        validar_url(url)
        intentos = self.conf["reintentos"] + 1
        for i in range(intentos):
            self._esperar(urlsplit(url).hostname)
            req = urllib.request.Request(url, headers={"User-Agent": self.conf["user_agent"], "Accept": "text/html,application/xhtml+xml"})
            try:
                with self.opener.open(req, timeout=self.conf["timeout_s"]) as r:
                    cuerpo = r.read(self.conf["max_bytes"] + 1)
                    return r.status, r.geturl(), cuerpo[: self.conf["max_bytes"]], len(cuerpo) > self.conf["max_bytes"]
            except urllib.error.HTTPError as e:
                if e.code < 500 or i == intentos - 1:
                    raise
            except (urllib.error.URLError, TimeoutError, socket.timeout):
                if i == intentos - 1:
                    raise
            time.sleep(2 * (i + 1))

    def permitido(self, url):
        p = urlsplit(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                _, _, cuerpo, _ = self.descargar(base + "/robots.txt")
                rp.parse(cuerpo.decode("utf-8", "replace").splitlines())
            except urllib.error.HTTPError as e:
                rp.disallow_all = e.code in (401, 403)  # misma regla que urllib.robotparser
                rp.allow_all = not rp.disallow_all
            except Exception:
                rp.allow_all = True
            self.robots[base] = rp
        return self.robots[base].can_fetch(self.conf["user_agent"], url)


# --- Texto canónico ---

INVISIBLES = dict.fromkeys(map(ord, "­​‌‍⁠﻿"))


def canon_texto(s):
    """Representación reproducible del texto: NFC, sin caracteres invisibles y con los espacios colapsados."""
    return " ".join(unicodedata.normalize("NFC", s).translate(INVISIBLES).split())


def hash_texto(texto):
    return "sha256:" + hashlib.sha256(texto.encode()).hexdigest()


# --- HTML ---

class _Pagina(HTMLParser):
    SALTAR = {"script", "style", "noscript", "nav", "footer", "aside", "figcaption", "form", "header", "button", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ld, self.parrafos, self.lang = [], [], None
        self.en_ld = False
        self.saltar = 0
        self.dentro = {"article": 0, "main": 0}
        self.p = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        if tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self.en_ld = True
            self.ld.append("")
            return
        if tag in self.dentro:
            self.dentro[tag] += 1
        if tag in self.SALTAR:
            self.saltar += 1
        if tag == "p" and not self.saltar:
            self.p = []

    def handle_endtag(self, tag):
        if tag == "script" and self.en_ld:
            self.en_ld = False
            return
        if tag in self.dentro and self.dentro[tag]:
            self.dentro[tag] -= 1
        if tag in self.SALTAR and self.saltar:
            self.saltar -= 1
        if tag == "p" and self.p is not None:
            t = " ".join("".join(self.p).split())
            if t:
                self.parrafos.append((t, self.dentro["article"] > 0, self.dentro["main"] > 0))
            self.p = None

    def handle_data(self, data):
        if self.en_ld:
            self.ld[-1] += data
        elif self.p is not None and not self.saltar:
            self.p.append(data)


def _objetos_ld(textos):
    for t in textos:
        try:
            d = json.loads(t)
        except ValueError:
            continue
        pila = [d]
        while pila:
            o = pila.pop()
            if isinstance(o, list):
                pila += o
            elif isinstance(o, dict):
                yield o
                pila += [v for k, v in o.items() if k in ("@graph", "mainEntity", "hasPart")]


def _tipos(o):
    t = o.get("@type") or []
    return {t} if isinstance(t, str) else set(t)


def genero(objetos):
    """Género solo si el medio lo declara en sus metadatos; si no, 'no_verificado'."""
    for o in objetos:
        tipos = _tipos(o)
        if not any("Article" in t for t in tipos):
            continue
        seccion = " ".join(o.get("articleSection") if isinstance(o.get("articleSection"), list) else [str(o.get("articleSection") or "")])
        if "OpinionNewsArticle" in tipos or re.search(r"opini|tribuna|column", seccion, re.I):
            return "opinion", f"declarado: {'OpinionNewsArticle' if 'OpinionNewsArticle' in tipos else 'sección ' + seccion}"
        if "AnalysisNewsArticle" in tipos or re.search(r"an[aá]lisis|analysis", seccion, re.I):
            return "analisis", "declarado: " + ("AnalysisNewsArticle" if "AnalysisNewsArticle" in tipos else "sección " + seccion)
        if re.search(r"entrevista|interview", seccion, re.I):
            return "entrevista", "declarado: sección " + seccion
        if tipos & {"NewsArticle", "ReportageNewsArticle"}:
            return "noticia", "declarado: " + "/".join(sorted(tipos & {"NewsArticle", "ReportageNewsArticle"}))
    return "no_verificado", None


CAPTCHA = re.compile(r"captcha|cf-challenge|challenge-platform|are you a robot|verify you are human", re.I)


def extraer(lector, url, muro=None, min_completo=1200, ahora=None):
    """Lee un artículo y devuelve sus metadatos de acceso. El texto se devuelve aparte (clave 'texto')
    y nunca debe guardarse ni publicarse."""
    ahora = ahora or datetime.now(timezone.utc).replace(microsecond=0)
    r = {"url": url, "final_url": url, "retrieved_at": ahora.isoformat(timespec="seconds"), "texto": "",
         "access_status": "solo_titular", "access_reason": None, "extraction_scope": "ninguno",
         "genre": "no_verificado", "genre_basis": None, "text_hash": None, "text_chars": 0, "lang": None}
    try:
        if not lector.permitido(url):
            r["access_reason"] = "robots.txt no permite leer esta página"
            return r
        _, final, cuerpo, recortado = lector.descargar(url)
    except Bloqueado as e:
        return {**r, "access_status": "inaccesible", "access_reason": f"URL no permitida ({e})"}
    except urllib.error.HTTPError as e:
        motivo = "control de acceso" if e.code in (401, 402, 403, 429, 451) else "error del servidor"
        return {**r, "access_status": "inaccesible", "access_reason": f"HTTP {e.code} ({motivo}; no se intenta sortear)"}
    except Exception as e:
        return {**r, "access_status": "inaccesible", "access_reason": f"no se pudo descargar ({type(e).__name__})"}
    r["final_url"] = final
    html = cuerpo.decode("utf-8", "replace")
    if CAPTCHA.search(html[:20000]) and len(html) < 60000:
        return {**r, "access_status": "inaccesible", "access_reason": "la página pide verificación (CAPTCHA); no se intenta sortear"}
    pag = _Pagina()
    pag.feed(html)
    objetos = list(_objetos_ld(pag.ld))
    r["genre"], r["genre_basis"] = genero(objetos)
    r["lang"] = pag.lang
    # mismo criterio que la etiqueta premium: marca del artículo o sección oculta declarada (no la marca genérica)
    de_pago = muro is True or tiene_muro(html, "ld")
    cuerpo_ld = next((o["articleBody"] for o in objetos if isinstance(o.get("articleBody"), str) and len(o["articleBody"]) > 200), None)
    if cuerpo_ld and not de_pago:
        texto, origen = cuerpo_ld, "articleBody"
    else:
        ps = [t for t, art, _ in pag.parrafos if art] or [t for t, _, m in pag.parrafos if m] or [t for t, _, _ in pag.parrafos if len(t) >= 60]
        texto, origen = "\n".join(ps), "párrafos visibles"
    texto = canon_texto(texto)
    r.update(texto=texto, text_hash=hash_texto(texto) if texto else None, text_chars=len(texto))
    if not texto:
        r["access_reason"] = "no se encontró texto del cuerpo"
    elif de_pago:
        r.update(access_status="parcial", extraction_scope="cuerpo_parcial", access_reason="el medio declara contenido de pago: solo la parte visible")
    elif recortado:
        r.update(access_status="parcial", extraction_scope="cuerpo_parcial", access_reason="página más grande que el límite de descarga")
    elif len(texto) < min_completo:
        r.update(access_status="parcial", extraction_scope="cuerpo_parcial", access_reason=f"texto corto ({len(texto)} caracteres, {origen})")
    else:
        r.update(access_status="completo", extraction_scope="cuerpo_completo", access_reason=origen)
    return r
