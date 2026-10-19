"""Fetch en vivo (paso online 4 del spec): cuando el retrieval no encuentra nada
usable, se trae la página oficial vía `enlaces` del registro más cercano y se
extrae con el mismo modelo potente y esquema que el paso offline. Fail-soft total."""
import ipaddress
import logging
import socket
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from db.connection import get_connection
from db.queries import guardar_fetch_cache, leer_fetch_cache
from ingest.costo_llm import extraer_costo
from providers.base import ChatProvider

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 10.0
MAX_BYTES = 2_000_000
MAX_CHARS_TEXTO = 8000
MIN_CHARS_TEXTO = 200
TTL_DIAS = 7
MAX_REDIRECCIONES = 3


def primera_url(enlaces) -> str | None:
    for enlace in enlaces or []:
        if isinstance(enlace, str) and _es_http(enlace):
            return enlace
        if isinstance(enlace, dict):
            for clave in ("url", "enlace", "href", "link"):
                valor = enlace.get(clave)
                if isinstance(valor, str) and _es_http(valor):
                    return valor
    return None


def extraer_texto(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    texto = " ".join(soup.get_text(" ").split())
    return texto[:MAX_CHARS_TEXTO]


def _es_http(url: str) -> bool:
    return urlsplit(url.strip()).scheme.lower() in ("http", "https")


def url_es_publica(url: str) -> bool:
    """Defensa SSRF: solo http(s) hacia hosts cuyas IPs sean TODAS públicas.

    Las URLs salen del dataset (no del usuario), pero si un registro trae
    http://169.254.169.254/ o http://localhost:5432, el backend no debe ir a
    buscarlas. Queda abierta la ventana de DNS rebinding entre este chequeo y la
    conexión; para páginas de gob.bo y un backend sin red interna alcanza."""
    try:
        partes = urlsplit(url)
        if partes.scheme.lower() not in ("http", "https") or not partes.hostname:
            return False
        if partes.username or partes.password:
            return False
        puerto = partes.port or (443 if partes.scheme.lower() == "https" else 80)
        direcciones = {info[4][0] for info in socket.getaddrinfo(partes.hostname, puerto)}
    except (ValueError, OSError):
        return False
    return bool(direcciones) and all(
        ipaddress.ip_address(d.split("%")[0]).is_global for d in direcciones
    )


def fetch_pagina(url: str) -> str | None:
    """Fail-soft: None ante cualquier problema de red, tamaño o destino no público.

    Las redirecciones se siguen a mano (máx. MAX_REDIRECCIONES) para validar cada
    salto: un sitio público podría redirigir a una IP interna."""
    try:
        with httpx.Client(timeout=TIMEOUT_SEGUNDOS, follow_redirects=False) as client:
            for _ in range(MAX_REDIRECCIONES + 1):
                if not url_es_publica(url):
                    logger.warning("fetch en vivo bloqueado (destino no público): %s", url)
                    return None
                with client.stream("GET", url) as respuesta:
                    if respuesta.is_redirect:
                        url = urljoin(url, respuesta.headers.get("location", ""))
                        continue
                    respuesta.raise_for_status()
                    # tope de tamaño leyendo por partes: no confiar en Content-Length
                    cuerpo = bytearray()
                    for trozo in respuesta.iter_bytes():
                        cuerpo.extend(trozo)
                        if len(cuerpo) > MAX_BYTES:
                            return None
                    return cuerpo.decode(respuesta.encoding or "utf-8", errors="replace")
            logger.warning("fetch en vivo: demasiadas redirecciones desde %s", url)
            return None
    except Exception:
        logger.warning("fetch en vivo falló para %s", url, exc_info=True)
        return None


def buscar_en_vivo(chat_potente: ChatProvider, candidatos: list[dict]) -> dict | None:
    """Intenta responder desde la página externa del candidato más cercano con enlaces.

    Devuelve {"url", "texto", "costo"} o None. Fail-soft total: nunca lanza.
    """
    try:
        url = None
        for candidato in candidatos or []:
            url = primera_url(candidato.get("enlaces"))
            if url:
                break
        if not url:
            return None

        with get_connection() as conn:
            cacheado = leer_fetch_cache(conn, url, ttl_dias=TTL_DIAS)
        if cacheado is not None:
            return cacheado

        html = fetch_pagina(url)
        if not html:
            return None
        texto = extraer_texto(html)
        if len(texto) < MIN_CHARS_TEXTO:
            return None

        costo = extraer_costo(chat_potente, texto, None)
        datos = {"url": url, "texto": texto, "costo": costo}
        with get_connection() as conn:
            guardar_fetch_cache(conn, url, datos)
            conn.commit()
        return datos
    except Exception:
        logger.warning("buscar_en_vivo falló", exc_info=True)
        return None
