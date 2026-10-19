import json
import logging
import os
import time
import uuid

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Path, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from api import whatsapp
from api.deps import get_deps
from api.limites import LimitadorPorMinuto, ip_cliente
from api.pipeline import Deps, procesar_mensaje
from db.connection import get_connection
from db.queries import estadisticas, obtener_tramite

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="AMI — Asistente de Trámites Bolivia")
app.include_router(whatsapp.router)

# Orígenes del frontend web, separados por coma (ej. https://ami.vercel.app).
# Sin la variable solo se acepta el dev server local.
_origenes = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origenes,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

_CABECERAS_SEGURIDAD = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
]


class CabecerasDeSeguridad:
    """API JSON/SSE: nadie debería embeberla en un iframe ni adivinarle el
    content-type. Middleware ASGI puro (no BaseHTTPMiddleware) para no
    interferir con el streaming SSE de /chat."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def enviar(mensaje):
            if mensaje["type"] == "http.response.start":
                mensaje.setdefault("headers", [])
                mensaje["headers"] = list(mensaje["headers"]) + _CABECERAS_SEGURIDAD
            await send(mensaje)

        await self.app(scope, receive, enviar)


app.add_middleware(CabecerasDeSeguridad)

# Límite por IP para /chat: el demo es público y cada mensaje gasta cuota del LLM.
# En memoria (una sola instancia en Render free); 0 lo desactiva.
CHAT_LIMITE_POR_MINUTO = int(os.environ.get("CHAT_RATE_LIMIT_PER_MIN", "12"))
limitador_chat = LimitadorPorMinuto(CHAT_LIMITE_POR_MINUTO)


def limitar_chat(request: Request) -> None:
    if not limitador_chat.permitir(ip_cliente(request)):
        raise HTTPException(status_code=429, detail="Demasiados mensajes seguidos. Espera un minuto 🙏")


class ChatRequest(BaseModel):
    mensaje: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = None
    traza: bool = False

    @field_validator("conversation_id")
    @classmethod
    def _solo_uuid(cls, valor: str | None) -> str | None:
        # Los ids que entrega el backend son UUID. Aceptar cualquier string dejaba
        # pedir "whatsapp:<número>" y leer/escribir la conversación de esa persona.
        if valor is None:
            return None
        try:
            return str(uuid.UUID(valor))
        except ValueError:
            raise ValueError("conversation_id inválido") from None


def _sse(evento: str, data: dict) -> str:
    return f"event: {evento}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/chat", dependencies=[Depends(limitar_chat)])
def chat(request: ChatRequest, deps: Deps = Depends(get_deps)):
    cid = deps.store.get_or_create(request.conversation_id)

    def generar():
        for evento, data in procesar_mensaje(deps, cid, request.mensaje, con_traza=request.traza):
            yield _sse(evento, {"conversation_id": cid, **data})

    return StreamingResponse(generar(), media_type="text/event-stream")


@app.get("/tramites/{tramite_id}")
def tramite(tramite_id: int = Path(ge=1, le=2_147_483_647)):
    with get_connection() as conn:
        ficha = obtener_tramite(conn, tramite_id)
    if ficha is None:
        raise HTTPException(status_code=404, detail="Trámite no encontrado")
    return ficha


_cache_stats: dict = {"ts": 0.0, "datos": None}


@app.get("/stats")
def stats():
    # el corpus cambia con el sync semanal: 10 min de cache sobra
    if _cache_stats["datos"] is None or time.monotonic() - _cache_stats["ts"] > 600:
        with get_connection() as conn:
            _cache_stats["datos"] = estadisticas(conn)
        _cache_stats["ts"] = time.monotonic()
    return _cache_stats["datos"]
