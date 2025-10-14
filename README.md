
# DataSync QA Adapter – Sincronización segura con FastAPI

[![QA Workflow](https://github.com/MRochin/Reto3_InteligenciaArtificial/actions/workflows/qa.yml/badge.svg)](https://github.com/MRochin/Reto3_InteligenciaArtificial/actions/workflows/qa.yml)
[![CodeQL Analysis](https://github.com/MRochin/Reto3_InteligenciaArtificial/actions/workflows/codeql.yml/badge.svg)](https://github.com/MRochin/Reto3_InteligenciaArtificial/actions/workflows/codeql.yml)
[![Docker Publish](https://github.com/MRochin/Reto3_InteligenciaArtificial/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/MRochin/Reto3_InteligenciaArtificial/actions/workflows/docker-publish.yml)

---

## 🧩 Descripción general

**DataSync QA Adapter** es un servicio **FastAPI** diseñado para sincronizar información entre bases de datos **SQL Server** y **MySQL** con un enfoque en **seguridad, trazabilidad y aseguramiento de calidad automatizado (QA)**.  
Integra autenticación **JWT**, validaciones **Pydantic**, **Rate Limiting**, y un **modo Mock** para pruebas sin base de datos real.  

Además, incluye un pipeline completo **CI/CD** con herramientas de IA y seguridad:

- **Ruff + Bandit + Detect-Secrets + Pip-Audit + CodeQL + Trivy**  
- **Pruebas unitarias automatizadas (pytest + coverage ≥80%)**  
- **Despliegue automático a GHCR (GitHub Container Registry)**  
- **Actualizaciones automáticas con Dependabot**  

---

## 🚀 Despliegue con Docker / Docker Compose

### 🧱 Opción A: Docker Compose (recomendada)
1. Copia `.env.example` a `.env` y ajusta variables (`HOST_DATASYNC_PATH`, `JWT_SECRET`, `ALLOWED_TABLES`).
2. Levanta el servicio:
   ```bash
   docker compose up --build -d
   ```
3. Verifica el estado:
   ```bash
   curl http://localhost:8000/health
   ```

> El DataSync del host se monta **de solo lectura** en `/app/datasync`.  
> Si requieres escritura para logs, cambia `:ro` por `:rw`.

---


## 🧪 Modo Mock – Simulación sin Bases de Datos

Permite validar todo el adapter (**JWT**, rate limit, listas blancas, `/logs`, `/status`, `/sync`) **sin depender de SQL Server ni MySQL**.

### 🔎 Prueba rápida

# health
```bash 
curl http://localhost:8000/health
```
```bash 
# login → token
TOKEN=$(curl -s -X POST -d "username=admin&password=adminadmin" http://localhost:8000/auth/login | jq -r .access_token)
```

# status
```bash 
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/status
```
# sync (mock simula éxito)
```bash 
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json"   -d '{"tables":["kpi_jornadas"],"dry_run":true}' http://localhost:8000/sync
```

---

## ⚙️ CI/CD y QA Segura

El proyecto implementa un flujo completo de integración continua (CI/CD) para asegurar la calidad y seguridad del código:

### 🧪 **1. QA Workflow (`.github/workflows/qa.yml`)**
Ejecuta en cada *push* o *pull request*:
- `ruff` → estilo y convenciones.  
- `bandit` → análisis estático de seguridad.  
- `detect-secrets` → búsqueda de credenciales expuestas.  
- `pip-audit` → vulnerabilidades en dependencias.  
- `pytest` → pruebas unitarias (mínimo 80% cobertura).  
- Falla automáticamente si algún gate no se cumple.

### 🔬 **2. CodeQL (`.github/workflows/codeql.yml`)**
Escanea el código fuente (Python) en busca de patrones de vulnerabilidad.  
Corre en el branch `main`, en PRs y de forma semanal.

### 🐳 **3. Docker Publish (`.github/workflows/docker-publish.yml`)**
Construye y publica imágenes Docker firmadas en GHCR (`ghcr.io/MRochin/Reto3_InteligenciaArtificial`).  
Incluye escaneo de vulnerabilidades de imagen con **Trivy** (HIGH/CRITICAL bloquean publicación).

### 🧠 **4. Dependabot & Security**
- `dependabot.yml` → actualizaciones automáticas de pip y GitHub Actions.  
- `SECURITY.md` → política de seguridad con lineamientos del pipeline.  

> Todos los flujos CI/CD se ejecutan en `main`, y los resultados se reflejan en los **badges** del encabezado.

---

## ⚙️ Comandos útiles

| Acción | Comando |
|--------|----------|
| 🧪 Ejecutar pruebas | `pytest --cov=app --cov-report=term-missing` |
| 🧰 Linter | `ruff check app` |
| 🔒 Análisis de seguridad | `bandit -r app -ll` |
| 🧼 Auditoría de dependencias | `pip-audit` |
| 🧬 Ejecutar CI local | `pytest && ruff check app && bandit -r app && pip-audit` |
| 🐳 Construir imagen Docker | `docker build -t datasync-qa-adapter .` |
| 🚀 Correr modo Mock local | `./run-mock.sh` |

---

## 🔐 Seguridad y calidad

- Pipelines CI/CD con **SAST**, **SCA** y **tests automatizados**.  
- **Cobertura mínima 80%** como gate obligatorio.  
- Revisión automática de dependencias y secretos.  
- Imágenes Docker escaneadas por vulnerabilidades (Trivy).  
- Gestión segura de variables con `.env` y **GitHub Secrets**.  

---

## 🧠 Arquitectura general

```
📦 DataSync QA Adapter
├── app/
│   ├── main.py              → Entrypoint FastAPI
│   ├── auth.py              → JWT + bcrypt
│   ├── schemas.py           → Validaciones Pydantic
│   └── settings.py          → Configuración y rate limits
│
├── datasync-mock/           → Motor simulado (sin BD)
│   └── src/sync_engine.py
│
├── tests/                   → Pruebas automatizadas (pytest)
├── docker-compose.yml       → Entorno Docker
├── Dockerfile               → Imagen base
├── .env.example             → Variables de entorno (ejemplo)
├── .github/workflows/       → CI/CD pipelines (QA, CodeQL, Docker)
└── README.md                → Documentación completa
```

---

## 🧑‍💻 Autor y mantenimiento

**Desarrollado por:** [MRochin](https://github.com/MRochin)  
**Repositorio:** [Reto3_InteligenciaArtificial](https://github.com/MRochin/Reto3_InteligenciaArtificial)  
**Licencia:** MIT  
**Última actualización:** Octubre 2025
