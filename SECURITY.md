# Política de Seguridad

- No subir secretos (.env) al repositorio; usar GitHub Secrets.
- PRs deben pasar los gates de CI: ruff, bandit, detect-secrets, pip-audit, tests (≥80%).
- Las imágenes Docker publicadas en GHCR se escanean por vulnerabilidades (HIGH/CRITICAL bloquean publicación).