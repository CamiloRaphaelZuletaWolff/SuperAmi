"""Webhook de WhatsApp Cloud API.

Recibe los mensajes entrantes de WhatsApp, los pasa por el MISMO pipeline que
usa POST /chat (api/pipeline.py::procesar_mensaje), junta la respuesta en
streaming en un solo texto (WhatsApp no soporta streaming) y la manda de
vuelta llamando a la Graph API de Meta.

Importante: le respondemos 200 OK a Meta ANTES de terminar de procesar
(usando BackgroundTasks). Si tardamos varios segundos en responder al POST
del webhook (el pipeline llama a un LLM, puede tardar), Meta puede reintentar
la entrega y duplicar el mensaje. Procesar en background evita eso.

Variables de entorno requeridas (agregalas a .env, ver .env.example):
- WHATSAPP_TOKEN            access token (temporal de prueba, o permanente de
                             un system user para producción)
- WHATSAPP_PHONE_NUMBER_ID  id del número de teléfono, lo da Meta en
                             WhatsApp Manager / App Dashboard > WhatsApp > API Setup
- WHATSAPP_VERIFY_TOKEN     un string que vos inventás; se usa SOLO para el
                             handshake de verificación del webhook (paso GET).
                             Sin él, la verificación se rechaza siempre.
- WHATSAPP_APP_SECRET       OBLIGATORIO: valida que los POST entrantes vienen
                             realmente de Meta y no de un tercero que le pegue
                             a tu URL. Sin él, el webhook rechaza todo (401).
- WHATSAPP_ALLOW_UNSIGNED   solo desarrollo local: "true" acepta POST sin firma
                             cuando no hay WHATSAPP_APP_SECRET. Nunca en producción.
- WHATSAPP_RATE_LIMIT_PER_MIN  mensajes por minuto por número (default 6; 0 lo
                             desactiva). Cada mensaje gasta cuota del LLM.
"""

import hashlib
import hmac
import json
import logging
import os
import re
from collections import deque

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response

from api.deps import get_deps
from api.limites import LimitadorPorMinuto
from api.pipeline import Deps, procesar_mensaje

logger = logging.getLogger(__name__)

router = APIRouter()

GRAPH_API_VERSION = "v23.0"  # versión actual de Graph API al momento de escribir esto (jul 2026)
LIMITE_TEXTO_WHATSAPP = 4096  # límite de WhatsApp por mensaje de texto
MAX_CHARS_ENTRADA = 1000  # mismo tope que POST /chat: textos enormes = tokens caros

# Un número que manda ráfagas (o un bot) quema la cuota del LLM igual que /chat.
limitador_whatsapp = LimitadorPorMinuto(int(os.environ.get("WHATSAPP_RATE_LIMIT_PER_MIN", "6")))

# Dedup en memoria: Meta entrega "al menos una vez" y puede reenviar el mismo
# mensaje. Guardamos los ids recientes para no responder dos veces (se ve feo en
# vivo). Suficiente para un proceso único; se reinicia si se reinicia el server.
_mensajes_vistos: deque[str] = deque(maxlen=512)


@router.get("/webhook/whatsapp")
def verificar_webhook(request: Request):
    """Meta llama este endpoint (GET) al configurar el webhook en el dashboard,
    para confirmar que la URL es tuya. Debe devolver el `hub.challenge` tal
    cual si el `hub.verify_token` coincide con el que configuraste."""
    params = request.query_params
    verify_token = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
    recibido = params.get("hub.verify_token", "")
    # fail-closed: sin token configurado, "" == "" dejaba verificar a cualquiera
    if (
        verify_token
        and params.get("hub.mode") == "subscribe"
        and hmac.compare_digest(recibido.encode(), verify_token.encode())
    ):
        # text/plain + nosniff: el challenge vuelve tal cual, que no se interprete como HTML
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=403)


def _permitir_sin_firma() -> bool:
    return os.environ.get("WHATSAPP_ALLOW_UNSIGNED", "").strip().lower() in ("1", "true", "yes")


def _firma_valida(body: bytes, firma_header: str | None) -> bool:
    """Verifica el header X-Hub-Signature-256 que Meta manda en cada POST,
    calculado con el App Secret. Evita que cualquiera le pegue a tu webhook
    haciéndose pasar por Meta."""
    app_secret = os.environ.get("WHATSAPP_APP_SECRET")
    if not app_secret:
        if _permitir_sin_firma():
            logger.warning(
                "WHATSAPP_ALLOW_UNSIGNED=true y sin WHATSAPP_APP_SECRET: aceptando webhook SIN "
                "validar firma. Cualquiera puede gastar tu cuota del LLM. SOLO para desarrollo local."
            )
            return True
        logger.error(
            "WHATSAPP_APP_SECRET no configurado: se rechazan todos los POST del webhook "
            "(para pruebas locales sin firma: WHATSAPP_ALLOW_UNSIGNED=true)"
        )
        return False
    if not firma_header:
        return False
    esperado = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    # bytes: compare_digest con str no-ASCII lanza TypeError (500 en vez de 401)
    return hmac.compare_digest(esperado.encode(), firma_header.encode())


@router.post("/webhook/whatsapp")
async def recibir_mensaje(
    request: Request, background_tasks: BackgroundTasks, deps: Deps = Depends(get_deps)
):
    body = await request.body()
    if not _firma_valida(body, request.headers.get("x-hub-signature-256")):
        logger.warning("firma de webhook inválida o ausente, se descarta el POST")
        return Response(status_code=401)

    try:
        payload = json.loads(body)
        cambio = payload["entry"][0]["changes"][0]["value"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        logger.warning("payload de whatsapp con forma inesperada")
        return Response(status_code=200)

    mensajes = cambio.get("messages")
    if not mensajes:
        # eventos de status (entregado/leído) u otros — nada que responder
        return Response(status_code=200)

    mensaje_wa = mensajes[0]
    wa_id = mensaje_wa.get("from")  # número del usuario, formato internacional sin "+"
    if not isinstance(wa_id, str) or not wa_id:
        return Response(status_code=200)
    wa_message_id = mensaje_wa.get("id")
    texto = (mensaje_wa.get("text") or {}).get("body")

    # dedup de reenvíos de Meta (evita responder dos veces en vivo)
    if wa_message_id and wa_message_id in _mensajes_vistos:
        return Response(status_code=200)
    if wa_message_id:
        _mensajes_vistos.append(wa_message_id)

    if not limitador_whatsapp.permitir(wa_id):
        # sin respuesta: avisar en cada mensaje de la ráfaga también gastaría mensajes
        logger.warning("límite de mensajes alcanzado para %s, se ignora", _enmascarar(wa_id))
        return Response(status_code=200)

    if not isinstance(texto, str) or not texto.strip():
        background_tasks.add_task(
            _enviar_texto,
            wa_id,
            "¡Hola! 👋 Por ahora solo puedo leer mensajes de texto. "
            "Escríbeme tu consulta y con gusto te ayudo con tu trámite 😊",
        )
        return Response(status_code=200)

    # procesar en background: responder rápido a Meta, evitar reintentos/duplicados
    background_tasks.add_task(_procesar_y_responder, deps, wa_id, texto[:MAX_CHARS_ENTRADA], wa_message_id)
    return Response(status_code=200)


def _enmascarar(wa_id: str) -> str:
    """Para logs: el número completo es dato personal; con los últimos 4 alcanza."""
    return "***" + wa_id[-4:]


def _id_conversacion(wa_id: str) -> str:
    """Id de conversación sin el número en claro (queda en la base y en
    consultas_log). HMAC con el App Secret: un hash simple de un teléfono se
    revierte probando todos los números. Si se rota el secret, las
    conversaciones en curso arrancan de cero (se borran a las 24 h igual)."""
    clave = os.environ.get("WHATSAPP_APP_SECRET", "").encode()
    resumen = hmac.new(clave, wa_id.encode(), hashlib.sha256).hexdigest()[:32]
    return f"whatsapp:{resumen}"


def _procesar_y_responder(deps: Deps, wa_id: str, texto: str, wa_message_id: str | None = None) -> None:
    try:
        # marca leído + "escribiendo…": la síntesis tarda unos segundos y sin esto
        # el usuario ve silencio. Fail-soft: si falla, se sigue igual.
        _marcar_leido_y_escribiendo(wa_message_id)
        # una conversación por número de WhatsApp; reusa el mismo store que /chat
        conversation_id = deps.store.get_or_create(_id_conversacion(wa_id))

        partes: list[str] = []
        respuesta_final: str | None = None
        for evento, data in procesar_mensaje(deps, conversation_id, texto):
            if evento == "answer" and "delta" in data:
                partes.append(data["delta"])
            elif evento == "clarification":
                respuesta_final = data["text"]
            elif evento == "error":
                respuesta_final = data["message"]

        if respuesta_final is None:
            respuesta_final = "".join(partes).strip()

        if respuesta_final:
            _enviar_texto(wa_id, respuesta_final)
    except Exception:
        logger.exception("error procesando mensaje de whatsapp de %s", _enmascarar(wa_id))
        try:
            _enviar_texto(wa_id, "Hubo un problema procesando tu consulta. Intentá de nuevo en un momento.")
        except Exception:
            logger.exception("no se pudo avisar el error a %s", _enmascarar(wa_id))


def _marcar_leido_y_escribiendo(wa_message_id: str | None) -> None:
    """Marca el mensaje entrante como leído y muestra 'escribiendo…' (Cloud API
    v21+). Fail-soft total: cualquier error se ignora y no corta la respuesta."""
    if not wa_message_id:
        return
    try:
        token = os.environ["WHATSAPP_TOKEN"]
        phone_number_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": wa_message_id,
            "typing_indicator": {"type": "text"},
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        with httpx.Client(timeout=10) as client:
            client.post(url, headers=headers, json=payload)
    except Exception:
        logger.warning("no se pudo marcar leído/escribiendo para %s", wa_message_id, exc_info=True)


def _a_formato_whatsapp(texto: str) -> str:
    """Normaliza el markdown que a veces emite el modelo al formato de WhatsApp.
    WhatsApp usa *un asterisco* para negrita; **doble** se ve literal. También
    quita encabezados markdown (#) que WhatsApp no interpreta."""
    # **negrita** -> *negrita*  (y ***x*** -> *x*)
    texto = re.sub(r"\*{2,3}(.+?)\*{2,3}", r"*\1*", texto)
    # encabezados "### Título" -> "*Título*"
    texto = re.sub(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*$", r"*\1*", texto)
    return texto


def _enviar_texto(to: str, texto: str) -> None:
    token = os.environ["WHATSAPP_TOKEN"]
    phone_number_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": _a_formato_whatsapp(texto)[:LIMITE_TEXTO_WHATSAPP]},
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    with httpx.Client(timeout=15) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.error("error enviando whatsapp a %s: %s %s", _enmascarar(to), resp.status_code, resp.text[:500])
