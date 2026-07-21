# Imagen de runtime para el backend AMI (FastAPI + uvicorn).
# Usa solo requirements.txt (proveedor Gemini/OpenAI-compat) -> imagen liviana,
# sin torch. La DB (Postgres+pgvector) es un servicio aparte (Render managed DB).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Render inyecta $PORT; en local cae a 8000.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
