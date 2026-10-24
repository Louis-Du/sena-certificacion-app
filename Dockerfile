FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY app ./app

# Etapa de pruebas: agrega la configuracion de pytest, las pruebas y los
# archivos de ejemplo. Se construye aparte para no incluirlos en la imagen
# final de la API:
#   docker build --target test -t sena-certificacion-app-tests .
#   docker run --rm sena-certificacion-app-tests
# Las pruebas E2E quedan excluidas por pytest.ini (--ignore=tests/e2e).
FROM base AS test

COPY pytest.ini ./
COPY tests ./tests
COPY archivos_prueba ./archivos_prueba

CMD ["pytest"]

# Imagen final de la API (etapa por defecto al construir sin --target).
FROM base AS runtime

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
