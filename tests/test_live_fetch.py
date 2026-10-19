from api.live_fetch import extraer_texto, primera_url


def test_primera_url_acepta_strings_y_dicts():
    assert primera_url(["https://a.gob.bo/x"]) == "https://a.gob.bo/x"
    assert primera_url([{"url": "https://b.gob.bo/y"}]) == "https://b.gob.bo/y"
    assert primera_url([{"enlace": "https://c.gob.bo/z"}]) == "https://c.gob.bo/z"
    assert primera_url([{"titulo": "sin url"}, "https://d.gob.bo"]) == "https://d.gob.bo"
    assert primera_url([]) is None
    assert primera_url(None) is None
    assert primera_url(["ftp://no-http"]) is None


def test_extraer_texto_limpia_html():
    html = """<html><head><style>body{color:red}</style></head>
    <body><nav>menu</nav><script>var x=1;</script>
    <p>Requisitos   del  trámite</p><p>Costo: 50 Bs</p></body></html>"""
    texto = extraer_texto(html)
    assert "Requisitos del trámite" in texto
    assert "Costo: 50 Bs" in texto
    assert "var x=1" not in texto
    assert "menu" not in texto


def test_extraer_texto_trunca():
    texto = extraer_texto("<p>" + "palabra " * 5000 + "</p>")
    assert len(texto) <= 8000


def test_primera_url_ignora_esquemas_no_http():
    assert primera_url(["javascript:alert(1)", "httpfoo://x", "https://ok.gob.bo"]) == "https://ok.gob.bo"


def test_url_es_publica_bloquea_destinos_internos():
    from api.live_fetch import url_es_publica

    assert url_es_publica("https://8.8.8.8/tramite")
    for mala in (
        "http://127.0.0.1:8000/health",
        "http://localhost:5432/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://8.8.8.8/",
        "http://usuario:clave@8.8.8.8/",
        "no-es-url",
    ):
        assert not url_es_publica(mala), mala


def test_fetch_pagina_no_sigue_redireccion_a_ip_interna(monkeypatch):
    import httpx

    import api.live_fetch as live_fetch

    pedidos = []

    def _manejar(request):
        pedidos.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    cliente_real = httpx.Client
    monkeypatch.setattr(
        live_fetch.httpx, "Client", lambda **kw: cliente_real(transport=httpx.MockTransport(_manejar), **kw)
    )
    assert live_fetch.fetch_pagina("https://8.8.8.8/tramite") is None
    assert pedidos == ["https://8.8.8.8/tramite"]


def test_fetch_pagina_corta_respuestas_enormes(monkeypatch):
    import httpx

    import api.live_fetch as live_fetch

    cliente_real = httpx.Client
    enorme = httpx.MockTransport(lambda req: httpx.Response(200, content=b"a" * (live_fetch.MAX_BYTES + 10)))
    monkeypatch.setattr(live_fetch.httpx, "Client", lambda **kw: cliente_real(transport=enorme, **kw))
    assert live_fetch.fetch_pagina("https://8.8.8.8/tramite") is None

    normal = httpx.MockTransport(lambda req: httpx.Response(200, text="<p>hola</p>"))
    monkeypatch.setattr(live_fetch.httpx, "Client", lambda **kw: cliente_real(transport=normal, **kw))
    assert live_fetch.fetch_pagina("https://8.8.8.8/tramite") == "<p>hola</p>"
