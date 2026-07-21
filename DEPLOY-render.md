# Desplegar el backend AMI en Render

Objetivo: un **link estable HTTPS** (`https://ami-backend-XXXX.onrender.com`) para
que el webhook de WhatsApp le pegue sin depender de tu compu ni de ngrok.

Arquitectura en Render: un **Web Service (Docker)** + una **base Postgres
administrada** con pgvector. La base se carga UNA vez con el dump que ya tiene
los embeddings Gemini (`ami-20260721-gemini.dump`) — no hay que re-embeber nada.

---

## 0. Requisitos

- Cuenta en [render.com](https://render.com) (el plan free alcanza para el hackathon).
- El repo en GitHub (Render despliega desde GitHub).
- Estos archivos ya están en el repo: `Dockerfile`, `render.yaml`, `.dockerignore`.
- A mano: `GEMINI_API_KEY`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`,
  `WHATSAPP_APP_SECRET`, y el archivo `ami-20260721-gemini.dump`.

> El `.env` y los `*.dump` están en `.gitignore` — NO se suben a GitHub (bien:
> los secretos se cargan en el panel de Render, y la base se siembra aparte).

---

## 1. Subir el código a GitHub

```bash
git add Dockerfile render.yaml .dockerignore api/ providers/ db/ ingest/ requirements.txt
git commit -m "deploy: backend AMI en Render (Docker + Gemini)"
git push
```

## 2. Crear el Blueprint en Render

1. Render Dashboard → **New +** → **Blueprint**.
2. Elegí el repo `superAMI`. Render lee `render.yaml` y propone:
   - `ami-backend` (web service, Docker)
   - `ami-db` (Postgres 16)
3. Te va a pedir los secretos marcados `sync: false`. Cargá:
   - `GEMINI_API_KEY`
   - `WHATSAPP_TOKEN`
   - `WHATSAPP_PHONE_NUMBER_ID`
   - `WHATSAPP_APP_SECRET`
4. **Apply** / **Create**. Render construye la imagen y levanta ambos servicios.
   El web queda en `https://ami-backend-XXXX.onrender.com` (ese es el link).

## 3. Cargar la base (una sola vez)

El servicio arranca pero la base está vacía. Sembrala con el dump Gemini desde
tu compu (necesitás Docker; no hace falta instalar Postgres).

1. En Render: **ami-db** → **Connect** → copiá la **External Database URL**
   (algo como `postgresql://user:pass@dpg-xxxx.oregon-postgres.render.com/ami_db_xxxx`).
2. Desde la carpeta `superAMI/` (donde está el `.dump`):

```bash
# agregá ?sslmode=require al final de la URL externa
docker run --rm -i postgres:16 pg_restore --no-owner --no-acl --clean --if-exists \
  -d "postgresql://USER:PASS@HOST/DB?sslmode=require" < ami-20260721-gemini.dump
```

> Si `CREATE EXTENSION vector` falla por permisos, corré primero:
> `docker run --rm postgres:16 psql "postgresql://USER:PASS@HOST/DB?sslmode=require" -c "CREATE EXTENSION IF NOT EXISTS vector;"`
> y volvé a correr el `pg_restore`.

3. Verificá (debe decir 1814):

```bash
docker run --rm postgres:16 psql "postgresql://USER:PASS@HOST/DB?sslmode=require" \
  -c "SELECT count(*) tramites, count(embedding) con_embedding FROM tramites;"
```

## 4. Probar el backend (sin WhatsApp todavía)

```bash
curl https://ami-backend-XXXX.onrender.com/health
# {"ok":true}

curl -N -X POST https://ami-backend-XXXX.onrender.com/chat \
  -H 'content-type: application/json' \
  -d '{"mensaje":"cuanto cuesta pagar el impuesto de mi casa"}'
# stream SSE con la respuesta amable
```

## 5. Conectar WhatsApp (webhook)

Meta App Dashboard → WhatsApp → **Configuration → Webhook → Edit**:
- **Callback URL:** `https://ami-backend-XXXX.onrender.com/webhook/whatsapp`
- **Verify token:** `ami2026`
- Verificar → **Subscribe** al campo `messages`.

Ese es el link que tu compañero necesita: el **Callback URL** de arriba.

---

## ⚠️ Importante para la demo

- **Cold start (plan free):** el web se duerme tras ~15 min sin uso y tarda ~50s
  en despertar. El PRIMER mensaje de WhatsApp tras el reposo puede demorar (Meta
  reintenta; el bot deduplica, así que no responde doble). **Antes de presentar,
  “despertalo”**: abrí `https://ami-backend-XXXX.onrender.com/health` un minuto
  antes. Para que nunca duerma: subí `ami-backend` al plan **Starter (US$7/mes)**.
- **Token de WhatsApp temporal (~24h):** si los envíos empiezan a dar 401,
  regeneralo en Meta (API Setup) y actualizá `WHATSAPP_TOKEN` en Render →
  ami-backend → Environment → Save (redeploy automático).
- **Región:** dejá web y DB en la misma región (oregon) o la `DATABASE_URL`
  interna no conecta.
- **Un solo webhook a la vez:** Meta entrega a UNA sola Callback URL. Si tu
  compañero ya configuró otra, la de Render la reemplaza.
