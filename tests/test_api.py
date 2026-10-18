from fastapi.testclient import TestClient

import api.main as main
from api.conversations import ConversationStore
from api.pipeline import Deps


def _deps_fake():
    return Deps(chat_economico=None, chat_potente=None, embedder=None, store=ConversationStore(), catalogos={})


def _pipeline_fake(deps, cid, mensaje, con_traza=False):
    yield ("answer", {"delta": f"eco: {mensaje}"})
    yield ("answer", {"done": True, "tramite_ids": [42]})


def test_chat_devuelve_sse_con_conversation_id(monkeypatch):
    deps = _deps_fake()
    main.app.dependency_overrides[main.get_deps] = lambda: deps
    monkeypatch.setattr(main, "procesar_mensaje", _pipeline_fake)
    client = TestClient(main.app)

    respuesta = client.post("/chat", json={"mensaje": "hola"})

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/event-stream")
    cuerpo = respuesta.text
    assert "event: answer" in cuerpo
    assert '"delta": "eco: hola"' in cuerpo
    assert '"conversation_id"' in cuerpo
    assert '"tramite_ids": [42]' in cuerpo
    main.app.dependency_overrides.clear()


def test_health():
    client = TestClient(main.app)
    assert client.get("/health").json() == {"ok": True}


def test_chat_pasa_traza_al_pipeline(monkeypatch):
    recibido = {}

    def _pipeline(deps, cid, mensaje, con_traza=False):
        recibido["con_traza"] = con_traza
        yield ("answer", {"done": True, "tramite_ids": []})

    main.app.dependency_overrides[main.get_deps] = _deps_fake
    monkeypatch.setattr(main, "procesar_mensaje", _pipeline)
    TestClient(main.app).post("/chat", json={"mensaje": "hola", "traza": True})
    assert recibido["con_traza"] is True
    main.app.dependency_overrides.clear()


def test_chat_limita_por_ip(monkeypatch):
    main.app.dependency_overrides[main.get_deps] = _deps_fake
    monkeypatch.setattr(main, "procesar_mensaje", _pipeline_fake)
    monkeypatch.setattr(main, "CHAT_LIMITE_POR_MINUTO", 2)
    main._ventanas.clear()
    client = TestClient(main.app)
    cabecera = {"X-Forwarded-For": "203.0.113.7"}
    codigos = [client.post("/chat", json={"mensaje": "hola"}, headers=cabecera).status_code for _ in range(3)]
    assert codigos == [200, 200, 429]
    # otra IP no comparte la ventana
    assert client.post("/chat", json={"mensaje": "hola"}, headers={"X-Forwarded-For": "198.51.100.1"}).status_code == 200
    main._ventanas.clear()
    main.app.dependency_overrides.clear()


def test_cors_permite_origen_configurado():
    client = TestClient(main.app)
    respuesta = client.options(
        "/chat",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert respuesta.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_tramite_inexistente_da_404(monkeypatch):
    from contextlib import contextmanager

    @contextmanager
    def _conn():
        yield None

    monkeypatch.setattr(main, "get_connection", _conn)
    monkeypatch.setattr(main, "obtener_tramite", lambda conn, tid: None)
    assert TestClient(main.app).get("/tramites/999").status_code == 404
