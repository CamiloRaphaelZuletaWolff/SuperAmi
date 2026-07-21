# Desplegar AMI en AWS EC2 (guía rápida, todo dockerizado)

Corre TODO en una sola instancia con `docker compose`: Postgres+pgvector + el
backend + **Caddy** (que saca y renueva el certificado HTTPS solo, gratis, con
Let's Encrypt). El link final para el webhook queda:

    https://<IP-con-guiones>.sslip.io/webhook/whatsapp

`sslip.io` resuelve `54-91-22-10.sslip.io` → `54.91.22.10` sin registrar nada.
Meta exige HTTPS con certificado válido; Caddy + sslip.io te lo da en ~30 s.

> Antes de empezar: `git push` para que el repo en GitHub tenga `Dockerfile`,
> `docker-compose.prod.yml`, `Caddyfile` y el código. El `.env` y el `.dump` NO
> están en git (bien): los copiás a la instancia por separado (Parte C).

---

## Parte A — Crear la instancia (consola web de AWS)

1. **EC2 → Launch instance.**
2. **Name:** `ami-backend`.
3. **AMI:** *Ubuntu Server 24.04 LTS* (64-bit x86). Free-tier eligible.
4. **Instance type** (definí acá si sale gratis):
   - `t2.micro` / `t3.micro` (1 GB) — **cubierto por el free tier** (750 h/mes = 24/7).
     Anda bien para AMI **con el swap de 2 GB de la Parte B**. ← elegí esta para que sea gratis.
   - `t3.small` (2 GB) — más holgado pero **NO es free tier** (~US$0.02/h ≈ US$15/mes 24/7).
5. **Key pair:** *Create new key pair* → nombre `ami-key` → tipo RSA → **Download** el `.pem` (lo usás para SSH; guardalo).
6. **Network settings → Edit → Security group** (crear uno nuevo) con estas reglas de **entrada**:
   | Tipo | Puerto | Origen | Para qué |
   |------|--------|--------|----------|
   | SSH | 22 | My IP | entrar por SSH |
   | HTTP | 80 | Anywhere (0.0.0.0/0) | reto de Let's Encrypt (obligatorio) |
   | HTTPS | 443 | Anywhere (0.0.0.0/0) | webhook de WhatsApp |
7. **Storage:** 20 GB gp3 (free tier cubre hasta 30 GB).
8. **Launch instance.**

### IP fija (Elastic IP) — importante
Si la IP cambia, se rompe el hostname sslip.io y el webhook. Fijala:

9. **EC2 → Elastic IPs → Allocate Elastic IP address → Allocate.**
10. Seleccionala → **Actions → Associate** → elegí la instancia `ami-backend` → **Associate.**
11. Anotá esa IP (ej. `54.91.22.10`). Tu hostname será `54-91-22-10.sslip.io`.

### ¿Sale gratis?

Depende de tu cuenta, pero para el hackathon es ~gratis o casi:

| Recurso | Costo |
|---------|-------|
| EC2 `t2.micro`/`t3.micro` | **Gratis** si tu cuenta tiene <12 meses (750 h/mes = 24/7). `t3.small` NO es gratis. |
| Disco EBS 20 GB | Gratis (free tier cubre 30 GB). |
| Transferencia de datos | Gratis (un chatbot mueve muy poco). |
| **Elastic IP / IPv4 pública** | ⚠️ Desde feb-2024 AWS cobra **~US$0.005/h (~US$3.60/mes)** por CADA IPv4 pública. Incluida gratis 750 h/mes **solo durante los primeros 12 meses** de la cuenta. |
| API de Gemini | Aparte de AWS (tu key free de Gemini). |

Traducción: **cuenta nueva (<12 meses) + `t2.micro` = prácticamente US$0.**
Cuenta más vieja (o el plan por créditos que AWS arrancó a mediados de 2025):
contá **~US$4–5/mes**, casi todo por la IPv4.

Protegete en 3 pasos:
- Elegí `t2.micro` (no `t3.small`).
- **Billing → Budgets → crear un budget de US$5 con alerta** (1 minuto).
- Al terminar el hackathon: **Stop/Terminate la instancia Y liberá la Elastic IP**
  (una IP sin asociar igual se cobra).

---

## Parte B — Entrar e instalar Docker (SSH)

Desde tu compu (en la carpeta donde está `ami-key.pem`):

```bash
chmod 400 ami-key.pem                       # (en Windows/PowerShell no hace falta)
ssh -i ami-key.pem ubuntu@54.91.22.10       # usá TU Elastic IP
```

Ya adentro de la instancia:

```bash
# Docker + plugin de compose en un solo paso
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
newgrp docker                                # aplica el grupo sin re-loguear

# (SOLO si usás t2.micro/t3.micro de 1 GB) swap de 2 GB para que no se quede sin RAM
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## Parte C — Traer el código, el .env y el dump

```bash
# En la instancia:
git clone https://github.com/TU_USUARIO/superAMI.git
cd superAMI
#  repo privado: git clone https://<TOKEN>@github.com/TU_USUARIO/superAMI.git
```

Desde **tu compu** (otra terminal), copiá los dos archivos que git ignora:

```bash
scp -i ami-key.pem .env ubuntu@54.91.22.10:~/superAMI/.env
scp -i ami-key.pem ami-20260721-gemini.dump ubuntu@54.91.22.10:~/superAMI/
```

De vuelta en la instancia, agregá tu hostname al `.env`:

```bash
echo "SITE_ADDRESS=54-91-22-10.sslip.io" >> .env   # usá TU IP con guiones
```

> El `DATABASE_URL` del `.env` (localhost:5434) lo pisa el compose para apuntar
> al contenedor `db`; no lo toques.

---

## Parte D — Levantar todo y cargar la base

```bash
# construir + levantar db + app + caddy
docker compose -f docker-compose.prod.yml up -d --build

# cargar la base UNA vez con el dump (embeddings Gemini ya incluidos)
docker compose -f docker-compose.prod.yml exec -T db \
  pg_restore -U ami -d ami --clean --if-exists --no-owner < ami-20260721-gemini.dump

# verificar (debe decir 1814)
docker compose -f docker-compose.prod.yml exec -T db \
  psql -U ami -d ami -c "SELECT count(*) tramites, count(embedding) con_embedding FROM tramites;"
```

Probar (dale ~30 s a Caddy para emitir el certificado la primera vez):

```bash
curl https://54-91-22-10.sslip.io/health
# {"ok":true}

curl -N -X POST https://54-91-22-10.sslip.io/chat \
  -H 'content-type: application/json' \
  -d '{"mensaje":"cuanto cuesta pagar el impuesto de mi casa"}'
```

Si el HTTPS todavía no responde, mirá el log de Caddy:
```bash
docker compose -f docker-compose.prod.yml logs caddy | tail -30
```

---

## Parte E — Conectar WhatsApp

Meta App Dashboard → WhatsApp → **Configuration → Webhook → Edit**:
- **Callback URL:** `https://54-91-22-10.sslip.io/webhook/whatsapp`
- **Verify token:** `ami2026`
- Verificar → **Subscribe** al campo `messages`.

Ese Callback URL es **el link que le pasás a tu compañero**. Es estable (no se
duerme, no cambia), a diferencia de Render free o ngrok.

---

## Operación

- **Ver logs del bot:** `docker compose -f docker-compose.prod.yml logs -f app`
- **Actualizar el token de WhatsApp** (expira ~24 h): editá `.env` en la
  instancia y `docker compose -f docker-compose.prod.yml up -d` (recrea el app).
- **Actualizar código:** `git pull && docker compose -f docker-compose.prod.yml up -d --build`
- **Apagar para no gastar:** EC2 → Instances → Stop (la Elastic IP y el disco
  quedan; al Start de nuevo, la IP sigue igual y todo levanta con `restart: unless-stopped`).

## Si Let's Encrypt falla con sslip.io (plan B: DuckDNS)

Raro, pero si Caddy no logra el certificado (rate-limit de sslip.io):
1. Registrate en [duckdns.org], creá un subdominio (ej. `ami-bo`) apuntando a tu Elastic IP.
2. En `.env`: `SITE_ADDRESS=ami-bo.duckdns.org`
3. `docker compose -f docker-compose.prod.yml up -d` y reintentá.
