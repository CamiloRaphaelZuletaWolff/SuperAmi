"""Límite de mensajes por ventana deslizante de 60 s, en memoria.

Lo usan POST /chat (por IP) y el webhook de WhatsApp (por número). Alcanza para
una sola instancia (Render free); con varias instancias habría que moverlo a
Redis o a la base.
"""

import ipaddress
import time
from collections import deque

from starlette.requests import Request

VENTANA_SEGUNDOS = 60
# Pasado este número de claves se barren las ventanas vencidas: sin esto, cada
# IP distinta deja una entrada para siempre y la memoria crece sin tope.
MAX_CLAVES_ANTES_DE_BARRER = 5000


class LimitadorPorMinuto:
    def __init__(self, limite: int):
        self.limite = limite
        self._ventanas: dict[str, deque] = {}

    def permitir(self, clave: str) -> bool:
        """True si `clave` todavía tiene cupo (y lo consume). limite <= 0 lo desactiva."""
        if self.limite <= 0:
            return True
        ahora = time.monotonic()
        if len(self._ventanas) > MAX_CLAVES_ANTES_DE_BARRER:
            self._barrer(ahora)
        ventana = self._ventanas.setdefault(clave, deque())
        while ventana and ahora - ventana[0] > VENTANA_SEGUNDOS:
            ventana.popleft()
        if len(ventana) >= self.limite:
            return False
        ventana.append(ahora)
        return True

    def _barrer(self, ahora: float) -> None:
        vencidas = [c for c, v in self._ventanas.items() if not v or ahora - v[-1] > VENTANA_SEGUNDOS]
        for clave in vencidas:
            del self._ventanas[clave]

    def limpiar(self) -> None:
        self._ventanas.clear()

    def __len__(self) -> int:
        return len(self._ventanas)


def _es_ip_publica(valor: str) -> bool:
    try:
        return ipaddress.ip_address(valor).is_global
    except ValueError:
        return False


def ip_cliente(request: Request) -> str:
    """IP del cliente detrás del proxy de Render (o Caddy en EC2).

    X-Forwarded-For es "cliente, proxy1, proxy2…", pero Render NO borra lo que
    manda el cliente: solo AGREGA a la derecha la IP desde la que le llegó la
    conexión. Entonces la primera entrada la escribe quien quiera (falsificable:
    con un valor distinto por request se saltaba el límite). Lo confiable es lo
    que agregan los proxies, a la derecha: tomamos la primera IP pública
    empezando por la derecha (los saltos internos del proxy son IPs privadas).
    """
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        for entrada in reversed(reenviada.split(",")):
            entrada = entrada.strip()
            if _es_ip_publica(entrada):
                return entrada
    return request.client.host if request.client else "desconocida"
