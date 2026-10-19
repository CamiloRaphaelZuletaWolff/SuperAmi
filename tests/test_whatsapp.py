import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

import api.main as main
import api.whatsapp as whatsapp
from api.conversations import ConversationStore
from api.pipeline import Deps


@pytest.fixture(autouse=True)
def _limpiar_estado(monkeypatch):
    monkeypatch.delenv("WHATSAPP_ALLOW_UNSIGNED", raising=False)
    whatsapp.limitador_whatsapp.limpiar()
    whatsapp._mensajes_vistos.clear()
    yield
    main.app.dependency_overrides.clear()


def _firmar(cuerpo: bytes, secreto: bytes = b"shhh") -> str:
    return "sha256=" + hmac.new(secreto, cuerpo, hashlib.sha256).hexdigest()


def _deps_fake():
    return Deps(chat_economico=None, chat_potente=None, embedder=None, store=ConversationStore(), catalogos={})


def _payload_mensaje(texto: str, wa_id: str = "59171234567") -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {"from": wa_id, "type": "text", "text": {"body": texto}}
                            ]
                        }
                    }
                ]
            }
        ]
    }


def _payload_status() -> dict:
    """Forma real de un evento de status (entregado/leído), sin 'messages'."""
    return {"entry": [{"changes": [{"value": {"statuses": [{"status": "delivered"}]}}]}]}


def test_verificar_webhook_ok(monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "token-secreto")
    client = TestClient(main.app)

    respuesta = client.get(
        "/webhook/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "token-secreto", "hub.challenge": "1234"},
    )

    assert respuesta.status_code == 200
    assert respuesta.text == "1234"


def test_verificar_webhook_token_invalido(monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "token-secreto")
    client = TestClient(main.app)

    respuesta = client.get(
        "/webhook/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "token-incorrecto", "hub.challenge": "1234"},
    )

    assert respuesta.status_code == 403


def test_verificar_webhook_sin_token_configurado_rechaza(monkeypatch):
    """Fail-closed: sin WHATSAPP_VERIFY_TOKEN, un verify_token vacío no debe pasar."""
    monkeypatch.delenv("WHATSAPP_VERIFY_TOKEN", raising=False)
    client = TestClient(main.app)

    for params in (
        {"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1234"},
        {"hub.mode": "subscribe", "hub.challenge": "1234"},
    ):
        assert client.get("/webhook/whatsapp", params=params).status_code == 403


def test_verificar_webhook_token_vacio_configurado_rechaza(monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "")
    respuesta = TestClient(main.app).get(
        "/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"}
    )
    assert respuesta.status_code == 403


def test_post_sin_app_secret_se_rechaza(monkeypatch):
    """Fail-closed: sin WHATSAPP_APP_SECRET y sin opt-out explícito, 401 y no se procesa nada."""
    monkeypatch.delenv("WHATSAPP_APP_SECRET", raising=False)
    deps = _deps_fake()
    main.app.dependency_overrides[main.get_deps] = lambda: deps
    llamado = []
    monkeypatch.setattr(whatsapp, "procesar_mensaje", lambda d, cid, m: llamado.append(m) or iter([]))
    monkeypatch.setattr(whatsapp, "_enviar_texto", lambda to, texto: llamado.append(texto))
    client = TestClient(main.app)

    respuesta = client.post("/webhook/whatsapp", json=_payload_mensaje("hola"))

    assert respuesta.status_code == 401
    assert llamado == []


def test_post_sin_firma_con_app_secret_se_rechaza(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "shhh")
    monkeypatch.setenv("WHATSAPP_ALLOW_UNSIGNED", "true")  # el opt-out NO aplica si hay secret
    deps = _deps_fake()
    main.app.dependency_overrides[main.get_deps] = lambda: deps
    respuesta = TestClient(main.app).post("/webhook/whatsapp", json=_payload_mensaje("hola"))
    assert respuesta.status_code == 401


def test_post_sin_app_secret_con_opt_out_de_dev_se_acepta(monkeypatch):
    """WHATSAPP_ALLOW_UNSIGNED=true: modo desarrollo local, se acepta sin firma."""
    monkeypatch.delenv("WHATSAPP_APP_SECRET", raising=False)
    monkeypatch.setenv("WHATSAPP_ALLOW_UNSIGNED", "true")
    deps = _deps_fake()
    main.app.dependency_overrides[main.get_deps] = lambda: deps
    monkeypatch.setattr(whatsapp, "procesar_mensaje", lambda d, cid, m: iter([("answer", {"delta": "hola"})]))
    monkeypatch.setattr(whatsapp, "_enviar_texto", lambda to, texto: None)
    client = TestClient(main.app)

    respuesta = client.post("/webhook/whatsapp", json=_payload_mensaje("hola"))

    assert respuesta.status_code == 200
    main.app.dependency_overrides.clear()


def test_post_firma_invalida_se_rechaza(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "shhh")
    deps = _deps_fake()
    main.app.dependency_overrides[main.get_deps] = lambda: deps
    client = TestClient(main.app)

    respuesta = client.post(
        "/webhook/whatsapp",
        json=_payload_mensaje("hola"),
        headers={"x-hub-signature-256": "sha256=firma_incorrecta"},
    )

    assert respuesta.status_code == 401
    main.app.dependency_overrides.clear()


def test_post_firma_valida_se_acepta_y_responde(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "shhh")
    deps = _deps_fake()
    main.app.dependency_overrides[main.get_deps] = lambda: deps
    monkeypatch.setattr(
        whatsapp, "procesar_mensaje", lambda d, cid, m: iter([("answer", {"delta": f"eco: {m}"})])
    )
    enviados = []
    monkeypatch.setattr(whatsapp, "_enviar_texto", lambda to, texto: enviados.append((to, texto)))
    client = TestClient(main.app)
    cuerpo = json.dumps(_payload_mensaje("hola")).encode()
    firma = _firmar(cuerpo)

    respuesta = client.post(
        "/webhook/whatsapp", content=cuerpo, headers={"x-hub-signature-256": firma, "content-type": "application/json"}
    )

    assert respuesta.status_code == 200
    assert enviados == [("59171234567", "eco: hola")]
    main.app.dependency_overrides.clear()


def test_post_evento_de_status_no_hace_nada(monkeypatch):
    monkeypatch.delenv("WHATSAPP_APP_SECRET", raising=False)
    monkeypatch.setenv("WHATSAPP_ALLOW_UNSIGNED", "true")
    deps = _deps_fake()
    main.app.dependency_overrides[main.get_deps] = lambda: deps
    enviados = []
    monkeypatch.setattr(whatsapp, "_enviar_texto", lambda to, texto: enviados.append((to, texto)))
    client = TestClient(main.app)

    respuesta = client.post("/webhook/whatsapp", json=_payload_status())

    assert respuesta.status_code == 200
    assert enviados == []
    main.app.dependency_overrides.clear()


def _post_firmado(client, payload: dict):
    cuerpo = json.dumps(payload).encode()
    return client.post(
        "/webhook/whatsapp",
        content=cuerpo,
        headers={"x-hub-signature-256": _firmar(cuerpo), "content-type": "application/json"},
    )


def test_limite_por_numero(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "shhh")
    monkeypatch.setattr(whatsapp.limitador_whatsapp, "limite", 2)
    deps = _deps_fake()
    main.app.dependency_overrides[main.get_deps] = lambda: deps
    procesados = []
    monkeypatch.setattr(
        whatsapp, "procesar_mensaje", lambda d, cid, m: procesados.append(m) or iter([("answer", {"delta": "ok"})])
    )
    monkeypatch.setattr(whatsapp, "_enviar_texto", lambda to, texto: None)
    client = TestClient(main.app)

    for i in range(3):
        assert _post_firmado(client, _payload_mensaje(f"consulta {i}")).status_code == 200
    assert procesados == ["consulta 0", "consulta 1"]
    # otro número tiene su propio cupo
    _post_firmado(client, _payload_mensaje("otra", wa_id="59170000000"))
    assert procesados[-1] == "otra"


def test_texto_largo_se_recorta_y_conversacion_no_guarda_el_numero(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "shhh")
    deps = _deps_fake()
    main.app.dependency_overrides[main.get_deps] = lambda: deps
    recibido = {}

    def _pipeline(d, cid, m):
        recibido.update(cid=cid, mensaje=m)
        return iter([("answer", {"delta": "ok"})])

    monkeypatch.setattr(whatsapp, "procesar_mensaje", _pipeline)
    monkeypatch.setattr(whatsapp, "_enviar_texto", lambda to, texto: None)

    _post_firmado(TestClient(main.app), _payload_mensaje("x" * 5000))

    assert len(recibido["mensaje"]) == whatsapp.MAX_CHARS_ENTRADA
    assert recibido["cid"].startswith("whatsapp:")
    assert "59171234567" not in recibido["cid"]


def test_post_firma_con_caracteres_raros_da_401_no_500(monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "shhh")
    deps = _deps_fake()
    main.app.dependency_overrides[main.get_deps] = lambda: deps
    respuesta = TestClient(main.app).post(
        "/webhook/whatsapp",
        json=_payload_mensaje("hola"),
        headers={"x-hub-signature-256": "sha256=éé".encode("latin-1")},
    )
    assert respuesta.status_code == 401
