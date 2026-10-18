# AMI — Asistente de Trámites Bolivia

[![CI](https://github.com/CamiloRaphaelZuletaWolff/SuperAmi/actions/workflows/ci.yml/badge.svg)](https://github.com/CamiloRaphaelZuletaWolff/SuperAmi/actions/workflows/ci.yml)

**Demo:** <!-- reemplazar tras el deploy --> https://ami-web.vercel.app · también por WhatsApp

Asistente que responde preguntas sobre trámites del Estado boliviano (qué
necesito, cuánto cuesta, dónde voy) con RAG sobre el dataset abierto
[tramites-bo](https://github.com/datosbolivia/tramites-bo) más trámites
scrapeados del GAMLP La Paz. Se usa por WhatsApp (Meta Cloud API) o por la web.

```
 WhatsApp ──webhook──┐                       ┌── Gemini (filtros, síntesis, embeddings)
                     ▼                       │
 Web (Next.js) ──SSE──► FastAPI ──► pipeline ┼── Postgres + pgvector (HNSW, 1.814 trámites,
   Vercel              Render       RAG      │    grafo de 4.327 relaciones) · Neon
                                             └── live fetch de la página oficial (fallback)
```

El pipeline: filtros inferidos por un modelo liviano → búsqueda vectorial
acotada al dominio → **gate de confianza determinista** (claro / ambiguo →
pregunta aclaratoria / lejano → consulta en vivo) → síntesis anclada a la ficha
oficial. La web muestra ese veredicto y los candidatos comparados en cada respuesta.

Docs: `DEPLOY.md` (deploy gratuito paso a paso) · `DECISIONS.md` (decisiones y
evals) · `ROADMAP.md` · `CLAUDE.md` (spec original).

## Requisitos

- Python 3.11+, Docker + docker compose, Node 20+ (frontend)
- API key gratuita de [Google AI Studio](https://aistudio.google.com/apikey) (`PROVIDER=gemini`)
  — alternativas: NVIDIA Build (`nvidia`), Anthropic + Voyage (`anthropic`), Ollama (`ollama`)

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env    # completar GEMINI_API_KEY
docker compose up -d    # Postgres+pgvector en localhost:5434
```

> En Windows el intérprete del venv es `venv\Scripts\python.exe` (y
> `venv\Scripts\pip.exe`); reemplazar `.venv/bin/...` por esa ruta en todos
> los comandos.

## Cargar los datos (una vez, ~3-5 min)

> ¿Recibiste `ami-YYYYMMDD.dump`? **No reproceses**: importá el dump
> (embeddings + grafo de relaciones ya calculados) y saltá esta sección.
> Ver **[COMPARTIR.md](COMPARTIR.md)** → `scripts/import_db.sh ami-YYYYMMDD.dump`.

```bash
.venv/bin/python -m ingest.load
```

Descarga los ~1,700 trámites, extrae costos faltantes con el modelo potente
(llama-3.3-70b), genera embeddings (bge-m3) y los guarda en Postgres.

## Correr el API

```bash
.venv/bin/uvicorn api.main:app --port 8000
```

## Usar el chat

```bash
curl -N -X POST localhost:8000/chat -H 'content-type: application/json' \
  -d '{"mensaje": "¿qué necesito para sacar mi carnet de identidad?"}'
```

La respuesta es un stream SSE. Eventos: `answer` (deltas de texto y un
`{"done": true, "tramite_ids": [...]}` final), `clarification` (pregunta
aclaratoria — respondé mandando otro mensaje con el mismo
`conversation_id`), `error`. Con `"traza": true` en el body llega además un
evento `trace` (veredicto del gate, umbrales, filtros y candidatos con su
distancia). Otros endpoints: `GET /tramites/{id}` (ficha), `GET /stats`,
`GET /health`. `/chat` tiene límite por IP (`CHAT_RATE_LIMIT_PER_MIN`).

## Frontend web

```bash
cd frontend
cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install && npm run dev   # http://localhost:3000
```

Seguimiento de conversación:

```bash
# el primer evento trae conversation_id; usarlo en el siguiente turno
curl -N -X POST localhost:8000/chat -H 'content-type: application/json' \
  -d '{"mensaje": "el de propiedad", "conversation_id": "<uuid>"}'
```

## Tests

```bash
.venv/bin/pytest                                # unit + integración (necesita docker)
.venv/bin/python tests/eval_retrieval.py        # eval de retrieval con frases reales
```

## Sync semanal

El dataset se actualiza los domingos. Correr:

    venv/Scripts/python.exe -m ingest.sync --dry-run   # ver qué cambiaría
    venv/Scripts/python.exe -m ingest.sync             # aplicar

Idempotente: solo procesa registros nuevos/modificados (diff por fechaActualización)
y marca bajas como `activo=false`. Agendable con cron / Programador de tareas de Windows.

## Calibración del gate

    venv/Scripts/python.exe tests/verificar_eval.py    # etiquetas del eval vs DB
    venv/Scripts/python.exe tests/eval_retrieval.py    # corrida informativa
    venv/Scripts/python.exe tests/calibrar_gate.py     # barrido de umbrales

Tras una sesión con usuarios, las frases quedan en `consultas_log`; incorporarlas
al eval (`tests/eval_dataset.py`) y re-correr el barrido.

## Providers open-source (opcional)

    venv/Scripts/python.exe -m pip install -r requirements-oss.txt
    # en .env: PROVIDER=ollama (ver .env.example)

NIM sigue siendo el default. Comparar calidad antes de migrar:

    venv/Scripts/python.exe tests/eval_comparativo.py --embeddings
    venv/Scripts/python.exe tests/eval_comparativo.py --sintesis 5
