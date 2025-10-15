#!/usr/bin/env python3
"""
ai_test_runner.py (versión reforzada)
- Ejecuta pytest con cobertura (coverage.xml)
- Extrae rutas FastAPI y modelos Pydantic
- Inyecta fragmentos del código fuente al LLM (contexto real)
- Genera tests en tests/ai_generated/*.py
- Post-procesa tests (auto-fixes) para evitar fallas comunes
- Re-ejecuta pytest y compara cobertura antes/después
- Itera con auto-crítica (lee fallos y antipatrón y realimenta al LLM)
"""

import os
import re
import sys
import json
import pathlib
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any
import ast

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
TESTS_DIR = ROOT / "tests"
AIGEN_DIR = TESTS_DIR / "ai_generated"
PROMPTS_DIR = ROOT / "prompts"
PROMPT_FILE = PROMPTS_DIR / "test_gen_prompt.md"

MAX_SOURCE_CHARS = int(os.getenv("MAX_SOURCE_CHARS", "12000"))
MAX_ITERS = int(os.getenv("MAX_ITERS", "2"))
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# ---------------- Utils ----------------

def run(cmd: str, check=True) -> str:
    print(f"$ {cmd}")
    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if check and p.returncode != 0:
        print(p.stdout)
        print(p.stderr)
        raise SystemExit(p.returncode)
    return (p.stdout or "") + (p.stderr or "")

def ensure_dirs():
    AIGEN_DIR.mkdir(parents=True, exist_ok=True)
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------- Pytest / Coverage ----------------

def run_pytest_coverage() -> dict:
    out = run("pytest --cov=app --cov-report=xml --cov-report=term-missing", check=False)
    cov_xml = ROOT / "coverage.xml"
    cov = {"output": out, "xml_path": str(cov_xml), "summary": {}, "files": []}
    if cov_xml.exists():
        tree = ET.parse(str(cov_xml))
        root = tree.getroot()
        cov["summary"]["line_rate"] = float(root.attrib.get("line-rate", "0"))
        cov["summary"]["branch_rate"] = float(root.attrib.get("branch-rate", "0"))
        files = []
        for pkg in root.findall(".//package"):
            for cls in pkg.findall(".//class"):
                files.append({
                    "filename": cls.attrib.get("filename", ""),
                    "line_rate": float(cls.attrib.get("line-rate", "0")),
                    "lines": [
                        {"number": int(line.attrib.get("number", "0")),
                         "hits": int(line.attrib.get("hits", "0"))}
                        for line in cls.findall(".//line")
                    ],
                })
        cov["files"] = files
    return cov

# ---------------- Metadata proyecto ----------------

def extract_fastapi_routes() -> list:
    routes = []
    p = APP_DIR / "main.py"
    if p.exists():
        txt = p.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'@app\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']', txt):
            routes.append({"method": m.group(1).upper(), "path": m.group(2)})
    return routes

def extract_pydantic_models() -> list:
    models = []
    for py in APP_DIR.glob("*.py"):
        txt = py.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"class\s+([A-Za-z_]\w*)\s*\(\s*BaseModel\s*\)\s*:", txt):
            models.append({"file": py.name, "model": m.group(1)})
    return models

# ---------------- Fuentes para contexto ----------------

def pick_files_for_context(cov: dict) -> List[pathlib.Path]:
    priority = [APP_DIR / "main.py", APP_DIR / "auth.py", APP_DIR / "settings.py", APP_DIR / "schemas.py"]
    chosen = [p for p in priority if p.exists()]
    low_cov = [f["filename"] for f in cov.get("files", []) if f.get("line_rate", 1.0) < 0.90]
    for rel in low_cov:
        p = (ROOT / rel).resolve()
        if p.exists() and p not in chosen:
            chosen.append(p)
    # único
    uniq, seen = [], set()
    for p in chosen:
        if str(p) not in seen:
            uniq.append(p)
            seen.add(str(p))
    return uniq

def assemble_sources_payload(paths: List[pathlib.Path], budget: int = MAX_SOURCE_CHARS) -> List[Dict[str, Any]]:
    payload, remaining = [], max(budget, 0)
    for p in paths:
        if remaining <= 0:
            break
        text = p.read_text(encoding="utf-8", errors="ignore")
        max_per_file = min(len(text), max(2000, budget // 3))
        snippet = text if len(text) <= remaining else text[:min(remaining, max_per_file)]
        payload.append({
            "filename": str(p.relative_to(ROOT)),
            "chars": len(snippet),
            "truncated": len(snippet) < len(text),
            "source": snippet
        })
        remaining -= len(snippet)
    return payload

# ---------------- Prompt ----------------

DEFAULT_PROMPT = """Tu tarea: generar **nuevas** pruebas pytest que aumenten cobertura y validen rutas/errores de una API FastAPI.

Contexto del proyecto (JSON con cobertura, rutas, modelos y fragmentos de código fuente):
{{CONTEXT_JSON}}

Reglas:
- Importa desde el paquete **app** (p.ej., `from app.schemas import ...`).
- Usa fixtures existentes: **client** y **authed_client**. No crees `TestClient(app)` manualmente.
- Para `'/'` usa `allow_redirects=False` y valida 302/307 + cabecera `location`.
- Para fallback del motor, rompe `app.main._load_sync_engine` con `monkeypatch.setattr`; si el endpoint está protegido, sobreescribe `require_auth` con `app.dependency_overrides`.
- Para 401 no inventes tokens: o no envíes Authorization o tampera uno obtenido de `/auth/login`.
- No dependas de librerías adicionales.

Prioriza cubrir:
- `"/"` redirect, `"/favicon.ico" 204`
- Fallback en `_load_sync_engine`
- Whitelist en `/sync`
- JWT inválido/expirado/tamper
- Parsing en `Settings` (`CORS_ORIGINS`, `ALLOWED_TABLES`)

Entrega solo bloques ```python ...``` con archivos listos en `tests/ai_generated/test_ai_*.py`.
"""

def build_prompt_context(cov: dict, routes: list, models: list, critique: dict | None = None) -> str:
    summary = cov.get("summary", {})
    files = cov.get("files", [])
    uncovered_files = [f for f in files if f.get("line_rate", 0.0) < 0.9]
    sources_payload = assemble_sources_payload(pick_files_for_context(cov), budget=MAX_SOURCE_CHARS)
    base = PROMPT_FILE.read_text(encoding="utf-8") if PROMPT_FILE.exists() else DEFAULT_PROMPT
    ctx = {
        "coverage_line_rate": summary.get("line_rate", 0.0),
        "uncovered_files": uncovered_files,
        "routes": routes,
        "models": models,
        "sources": sources_payload,
    }
    if critique:
        ctx["auto_critique"] = critique
    return base.replace("{{CONTEXT_JSON}}", json.dumps(ctx, indent=2))

# ---------------- LLM ----------------

def call_llm(prompt: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return DRY_RUN_EXAMPLE
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a senior QA engineer who writes high-quality pytest tests for FastAPI apps."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[LLM ERROR] {e}")
        return DRY_RUN_EXAMPLE

DRY_RUN_EXAMPLE = """```python
# tests/ai_generated/test_ai_login_expired.py
import jwt, pytest

def test_status_token_expired(client, monkeypatch):
    res = client.post("/auth/login", data={"username": "admin", "password": "adminadmin"})
    token = res.json()["access_token"]

    def fake_decode(*args, **kwargs):
        from jwt import ExpiredSignatureError
        raise ExpiredSignatureError("expired")

    monkeypatch.setattr(jwt, "decode", fake_decode)
    r = client.get("/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
```"""


def _validate_python(code: str) -> tuple[bool, str]:
    """Devuelve (ok, error_msg). ok=False si SyntaxError."""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as se:
        # Mensaje corto para diagnosticar
        return False, f"{se.msg} at line {se.lineno}, col {se.offset}"

# ---------------- Post-procesado (auto-fixes) ----------------

def _ensure_import_pytest_if_used(code: str) -> str:
    if "pytest." in code and "import pytest" not in code:
        return "import pytest\n" + code
    return code

def _forbid_manual_testclient(code: str) -> str:
    # Elimina importaciones y construcciones de TestClient explícitas
    code = re.sub(r"from\s+fastapi\.testclient\s+import\s+TestClient\s*\n?", "", code)
    code = re.sub(r"client\s*=\s*TestClient\([^\)]*\)\s*\n", "", code)
    return code

def _fix_redirect_tests(code: str) -> str:
    # Asegura allow_redirects=False y validación por header location
    code = code.replace('client.get("/")', 'client.get("/", allow_redirects=False)')
    code = re.sub(
        r"assert\s+response\.url\.endswith\([\"']\/docs[\"']\)",
        "assert response.headers.get('location','').endswith('/docs')",
        code,
    )
    return code

def _drop_favicon_content_assert(code: str) -> str:
    # Mantén status 204, evita assert de contenido exacto
    code = re.sub(r"assert\s+response\.content\s*==\s*b[\"']{0,1}null[\"']{0,1}\s*\n", "", code)
    return code

def _add_fixture_param_if_used(code: str, name: str) -> str:
    """
    Si se usa 'client.' o 'authed_client.' dentro de la función pero
    el nombre no está en la firma, lo agrega.
    """
    def add_param_to_def(match):
        head = match.group(1)  # 'def test_xxx('
        params = match.group(2)  # contenido entre paréntesis
        body = match.group(3)  # resto
        if name not in params:
            params = (params + "," if params.strip() else "") + f"{name}"
        return f"{head}{params}){body}"

    # por función test_...
    pattern_use = rf"{name}\."
    if re.search(pattern_use, code):
        code = re.sub(r"(def\s+test_[\w_]+\()([^\)]*)(\):)", add_param_to_def, code)
    return code

def sanitize_generated_code(raw: str) -> str:
    code = raw.strip()
    code = _ensure_import_pytest_if_used(code)
    code = _forbid_manual_testclient(code)
    code = _fix_redirect_tests(code)
    code = _drop_favicon_content_assert(code)
    code = _add_fixture_param_if_used(code, "client")
    code = _add_fixture_param_if_used(code, "authed_client")
    return code

# ---------------- Escritura tests ----------------

def write_tests_from_llm(text: str) -> list:
    """
    Extrae bloques ```python ... ``` y los guarda en tests/ai_generated/.
    Si un bloque tiene SyntaxError, se guarda un archivo que hace pytest.skip
    a nivel de módulo, para no romper la colección.
    """
    code_blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, flags=re.DOTALL)
    if not code_blocks:
        code_blocks = [text]
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    written = []
    for i, raw in enumerate(code_blocks, start=1):
        code = raw.strip()
        name = f"test_ai_{ts}_{i}.py"
        path = AIGEN_DIR / name

        ok, err = _validate_python(code)
        if ok:
            path.write_text(code + "\n", encoding="utf-8")
        else:
            # Archiva como módulo “saltado” para no interrumpir Pytest
            safe = (
                "import pytest\n"
                f'pytest.skip("Skipping invalid AI-generated test: {err}", allow_module_level=True)\n\n'
                "# ---- Original AI output (commented) ----\n"
                + "\n".join(f"# {line}" for line in code.splitlines())
                + "\n"
            )
            path.write_text(safe, encoding="utf-8")

        written.append(str(path.relative_to(ROOT)))
    return written

# ---------------- Auto-crítica ----------------

ANTI_PATTERNS = [
    ("from schemas import", "Importa desde app.schemas (p.ej., `from app.schemas import ...`)."),
    ("TestClient(", "Usa fixtures `client`/`authed_client`, no crees TestClient manualmente."),
    ('Authorization": "Bearer valid_token', "No inventes tokens; usa /auth/login o fuerza 401 sin header."),
]

def analyze_generated_tests(files: List[str], pytest_output: str) -> dict:
    critique: Dict[str, Any] = {"anti_patterns": [], "pytest_failures": ""}

    for rel in files:
        full = ROOT / rel if not rel.startswith("/") else pathlib.Path(rel)
        if not full.exists():
            continue
        txt = full.read_text(encoding="utf-8", errors="ignore")
        for needle, advice in ANTI_PATTERNS:
            if needle in txt:
                critique["anti_patterns"].append({"file": str(full.relative_to(ROOT)), "pattern": needle, "advice": advice})
        if 'client.get("/")' in txt and 'allow_redirects=False' not in txt:
            critique["anti_patterns"].append({
                "file": str(full.relative_to(ROOT)),
                "pattern": 'client.get("/") sin allow_redirects=False',
                "advice": "Para cubrir redirect en '/', usa allow_redirects=False y valida header 'location'."
            })

    if "FAILED" in pytest_output or "ERROR" in pytest_output:
        tail = "\n".join(pytest_output.splitlines()[-160:])
        critique["pytest_failures"] = tail

    return critique

# ---------------- Main loop ----------------

def main():
    ensure_dirs()

    print("== 1) Pytest inicial con cobertura ==")
    cov_before = run_pytest_coverage()
    routes = extract_fastapi_routes()
    models = extract_pydantic_models()

    before = cov_before.get("summary", {}).get("line_rate", 0.0)
    best = before

    critique: dict | None = None

    for it in range(1, MAX_ITERS + 1):
        print(f"\n==== Iteración IA #{it}/{MAX_ITERS} ====")
        print("== 2) Construyendo prompt para LLM ==")
        prompt = build_prompt_context(cov_before, routes, models, critique=critique)

        print("== 3) Solicitando tests al LLM ==")
        llm_text = call_llm(prompt)

        print("== 4) Escribiendo tests generados ==")
        files = write_tests_from_llm(llm_text)
        print("Archivos creados:", files)

        print("== 5) Pytest después de generar tests ==")
        cov_after = run_pytest_coverage()
        after = cov_after.get("summary", {}).get("line_rate", 0.0)
        print(f"Cobertura: antes {before:.2%} | esta iteración {after:.2%}")

        critique = analyze_generated_tests(files, cov_after.get("output", ""))

        if after > best:
            best = after

        # Si no hay fallos ni antipatrón y no mejora, ya terminamos
        no_failures = not critique.get("pytest_failures")
        no_antipatterns = len(critique.get("anti_patterns", [])) == 0
        if it == MAX_ITERS or (no_failures and no_antipatterns and after >= best):
            break

    print(f"\nCobertura antes: {before:.2%}  |  mejor alcanzada: {best:.2%}")
    print("Listo.")

if __name__ == "__main__":
    os.chdir(str(ROOT))
    sys.exit(main())