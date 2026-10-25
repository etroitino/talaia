"""Cliente de IA para el análisis semanal. Solo Groq (plan gratuito); sin respaldo de pago.

- La clave se lee de la variable de entorno indicada en config.yaml (GitHub Secret). Nunca se escribe.
- Al empezar se comprueba en /models que el modelo configurado existe para la cuenta.
- Presupuesto: estimación previa conservadora (caracteres / caracteres_por_token × margen + respuesta);
  se registra el consumo real que devuelve la API ("usage"). Topes por petición, ejecución y 24 h móviles;
  el registro de 24 h vive en la rama archivo (uso/ia.json) y lo comparten todas las ejecuciones.
- Caché por hash de (modelo, versión de prompt, versión de esquema, tarea y contenido): repetir la misma
  entrada no gasta tokens. La caché guarda solo resultados ya validados (citas breves), nunca textos completos.
- 429, 5xx, timeout y JSON inválido: reintentos acotados; si la cuota se agota, se para y lo pendiente
  queda sin análisis (marcado así en el informe).
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


class SinIA(Exception):
    """No se puede usar la IA (sin clave, modelo no disponible, sin cuota...). El motivo va en el mensaje."""


class PeticionGrande(ValueError):
    """Esta petición no cabe en el tope por petición. Solo afecta a ella: el resto puede seguir."""


def ahora_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _transporte(metodo, url, cabeceras, cuerpo, timeout):
    req = urllib.request.Request(url, data=cuerpo, headers=cabeceras, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


def _error(cuerpo):
    """{"message", "code", "failed_generation"} del error de la API (nunca contiene la clave)."""
    try:
        e = json.loads(cuerpo).get("error") or {}
        return e if isinstance(e, dict) else {"message": str(e)}
    except (ValueError, AttributeError):
        return {"message": cuerpo[:200].decode("utf-8", "replace") if isinstance(cuerpo, bytes) else str(cuerpo)[:200]}


class Uso:
    """Registro compartido de tokens (ventana móvil). Se guarda en uso/ia.json de la rama archivo."""

    def __init__(self, ruta):
        self.ruta = Path(ruta)
        self.registros = json.loads(self.ruta.read_text())["registros"] if self.ruta.exists() else []

    def en_24h(self, ahora):
        desde = (ahora - timedelta(hours=24)).isoformat()
        return sum(r["tokens"] for r in self.registros if r["t"] >= desde)

    def anotar(self, ahora, tokens, ejecucion):
        self.registros.append({"t": ahora.isoformat(), "tokens": int(tokens), "ejecucion": ejecucion})
        desde = (ahora - timedelta(hours=48)).isoformat()
        self.registros = [r for r in self.registros if r["t"] >= desde]
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps({"registros": self.registros}, indent=0))
        tmp.replace(self.ruta)


class Cliente:
    def __init__(self, conf, carpeta_archivo, ejecucion, transporte=_transporte, reloj=ahora_utc, dormir=time.sleep):
        self.conf, self.lim = conf, conf["limites"]
        self.clave = os.environ.get(conf["secreto"])
        self.cache = Path(carpeta_archivo) / "cache_ia"
        self.uso = Uso(Path(carpeta_archivo) / "uso" / "ia.json")
        self.ejecucion = ejecucion
        self.transporte, self.reloj, self.dormir = transporte, reloj, dormir
        self.gastado = self.peticiones = self.de_cache = 0
        self.limites_api = {}
        self.ultima = 0.0

    def _cabeceras(self):
        return {"Authorization": f"Bearer {self.clave}", "Content-Type": "application/json", "User-Agent": "talaia"}

    def comprobar(self):
        if self.conf["proveedor"] != "groq":
            raise SinIA(f"proveedor no admitido: {self.conf['proveedor']}")
        if not self.clave:
            raise SinIA(f"falta la clave ({self.conf['secreto']} no está definida)")
        estado, _, cuerpo = self.transporte("GET", self.conf["url"] + "/models", self._cabeceras(), None, self.conf["timeout_s"])
        if estado != 200:
            raise SinIA(f"no se pudo consultar /models (HTTP {estado})")
        ids = {m.get("id") for m in json.loads(cuerpo).get("data", [])}
        if self.conf["modelo"] not in ids:
            raise SinIA(f"el modelo {self.conf['modelo']} no está disponible para esta cuenta")

    def estimar(self, mensajes):
        caracteres = sum(len(m["content"]) for m in mensajes)
        return int(caracteres / self.conf["caracteres_por_token"] * self.conf["margen_estimacion"]) + self.conf["max_tokens_respuesta"]

    def _reservar(self, estimado):
        if estimado > self.lim["tokens_peticion"]:
            raise PeticionGrande(f"petición estimada en {estimado} tokens, por encima del tope por petición")
        if self.peticiones >= self.lim["peticiones_ejecucion"]:
            raise SinIA("tope de peticiones de esta ejecución alcanzado")
        if self.gastado + estimado > self.lim["tokens_ejecucion"]:
            raise SinIA("tope de tokens de esta ejecución alcanzado")
        if self.uso.en_24h(self.reloj()) + estimado > self.lim["tokens_24h"]:
            raise SinIA("tope de tokens de 24 h alcanzado")

    def ruta_cache(self, clave):
        return self.cache / f"{hashlib.sha256(clave.encode()).hexdigest()}.json"

    def pedir(self, clave_cache, mensajes, validar):
        """Devuelve el resultado validado (de caché o de la API). validar(obj) -> (resultado|None, errores)."""
        ruta = self.ruta_cache(clave_cache)
        if ruta.exists():
            self.de_cache += 1
            return json.loads(ruta.read_text())
        mensajes = list(mensajes)
        reparaciones = self.conf["reparaciones"]
        intentos = 0
        while True:
            estimado = self.estimar(mensajes)
            self._reservar(estimado)
            espera = self.ultima + self.conf["pausa_minima_s"] - time.monotonic()
            if espera > 0:
                self.dormir(espera)
            self.ultima = time.monotonic()
            cuerpo = json.dumps({"model": self.conf["modelo"], "messages": mensajes, "temperature": 0,
                                 "max_tokens": self.conf["max_tokens_respuesta"], "response_format": {"type": "json_object"},
                                 **(self.conf.get("parametros") or {})}).encode()
            try:
                estado, cab, resp = self.transporte("POST", self.conf["url"] + "/chat/completions", self._cabeceras(), cuerpo, self.conf["timeout_s"])
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                estado, cab, resp = 0, {}, str(e).encode()
            self.peticiones += 1
            cab = {k.lower(): v for k, v in cab.items()}
            self.limites_api.update({k: v for k, v in cab.items() if k.startswith("x-ratelimit-")})
            error = _error(resp) if estado != 200 else {}
            if estado == 200 or error.get("code") == "json_validate_failed":
                # json_validate_failed: el modelo generó algo que no es JSON (p. ej. cortado). Ha gastado tokens
                # (sin "usage": se anota lo estimado) y se trata igual que un JSON inválido: se pide reparar.
                datos = json.loads(resp) if estado == 200 else {}
                usados = (datos.get("usage") or {}).get("total_tokens") or estimado  # sin dato: se anota lo estimado
                self.gastado += usados
                self.uso.anotar(self.reloj(), usados, self.ejecucion)
                contenido = datos["choices"][0]["message"].get("content") or "" if datos else (error.get("failed_generation") or "")
                try:
                    obj = json.loads(contenido)
                except ValueError:
                    obj, errores = None, ["la respuesta no es JSON válido"]
                if obj is not None:
                    resultado, errores = validar(obj)
                    if resultado is not None:
                        ruta.parent.mkdir(parents=True, exist_ok=True)
                        ruta.write_text(json.dumps(resultado, ensure_ascii=False))
                        return resultado
                if reparaciones <= 0:
                    raise ValueError("respuesta inválida tras reparar: " + "; ".join(errores[:3]))
                reparaciones -= 1
                mensajes += [{"role": "assistant", "content": contenido[:4000]},
                             {"role": "user", "content": "La respuesta no cumple el formato o las reglas: " + "; ".join(errores[:8])
                              + ". Devuelve de nuevo SOLO el objeto JSON corregido, con citas copiadas literalmente del texto."}]
                continue
            intentos += 1
            if estado == 429:
                espera = float(cab.get("retry-after") or 0)
                if espera > 60 or intentos > self.conf["reintentos"]:
                    raise SinIA("cuota de Groq agotada (HTTP 429)")
                self.dormir(max(espera, 2 * intentos))
                continue
            if estado in (401, 403):
                raise SinIA(f"clave rechazada por Groq (HTTP {estado})")
            if 400 <= estado < 500:  # petición rechazada: repetirla igual no sirve
                raise ValueError(f"Groq rechazó la petición (HTTP {estado}: {error.get('message', '')[:200]})")
            if intentos > self.conf["reintentos"]:
                raise ValueError(f"Groq no responde bien (HTTP {estado}: {error.get('message', '')[:200]})")
            self.dormir(2 ** intentos)
