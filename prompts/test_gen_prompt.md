# Generación de pruebas con IA — FastAPI (pytest)

## Objetivo
Genera **nuevas** pruebas con `pytest` para una API en FastAPI que **aumenten la cobertura** y validen:
- Casos borde no cubiertos
- Ramas de error (auth inválida/expirada, validación, fallbacks)
- Cobertura de rutas y modelos Pydantic

## Contexto (NO editar)
El orquestador insertará este JSON con cobertura, rutas, modelos **y fragmentos de código fuente** (verdad única):
```json
{{CONTEXT_JSON}}