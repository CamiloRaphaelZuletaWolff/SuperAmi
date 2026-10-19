# Deploy de AMI 100% gratis (Neon + Render + Vercel + WhatsApp)

Guía paso a paso, pensada para hacerla de corrido la primera vez (≈ 60–90 min).
Cada paso dice **dónde hacer clic** y **cómo verificar** que salió bien antes de
seguir.

---

## 0. Arquitectura y costos

```
                ┌──────────────────────────┐
  Navegador ───►│ Vercel (Hobby)           │  frontend/  (Next.js, estático)
                │ https://ami-web.vercel.app│
                └────────────┬─────────────┘
                             │ fetch + SSE (CORS)
  WhatsApp  ──webhook──┐     ▼
  (Meta Cloud API)     ▼ ┌──────────────────────────┐      ┌───────────────────┐
                         │ Render (free, Docker)    │─────►│ Neon (free)       │
                         │ FastAPI  ami-backend     │ SQL  │ Postgres + vector │
                         └────────────┬─────────────┘      └───────────────────┘
                                      │ HTTPS
                                      ▼
                              Gemini API (free tier)
```

| Servicio | Plan | Qué aloja | Límites que importan |
|---|---|---|---|
| **Vercel** Hobby | gratis | Frontend Next.js | Uso no comercial. 100 GB de transferencia/mes. |
| **Render** Free | gratis | Backend FastAPI (Docker) | 512 MB RAM. **Se duerme a los 15 min sin tráfico** (el primer request tarda ~50 s). **750 horas/mes por workspace**, compartidas con tus otros backends free. Sin shell. |
| **Neon** Free | gratis | Postgres 17 + pgvector | 0,5–1 GB por proyecto (la base de AMI ocupa ~30 MB). El cómputo se suspende tras 5 min sin uso y despierta en <1 s. **No expira.** |
| **Gemini API** | free tier | LLM + embeddings | Cuota por minuto y por día; si se supera devuelve 429. |
| **Meta WhatsApp Cloud API** | gratis | Bot de WhatsApp | El número de prueba solo escribe a 5 números que agregues. Las respuestas dentro de las 24 h de un mensaje del usuario son gratis. |
| **GitHub Actions** | gratis | CI | Ilimitado para repos públicos. |

> **¿Por qué Neon y no la Postgres de Render?** La Postgres gratuita de Render
> **se borra a los 30 días**. Neon no expira y trae `pgvector`.

> **¿Y las 750 horas de Render?** Un servicio encendido todo el mes consume 744 h.
> Como los servicios free se duermen solos cuando nadie los usa, varios backends
> caben en las 750 h. **No configures "keep-alive"** (pings cada 10 min): con
> cuatro proyectos se agotan las horas y Render suspende todo hasta el mes siguiente.
> El frontend ya muestra un aviso de "despertando el servidor".

---

## 1. Antes de empezar: seguridad (OBLIGATORIO)

El repo `SuperAmi` es **público** y versiones anteriores de `.env.example`
contenían credenciales reales de WhatsApp. Ya están reemplazadas por
placeholders, pero **siguen en el historial de git**, así que hay que invalidarlas:

1. **Rotar el App Secret de Meta.** [developers.facebook.com/apps](https://developers.facebook.com/apps)
   → tu app → **Configuración de la app → Básica** → *Clave secreta de la app*
   → **Restablecer**. Guarda la nueva: será `WHATSAPP_APP_SECRET`.
2. **El token de WhatsApp viejo** ya expiró. Igual vas a generar uno permanente
   nuevo en el paso 7.
3. **Cambiar el verify token.** `ami2026` era público. Inventa uno nuevo y largo
   (paso 2).
4. **Mover `ami-key.pem` fuera de la carpeta del repo** (está ignorado, pero es la
   llave SSH de la EC2 y no debe vivir ahí). Si esa instancia EC2 sigue
   encendida en alguna cuenta de AWS, termínala.
5. *(Opcional)* Limpiar el historial con
   [`git filter-repo`](https://github.com/newren/git-filter-repo). Una vez
   rotados los secretos ya no es urgente.

Y sube los cambios pendientes (el `.gitignore` con `*.pem` todavía no está commiteado):

```bash
git add .gitignore .env.example render.yaml README.md DEPLOY.md api db tests frontend .github
git rm DEPLOY-render.md
git commit -m "feat: frontend web, CORS, rate limit, deploy gratuito (Neon+Render+Vercel) y CI"
git push origin main
```

---

## 2. Generar los secretos propios

Solo necesitas uno: el **verify token** del webhook de WhatsApp (un texto
aleatorio que tú inventas y pegas en Render y en Meta).

PowerShell:

```powershell
-join ((48..57)+(97..122) | Get-Random -Count 40 | ForEach-Object {[char]$_})
```

Git Bash / Linux / macOS:

```bash
openssl rand -hex 20
```

Guárdalo como `WHATSAPP_VERIFY_TOKEN`.

**API key de Gemini:** [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
→ **Create API key** → elige (o crea) un proyecto de Google Cloud → copia la key.
Es `GEMINI_API_KEY`. No necesitas activar facturación.

---

## 3. Base de datos en Neon

### 3.1 Crear el proyecto

1. Entra a [neon.tech](https://neon.tech) → **Sign up** con GitHub.
2. **Create project**:
   - *Project name*: `ami`
   - *Postgres version*: la que venga por defecto (17)
   - *Region*: **AWS US West 2 (Oregon)**, la misma región que Render, para menos latencia.
3. Al terminar, en el **Dashboard** → botón **Connect**:
   - *Branch*: `main`, *Database*: `neondb`, *Role*: `neondb_owner`
   - **Desactiva "Connection pooling"**. Para `pg_restore` conviene la conexión directa, cuyo host no tiene `-pooler`.
   - Copia la cadena. Se ve así:
     `postgresql://neondb_owner:XXXX@ep-algo-123456.us-west-2.aws.neon.tech/neondb?sslmode=require`

Esa cadena es tu **`DATABASE_URL`**. La usarás para el restore y para Render.

### 3.2 Activar pgvector

Neon → **SQL Editor** → pega y ejecuta:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 3.3 Cargar el dump (una sola vez)

El dump `ami-20260721-gemini.dump` (11 MB, **no está en git**) ya trae los
1.814 trámites con embeddings Gemini y el grafo de relaciones. **Usa ese y no el
de bge-m3**: mezclar embeddings de modelos distintos rompe la búsqueda en silencio.

**Opción A: con Docker Desktop** (ábrelo primero y espera a que diga *Running*).
En PowerShell, dentro de `C:\Users\caezu\Desktop\superAMI`:

```powershell
$env:NEON_URL = "postgresql://neondb_owner:XXXX@ep-algo-123456.us-west-2.aws.neon.tech/neondb?sslmode=require"
docker run --rm -v "${PWD}:/data" postgres:17 pg_restore --no-owner --no-acl --clean --if-exists -d $env:NEON_URL /data/ami-20260721-gemini.dump
```

> El `-v` monta la carpeta actual dentro del contenedor como `/data`. No uses
> `Get-Content ... |` en PowerShell 5.1: corrompe archivos binarios.

**Opción B: sin Docker.** Instala solo las herramientas de cliente de
PostgreSQL 17 ([enterprisedb.com/downloads](https://www.enterprisedb.com/downloads/postgres-postgresql-downloads)
→ en el instalador marca únicamente **Command Line Tools**) y corre:

```powershell
& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" --no-owner --no-acl --clean --if-exists -d $env:NEON_URL .\ami-20260721-gemini.dump
```

Es normal ver avisos como `role "ami" does not exist` o `must be owner of extension vector`. Los errores reales cortan el restore con `pg_restore: error:` al final.

### 3.4 Verificar y limpiar datos personales

En el **SQL Editor** de Neon:

```sql
SELECT count(*) AS tramites, count(embedding) AS con_embedding FROM tramites;  -- 1814 | 1814
SELECT count(*) FROM dominio_mvp;                                              -- > 0
```

El dump incluye conversaciones y consultas de la sesión de pruebas con
usuarios. Para una demo pública, bórralas:

```sql
TRUNCATE conversaciones, consultas_log;
```

---

## 4. Backend en Render

1. [dashboard.render.com](https://dashboard.render.com) → **Sign up** con GitHub
   (si te pregunta, da acceso al repo `SuperAmi`).
2. **New +** → **Blueprint**.
3. Elige el repo **SuperAmi**, rama **main**. Render lee `render.yaml` y muestra
   el servicio `ami-backend`.
4. Te pide los valores marcados `sync: false`:

   | Variable | Valor |
   |---|---|
   | `DATABASE_URL` | la cadena de Neon del paso 3.1 (con `?sslmode=require`) |
   | `GEMINI_API_KEY` | tu key de AI Studio |
   | `CORS_ORIGINS` | por ahora `http://localhost:3000`; la cambias en el paso 6 |
   | `WHATSAPP_VERIFY_TOKEN` | el que generaste en el paso 2 |
   | `WHATSAPP_TOKEN` | déjalo vacío por ahora (paso 7) |
   | `WHATSAPP_PHONE_NUMBER_ID` | vacío por ahora |
   | `WHATSAPP_APP_SECRET` | el **nuevo** App Secret del paso 1 |

   > **Obligatorios para WhatsApp:** sin `WHATSAPP_VERIFY_TOKEN` Meta no puede
   > verificar el webhook (403), y sin `WHATSAPP_APP_SECRET` el backend rechaza
   > **todos** los POST del webhook (401): sin firma, cualquiera podría gastar tu
   > cuota de Gemini. `WHATSAPP_ALLOW_UNSIGNED=true` desactiva esa validación y es
   > **solo para desarrollo local**; nunca la agregues en Render.
   > `WHATSAPP_RATE_LIMIT_PER_MIN` (6 por defecto, ya en `render.yaml`) limita los
   > mensajes por minuto de cada número.

5. **Apply**. Render construye la imagen Docker (3–5 min). Míralo en
   `ami-backend` → **Logs**. Está listo cuando ves
   `Uvicorn running on http://0.0.0.0:10000` y el estado pasa a **Live**.
6. Copia la URL pública arriba a la izquierda, algo como
   `https://ami-backend-xxxx.onrender.com`. **Cópiala tal cual**, porque Render
   puede agregar un sufijo aleatorio.

### Verificar

```bash
curl https://ami-backend-xxxx.onrender.com/health
# {"ok":true}

curl https://ami-backend-xxxx.onrender.com/stats
# {"tramites":1814,"en_dominio":...,"entidades":...,"relaciones":...}

curl -N -X POST https://ami-backend-xxxx.onrender.com/chat \
  -H "content-type: application/json" \
  -d '{"mensaje":"cuanto cuesta el certificado catastral","traza":true}'
# event: trace ... event: answer ... {"done": true, "tramite_ids": [...]}
```

> En PowerShell usa `curl.exe` (no `curl`) y escapa las comillas del JSON:
> `curl.exe -N -X POST URL -H "content-type: application/json" -d '{\"mensaje\":\"hola\"}'`

---

## 5. Frontend en Vercel

1. [vercel.com](https://vercel.com) → **Sign up** con GitHub.
2. **Add New… → Project** → **Import** del repo **SuperAmi**.
3. En *Configure Project*:
   - **Root Directory** → **Edit** → elige `frontend`. Es clave, porque el Next.js vive en esa subcarpeta.
   - *Framework Preset*: Next.js (lo detecta solo).
   - **Environment Variables**: `NEXT_PUBLIC_API_URL` =
     `https://ami-backend-xxxx.onrender.com`, **sin `/` final**.
4. **Deploy** (≈1 min). Vercel te da `https://superami-xxxx.vercel.app`.
5. *(Opcional)* Cambia el nombre: **Settings → Domains → Edit** →
   `ami-bolivia.vercel.app` (si está libre).

> `NEXT_PUBLIC_*` se incrusta en el build. Si cambias la URL del backend, hay que
> **redeployar**: Deployments → ⋯ → **Redeploy**.

---

## 6. Conectar frontend y backend (CORS)

1. Render → `ami-backend` → **Environment** → `CORS_ORIGINS` → pega la URL
   exacta de Vercel, sin `/` final. Ejemplo: `https://ami-bolivia.vercel.app`.
   Para permitir varias, sepáralas con comas:
   `https://ami-bolivia.vercel.app,http://localhost:3000`
2. **Save Changes**. Render redeploya solo, en ~2 min.
3. Abre la web, toca un ejemplo. Deberías ver:
   - un aviso de "Despertando el servidor" si estaba dormido;
   - la respuesta escribiéndose en vivo y un **sello** ("Encontrado", "Por aclarar"…);
   - a la derecha, el **Expediente** con la ficha (costo, requisitos marcables) y
     "Cómo lo encontré", con los candidatos y sus distancias.

---

## 7. WhatsApp (Meta Cloud API)

### 7.1 App y número de prueba

1. [developers.facebook.com](https://developers.facebook.com) → **My Apps** →
   tu app existente, o **Create App** → caso de uso *Other* → tipo **Business**.
2. En el panel de la app → **Add product** → **WhatsApp** → **Set up**. Meta crea
   una cuenta de WhatsApp Business de prueba y un **número de prueba gratuito**.
3. **WhatsApp → API Setup**:
   - copia el **Phone number ID**: es `WHATSAPP_PHONE_NUMBER_ID`;
   - en **To** → **Manage phone number list** → agrega tu número y el de quien
     vaya a probar (máximo 5; cada uno recibe un código de verificación).

### 7.2 Token permanente (no el de 24 h)

El token de *API Setup* vence en 24 h. Esto fue lo que rompió el bot en julio.
Crea uno permanente:

1. [business.facebook.com/settings](https://business.facebook.com/settings) → elige
   la cuenta de negocio de la app.
2. **Users → System users → Add** → nombre `ami-bot`, rol **Admin** → crear.
3. Con `ami-bot` seleccionado → **Assign assets**:
   - **Apps** → tu app → *Full control*;
   - **WhatsApp accounts** → tu cuenta → *Full control*.
4. **Generate new token** → elige la app → *Token expiration*: **Never** →
   permisos `whatsapp_business_messaging` y `whatsapp_business_management` →
   **Generate**. Copia el token (no se vuelve a mostrar): es `WHATSAPP_TOKEN`.

### 7.3 Cargar en Render y conectar el webhook

1. Render → `ami-backend` → **Environment** → completa `WHATSAPP_TOKEN` y
   `WHATSAPP_PHONE_NUMBER_ID` → **Save Changes**.
2. **Despierta el backend antes de verificar.** Abre
   `https://ami-backend-xxxx.onrender.com/health` y espera `{"ok":true}`. Meta
   espera la respuesta solo unos segundos.
3. Meta → **WhatsApp → Configuration → Webhook → Edit**:
   - **Callback URL**: `https://ami-backend-xxxx.onrender.com/webhook/whatsapp`
   - **Verify token**: tu `WHATSAPP_VERIFY_TOKEN`
   - **Verify and save**.
4. En **Webhook fields** → `messages` → **Subscribe**.
5. Desde un número de la lista, escribe "hola" al número de prueba. Llega la
   bienvenida de AMI.

> **Cold start y WhatsApp:** si el backend dormía, el primer mensaje tarda ~1 min.
> Meta reintenta el webhook y el bot deduplica por `message_id`, así que no
> responde doble.
>
> **Para el portafolio:** como el número de prueba solo habla con 5 números, el
> demo público es la **web**. Graba un video corto o un GIF del bot en WhatsApp y
> ponlo en el README.

---

## 8. CI con GitHub Actions

`.github/workflows/ci.yml` corre en cada push y PR:

| Job | Qué hace |
|---|---|
| **Backend** | Levanta `pgvector/pgvector:pg16` como servicio, carga `db/schema.sql` y corre **toda** la suite de pytest, incluidos los tests de integración contra Postgres real. Los LLM usan fakes: ninguna key viaja al CI. |
| **Frontend** | `npm ci` → ESLint → `tsc --noEmit` → Vitest → `next build`. |

No necesita secretos. Si un job falla: pestaña **Actions** → la ejecución en
rojo → el paso en rojo muestra el log. El badge ya está en el README.

**El deploy no pasa por Actions:** Render y Vercel redeployan solos con cada
push a `main`. Si quieres que solo se publique lo que pasa el CI, en Render →
*Settings* → **Auto-Deploy: After CI Checks Pass**.

---

## 9. Checklist final

- [ ] `/health` responde `{"ok":true}`
- [ ] `/stats` muestra 1814 trámites
- [ ] La web carga, responde un ejemplo y muestra sello + ficha + traza
- [ ] Una pregunta ambigua ("papel del auto") devuelve una aclaración con sello "Por aclarar"
- [ ] Más de 12 mensajes en un minuto devuelven el aviso de límite (429)
- [ ] WhatsApp: "hola" → bienvenida; una pregunta real → respuesta
- [ ] La Action **CI** está en verde
- [ ] README: reemplazaste la URL de la demo por la real

---

## 10. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| La web dice "No pude conectar con el servidor" | CORS o URL mal escrita | `CORS_ORIGINS` debe ser idéntico al dominio de Vercel (https, sin `/` final). `NEXT_PUBLIC_API_URL` sin `/` final y redeploy en Vercel. Mira la consola del navegador (F12). |
| Render: `connection refused` / `SSL required` | `DATABASE_URL` sin `?sslmode=require` | Agrégalo al final de la cadena de Neon. |
| `/chat` responde "Tuve un problemita" | Error de Gemini o de la base | Render → Logs. `429 RESOURCE_EXHAUSTED` = cuota de Gemini agotada (espera o usa otra key). `relation "tramites" does not exist` = falta el restore (paso 3.3). |
| Respuestas sin sentido / siempre "no encontré" | Dump de bge-m3 con embeddings de Gemini | Restaura `ami-20260721-gemini.dump` con `--clean`. |
| `pg_restore: error: unsupported version` | Cliente más viejo que el dump | Usa la imagen `postgres:17` o las herramientas de cliente 17. |
| Meta: "The callback URL or verify token couldn't be validated" | Backend dormido o token distinto | Despierta `/health` primero; compara el token letra por letra. |
| WhatsApp recibe pero no responde (401 en logs) | `WHATSAPP_TOKEN` vencido o sin permisos | Token de System User con expiración *Never* (paso 7.2). |
| `firma inválida` en logs | `WHATSAPP_APP_SECRET` viejo | Pon el App Secret actual (el rotado en el paso 1). |
| `WHATSAPP_APP_SECRET no configurado` en logs, webhook 401 | Falta el App Secret | Cárgalo en Render → Environment. El webhook ya no acepta POST sin firma. |
| `/chat` responde 429 a todo el mundo | El límite por IP agrupa a todos | Revisa que llegue `X-Forwarded-For` con la IP pública del cliente (se usa la IP pública más a la derecha, la que agrega el proxy de Render). |
| Render suspendido a fin de mes | Se acabaron las 750 h del workspace | Quita cualquier keep-alive; espera al día 1 o pasa un servicio a Starter. |
| Build de Vercel falla con "No Next.js version detected" | Root Directory no es `frontend` | Settings → General → Root Directory = `frontend`. |

---

## 11. Mantenimiento

- **Sync semanal del dataset** (opcional): desde tu PC, con `DATABASE_URL`
  apuntando a Neon: `python -m ingest.sync --dry-run` y luego sin `--dry-run`.
  Usa la misma `GEMINI_API_KEY` para que los embeddings nuevos sean compatibles.
- **Neon** suspende el cómputo sin uso y lo despierta solo. No hay que hacer nada.
- **Rotar secretos:** cámbialos en Render → Environment. Se redeploya solo.
  Al rotar `WHATSAPP_APP_SECRET` las conversaciones de WhatsApp en curso empiezan
  de cero (su id es un HMAC del número con ese secret, para no guardar el
  teléfono en claro).
- **Datos personales:** lo que escribe la gente queda en `conversaciones` (se
  borra a las 24 h) y en `consultas_log` (se borra a los 90 días). La limpieza
  corre en cada arranque del backend. Los números de WhatsApp no se guardan en
  claro y en los logs aparecen enmascarados (`***1234`).
- **Dependencias:** `requirements.txt` está fijado. Para actualizar, cambia la
  versión, corre `pytest` y `pip-audit -r requirements.txt`; en el frontend
  `npm audit --omit=dev`.
