import json
import logging
import os
import time
from collections import defaultdict, deque

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api import whatsapp
from api.deps import get_deps
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

# Límite por IP para /chat: el demo es público y cada mensaje gasta cuota del LLM.
# En memoria (una sola instancia en Render free); 0 lo desactiva.
CHAT_LIMITE_POR_MINUTO = int(os.environ.get("CHAT_RATE_LIMIT_PER_MIN", "12"))
_ventanas: dict[str, deque] = defaultdict(deque)


def _ip_cliente(request: Request) -> str:
    # Render (y cualquier proxy) agrega la IP real al inicio de X-Forwarded-For
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"


def limitar_chat(request: Request) -> None:
    if CHAT_LIMITE_POR_MINUTO <= 0:
        return
    ahora = time.monotonic()
    ventana = _ventanas[_ip_cliente(request)]
    while ventana and ahora - ventana[0] > 60:
        ventana.popleft()
    if len(ventana) >= CHAT_LIMITE_POR_MINUTO:
        raise HTTPException(status_code=429, detail="Demasiados mensajes seguidos. Espera un minuto 🙏")
    ventana.append(ahora)


class ChatRequest(BaseModel):
    mensaje: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = None
    traza: bool = False


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
def tramite(tramite_id: int):
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
