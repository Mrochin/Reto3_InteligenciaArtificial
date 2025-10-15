FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencias
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Código app
COPY app /app/app

# (Opcional) este archivo debe EXISTIR o la build fallará.
# Si no lo usas, elimina la línea siguiente o crea un archivo vacío en la raíz.
# COPY .cursorrules /app/.cursorrules

# Documentación
COPY README.md /app/README.md

# 👉 Tests y configs de pytest (para que existan dentro de la imagen)
COPY tests /app/tests
COPY pytest.ini /app/pytest.ini
COPY .coveragerc /app/.coveragerc


# Herramientas IA y prompts (necesarios para el generador de tests)
COPY tools /app/tools
COPY prompts /app/prompts


# Variables por defecto dentro del contenedor
ENV DATASYNC_HOME=/app/datasync
ENV JWT_SECRET=change_me_please

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]