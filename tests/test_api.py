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
    monkeypatch.setattr(main.limitador_chat, "limite", 2)
    main.limitador_chat.limpiar()
    client = TestClient(main.app)
    cabecera = {"X-Forwarded-For": "8.8.8.8"}
    codigos = [client.post("/chat", json={"mensaje": "hola"}, headers=cabecera).status_code for _ in range(3)]
    assert codigos == [200, 200, 429]
    # otra IP no comparte la ventana
    assert client.post("/chat", json={"mensaje": "hola"}, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    main.limitador_chat.limpiar()
    main.app.dependency_overrides.clear()


def test_chat_limite_no_se_salta_falsificando_x_forwarded_for(monkeypatch):
    """El cliente controla el inicio de X-Forwarded-For; Render agrega la IP real
    al final. Cambiar la primera entrada en cada request no debe dar cupo nuevo."""
    main.app.dependency_overrides[main.get_deps] = _deps_fake
    monkeypatch.setattr(main, "procesar_mensaje", _pipeline_fake)
    monkeypatch.setattr(main.limitador_chat, "limite", 2)
    main.limitador_chat.limpiar()
    client = TestClient(main.app)
    codigos = [
        client.post(
            "/chat", json={"mensaje": "hola"}, headers={"X-Forwarded-For": f"9.9.9.{i}, 8.8.4.4, 10.0.0.5"}
        ).status_code
        for i in range(3)
    ]
    assert codigos == [200, 200, 429]
    main.limitador_chat.limpiar()
    main.app.dependency_overrides.clear()


def test_ip_cliente_toma_la_ip_publica_mas_a_la_derecha():
    from starlette.requests import Request

    from api.limites import ip_cliente

    def _req(xff):
        cabeceras = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
        return Request({"type": "http", "headers": cabeceras, "client": ("10.1.2.3", 1234)})

    assert ip_cliente(_req("1.2.3.4, 8.8.8.8")) == "8.8.8.8"
    assert ip_cliente(_req("basura, 8.8.8.8, 10.0.0.1, 127.0.0.1")) == "8.8.8.8"
    assert ip_cliente(_req("2001:4860:4860::8888")) == "2001:4860:4860::8888"
    # sin IP pública confiable: la conexión directa
    assert ip_cliente(_req("10.0.0.1")) == "10.1.2.3"
    assert ip_cliente(_req(None)) == "10.1.2.3"


def test_limitador_barre_ventanas_vencidas(monkeypatch):
    import api.limites as limites

    reloj = [1000.0]
    monkeypatch.setattr(limites.time, "monotonic", lambda: reloj[0])
    monkeypatch.setattr(limites, "MAX_CLAVES_ANTES_DE_BARRER", 10)
    limitador = limites.LimitadorPorMinuto(5)
    for i in range(11):
        limitador.permitir(f"ip-{i}")
    reloj[0] += 61
    limitador.permitir("ip-nueva")
    assert len(limitador) == 1


def test_chat_rechaza_conversation_id_que_no_es_uuid(monkeypatch):
    """Antes se aceptaba cualquier string: "whatsapp:<número>" daba acceso al
    historial de esa persona desde el chat web."""
    main.app.dependency_overrides[main.get_deps] = _deps_fake
    monkeypatch.setattr(main, "procesar_mensaje", _pipeline_fake)
    main.limitador_chat.limpiar()
    client = TestClient(main.app)
    for malo in ("whatsapp:59171234567", "x" * 5000, ""):
        respuesta = client.post("/chat", json={"mensaje": "hola", "conversation_id": malo})
        assert respuesta.status_code == 422
    ok = client.post("/chat", json={"mensaje": "hola", "conversation_id": "0b8f4c1e-9a52-4c39-9a1e-2f0f7d1c1a11"})
    assert ok.status_code == 200
    main.limitador_chat.limpiar()
    main.app.dependency_overrides.clear()


def test_cabeceras_de_seguridad():
    respuesta = TestClient(main.app).get("/health")
    assert respuesta.headers["x-content-type-options"] == "nosniff"
    assert respuesta.headers["x-frame-options"] == "DENY"


def test_tramite_id_fuera_de_rango_da_422():
    assert TestClient(main.app).get("/tramites/99999999999").status_code == 422


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
