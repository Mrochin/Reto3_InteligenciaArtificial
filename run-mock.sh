#!/usr/bin/env bash
set -euo pipefail
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATASYNC_HOME="$(pwd)/datasync-mock"
export JWT_SECRET="${JWT_SECRET:-cambia_este_secreto_largo_seguro}"
export ALLOWED_TABLES="${ALLOWED_TABLES:-kpi_jornadas}"
uvicorn app.main:app --reload
