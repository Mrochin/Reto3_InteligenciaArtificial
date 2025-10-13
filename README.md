# DataSync QA Adapter — FastAPI

(Sección Docker se agregará abajo)


---

## 🚀 Despliegue con Docker / Docker Compose

### Opción A) Docker Compose (recomendada)
1) Copia `.env.example` a `.env` y ajusta variables (en especial `HOST_DATASYNC_PATH`, `JWT_SECRET` y `ALLOWED_TABLES`).
2) Levanta el servicio:
```bash
docker compose up --build -d
```
3) Verifica salud:
```bash
curl http://localhost:${APP_PORT:-8000}/health
```

> El DataSync del host se monta **de solo lectura** en `/app/datasync`. Si requieres escritura para logs, cambia `:ro` por `:rw`.

### Opción B) Dockerfile (adapter mínimo)
```bash
docker build -t datasync-qa-adapter:latest .
docker run --rm -p 8000:8000   -e DATASYNC_HOME=/app/datasync   -e JWT_SECRET="cambia_este_secreto_largo_seguro"   -v /Users/mrochin/DataSync:/app/datasync:ro   datasync-qa-adapter:latest
```

### Opción C) Dockerfile.full (con ODBC para SQL Server)
Si tu `sync_engine` usa `pyodbc` y requiere el **Driver ODBC 18** para SQL Server dentro del contenedor:
```bash
docker build -t datasync-qa-adapter:odbc -f Dockerfile.full .
docker run --rm -p 8000:8000   -e DATASYNC_HOME=/app/datasync   -e JWT_SECRET="cambia_este_secreto_largo_seguro"   -v /Users/mrochin/DataSync:/app/datasync:ro   datasync-qa-adapter:odbc
```

> Nota: Asegura conectividad de red desde el contenedor hacia tus DBs (SQL Server/MySQL).


---

## 🧪 Modo B — Simulación sin BDs (Mock)

Este modo permite **probar todo el adapter** (JWT, rate limit, whitelist, `/logs`, `/status`, `/sync`) **sin** depender de SQL Server/MySQL.

### Ejecutar en local (sin Docker)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Apunta el adapter al mock incluido en este repo
export DATASYNC_HOME="$(pwd)/datasync-mock"
export JWT_SECRET="cambia_este_secreto_largo_seguro"
export ALLOWED_TABLES="kpi_jornadas"

uvicorn app.main:app --reload
```

Prueba rápida:
```bash
# health
curl http://localhost:8000/health

# login → token
TOKEN=$(curl -s -X POST -d "username=admin&password=adminadmin" http://localhost:8000/auth/login | jq -r .access_token)

# status (responde 'healthy-mock')
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/status

# sync (mock simula éxito)
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json"   -d '{"tables":["kpi_jornadas"],"dry_run":true}' http://localhost:8000/sync
```

### Ejecutar con Docker Compose (sin BDs)
1) Copia `.env.example` a `.env`.
2) Ajusta `.env` para que `HOST_DATASYNC_PATH` apunte al mock del repo:
```
HOST_DATASYNC_PATH=./datasync-mock
JWT_SECRET=cambia_este_secreto_largo_seguro
ALLOWED_TABLES=kpi_jornadas
```
3) Levanta el adapter:
```bash
docker compose up --build -d
curl http://localhost:${APP_PORT:-8000}/health
```
> El contenedor montará `./datasync-mock` en `/app/datasync`, por lo que el adapter importará `src/sync_engine.py` del mock automáticamente.
