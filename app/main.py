# app/main.py
import os
import sys
import asyncio
import subprocess
import pathlib
import xml.etree.ElementTree as ET
from typing import Dict, Any, AsyncIterator, List, Optional, Tuple

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Body,
    status,
    Query,
)
from fastapi.responses import (
    RedirectResponse,
    JSONResponse,
    HTMLResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles

# 🔧 Config & Rate Limit
from app.settings import settings, init_rate_limiter
# 🧾 Esquemas Pydantic
from app.schemas import SyncRequest, StatusResponse
# 🔐 Auth
from app.auth import router as auth_router, require_auth, create_access_token

# === APP INSTANCE ===
app = FastAPI(title=settings.APP_NAME)
limiter = init_rate_limiter(app)

# === ROOT / FAVICON ===
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return JSONResponse(status_code=204, content=None)

# === HEALTH ===
@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}

# === LOAD SYNC ENGINE (mock or real) ===
def _load_sync_engine():
    """
    Intenta cargar sync_engine desde DATASYNC_HOME/src.
    Si no existe, devuelve un motor mock para evitar errores.
    """
    home = os.environ.get("DATASYNC_HOME", settings.DATASYNC_HOME)
    src = os.path.join(home, "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        import sync_engine  # type: ignore
        return sync_engine
    except Exception as e:
        err_name = e.__class__.__name__

        class _Fallback:
            @staticmethod
            def get_sync_status():
                return {
                    "sqlserver": False,
                    "mysql": False,
                    "configured_tables": 0,
                    "enabled_tables": 0,
                    "system_health": f"fallback: {err_name}",
                }

            @staticmethod
            def sync_all_tables(specific_tables=None, dry_run=False):
                return None

        return _Fallback

# === PROTECTED ENDPOINTS ===
@app.get("/status", response_model=StatusResponse)
def status(_: str = Depends(require_auth)):
    engine = _load_sync_engine()
    return engine.get_sync_status()

@app.post("/sync")
def sync(req: SyncRequest, _: str = Depends(require_auth)) -> Dict[str, Any]:
    tables = req.tables or []

    # Validación defensiva
    bad = [t for t in tables if (";" in t or " " in t)]
    if bad:
        raise HTTPException(status_code=400, detail=f"Invalid table names: {bad}")

    # Whitelist desde settings.ALLOWED_TABLES
    allowed = set(settings.ALLOWED_TABLES or [])
    if allowed and any(t not in allowed for t in tables):
        raise HTTPException(status_code=403, detail="Table not allowed by whitelist")

    engine = _load_sync_engine()
    engine.sync_all_tables(specific_tables=tables, dry_run=req.dry_run)
    return {"ok": True, "tables": tables, "message": None}

# === AUTH ROUTER ===
app.include_router(auth_router)

# === DEV TOKEN ENDPOINT (solo dev) ===
@app.post("/internal/dev-token", include_in_schema=False)
def dev_token():
    """
    Emite un token válido automáticamente para el dashboard QA.
    ⚠️ Úsalo solo en desarrollo.
    """
    if not getattr(settings, "DASHBOARD_ENABLE_DEV", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Dev token disabled")
    return {"access_token": create_access_token(settings.ADMIN_USERNAME)}

# === QA / COBERTURA ===
HTMLCOV_DIR = pathlib.Path("htmlcov")
COV_XML = pathlib.Path("coverage.xml")

def _detect_ai_runner() -> Optional[Tuple[pathlib.Path, Optional[str]]]:
    """
    Busca el ai_test_runner en rutas comunes y prioriza el que vive en tools/.
    Retorna (path, module_name) si se debe ejecutar como módulo (con -m),
    o (path, None) si se ejecuta como script.
    """
    candidates: List[Tuple[str, Optional[str]]] = [
        # PRIORIDAD: el que empaquetas en la imagen
        ("/app/tools/ai_test_runner.py", "tools.ai_test_runner"),
        # alternativos relativos (por si corres fuera de docker)
        ("tools/ai_test_runner.py", "tools.ai_test_runner"),
        ("ai_test_runner.py", None),
        ("/app/ai_test_runner.py", None),
    ]
    for path_str, module_name in candidates:
        p = pathlib.Path(path_str)
        if p.exists():
            return (p, module_name)
    return None

def _mount_htmlcov() -> bool:
    """Monta /htmlcov si el directorio existe."""
    if HTMLCOV_DIR.exists():
        try:
            app.mount("/htmlcov", StaticFiles(directory=str(HTMLCOV_DIR)), name="htmlcov")
        except Exception:
            # ya montado
            pass
        return True
    return False

@app.on_event("startup")
def _startup_mount_cov():
    _mount_htmlcov()

def _read_coverage_summary() -> Dict[str, Any]:
    """Lee coverage.xml y devuelve {ok, percent} para el gauge del dashboard."""
    if not COV_XML.exists():
        return {"ok": False, "percent": None}
    try:
        root = ET.parse(str(COV_XML)).getroot()
        line_rate = float(root.attrib.get("line-rate", "0"))
        return {"ok": True, "percent": round(line_rate * 100, 2)}
    except Exception:
        return {"ok": False, "percent": None}

@app.post("/qa/coverage/refresh")
def qa_refresh_coverage(_: str = Depends(require_auth)):
    mounted = _mount_htmlcov()
    return {"ok": mounted}

@app.get("/qa/coverage/summary")
def qa_coverage_summary(_: str = Depends(require_auth)):
    return _read_coverage_summary()
@app.get("/qa/ai-runner", include_in_schema=False)
def qa_ai_runner(_: str = Depends(require_auth)):
    p = _detect_ai_runner()
    return {"path": str(p) if p else None, "exists": bool(p)}


# === Elección de comando de pruebas ===
def _choose_cmd(mode: str = "auto") -> List[str]:
    """
    mode=ai      -> corre el runner IA si existe (como módulo si vive en tools/)
    mode=pytest  -> pytest --cov ...
    mode=auto    -> IA si existe; si no, pytest
    """
    runner = _detect_ai_runner()

    # Si pidieron IA explícitamente y no hay runner → caer a pytest
    if mode == "ai" and not runner:
        return ["bash", "-lc", "pytest --cov=app --cov-report=xml --cov-report=html -q"]

    # IA (auto o explícito)
    if mode in ("ai", "auto") and runner:
        path, module_name = runner
        if module_name:
            # fuerza contexto correcto del paquete
            return ["bash", "-lc", "cd /app && PYTHONPATH=/app python -u -m tools.ai_test_runner"]
        # como script plano
        return ["bash", "-lc", f"python -u {path}"]

    # Pytest por defecto
    return ["bash", "-lc", "pytest --cov=app --cov-report=xml --cov-report=html -q"]

# === Ejecución normal (no streaming) ===
@app.post("/qa/run-tests")
def qa_run_tests_normal(
    mode: str = Query("auto", enum=["auto", "ai", "pytest"]),
    body: Dict[str, Any] | None = Body(None),
    _: str = Depends(require_auth),
):
    """
    Ejecuta pruebas y devuelve salida + cobertura.
    - Si pasas body {"with_ai": true/false}, mapea a mode=ai/pytest.
    - Query ?mode=ai|pytest|auto tiene prioridad.
    """
    if body is not None and "with_ai" in body and mode == "auto":
        mode = "ai" if bool(body.get("with_ai")) else "pytest"

    cmd = _choose_cmd(mode)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")

    _mount_htmlcov()
    cov = _read_coverage_summary()

    present = _detect_ai_runner() is not None
    return {
        "mode": mode,
        "resolved_cmd": cmd,
        "returncode": proc.returncode,
        "output": out,
        "coverage": cov,
        "htmlcov": HTMLCOV_DIR.exists(),
        "ai_runner_present": present,
    }

# === Streaming (log en vivo) ===
async def _stream_process(cmd: List[str]) -> AsyncIterator[bytes]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None
    async for line in proc.stdout:
        yield line
    await proc.wait()
    _mount_htmlcov()

@app.post("/qa/run-tests/stream")
def qa_run_tests_stream(
    mode: str = Query("auto", enum=["auto", "ai", "pytest"]),
    body: Dict[str, Any] | None = Body(None),
    _: str = Depends(require_auth),
):
    """
    Stream de pruebas. Igual que /qa/run-tests pero con salida en vivo.
    """
    if body is not None and "with_ai" in body and mode == "auto":
        mode = "ai" if bool(body.get("with_ai")) else "pytest"
    cmd = _choose_cmd(mode)
    return StreamingResponse(_stream_process(cmd), media_type="text/plain")

# === DASHBOARD QA (HTML) ===
@app.get("/qa", include_in_schema=False)
def qa_home():
    return HTMLResponse(
        """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>🧪 QA Dashboard</title>
  <style>
    :root{--bg:#f9fafb;--card:#fff;--ink:#111827;--muted:#6b7280;--primary:#2563eb;--ok:#059669;--warn:#d97706;--err:#dc2626;}
    body{font-family:system-ui,sans-serif;background:var(--bg);padding:24px;color:var(--ink)}
    .card{background:var(--card);padding:24px;border-radius:12px;max-width:1000px;margin:auto;box-shadow:0 1px 4px rgba(0,0,0,.1)}
    .btn{background:var(--primary);color:#fff;border:0;padding:10px 16px;border-radius:8px;cursor:pointer}
    .btn:disabled{opacity:.5;cursor:not-allowed}
    #out{white-space:pre-wrap;background:#0b1021;color:#e5e7eb;padding:12px;border-radius:8px;overflow:auto;max-height:360px}
    .row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:12px}
    .ok{color:var(--ok);font-weight:600}.err{color:var(--err);font-weight:600}.muted{color:var(--muted);font-size:12px}
    .grid{display:grid;grid-template-columns:320px 1fr;gap:16px;margin-top:16px}
    .panel{background:#fff;border-radius:12px;padding:16px;border:1px solid #e5e7eb}
    .barWrap{background:#e5e7eb;height:12px;border-radius:999px;overflow:hidden}
    .bar{height:100%;width:0;background:linear-gradient(90deg,#22c55e,#84cc16)}
    .covNum{font-size:32px;font-weight:700}.covSub{color:var(--muted);font-size:12px;margin-top:-6px}
    .svgGauge{width:220px;height:220px;display:block;margin:auto}
    .arc--good{stroke:var(--ok)}.arc--warn{stroke:var(--warn)}.arc--bad{stroke:var(--err)}
    #covTitle.good{color:var(--ok)}#covTitle.warn{color:var(--warn)}#covTitle.bad{color:var(--err)}
  </style>
</head>
<body>
  <div class="card">
    <h1>🧪 QA Dashboard</h1>
    <p>Ejecuta <code>ai_test_runner.py</code> si existe, si no, <code>pytest --cov=app --cov-report=xml --cov-report=html</code>.</p>

    <div class="grid">
      <div class="panel">
        <h3 id="covTitle" style="margin-top:0">📊 Cobertura</h3>
        <svg class="svgGauge" viewBox="0 0 120 120">
          <circle cx="60" cy="60" r="52" stroke="#e5e7eb" stroke-width="12" fill="none" />
          <circle id="arc" cx="60" cy="60" r="52" stroke="#22c55e" stroke-width="12" fill="none"
                  stroke-linecap="round" transform="rotate(-90 60 60)"
                  stroke-dasharray="327 327" stroke-dashoffset="327"/>
          <text id="pct" x="60" y="64" text-anchor="middle" class="covNum">--%</text>
          <text x="60" y="80" text-anchor="middle" class="covSub">Line coverage</text>
        </svg>
        <div class="barWrap"><div id="bar" class="bar"></div></div>
        <div id="covMeta" class="muted" style="margin-top:6px">Genera una corrida para ver datos.</div>
        <div class="muted" style="margin-top:8px">
          <span style="color:#dc2626;font-weight:600">●</span> &lt;60%
          <span style="color:#d97706;font-weight:600">●</span> 60–79%
          <span style="color:#059669;font-weight:600">●</span> ≥80%
        </div>
      </div>

      <div>
        <div class="panel">
          <div class="row">
            <button id="runAI" class="btn">🤖 Forzar IA</button>
            <button id="runPy" class="btn">🐍 Forzar pytest</button>
            <button id="runStream" class="btn">📡 Stream en vivo</button>
            <span id="status" class="muted">Listo</span>
          </div>
          <h3>Salida</h3>
          <div id="out"></div>
        </div>
      </div>
    </div>
  </div>

  <script>
    const $ = (id)=>document.getElementById(id);
    const out=$("out"),status=$("status"),runAI=$("runAI"),runPy=$("runPy"),runStream=$("runStream");
    const arc=$("arc"),pct=$("pct"),bar=$("bar"),covMeta=$("covMeta"),covTitle=$("covTitle");
    let token=null;

    async function getToken(){
      if(token) return token;
      const r=await fetch("/internal/dev-token",{method:"POST"});
      const j=await r.json(); token=j.access_token; return token;
    }
    function setBusy(b){runAI.disabled=b;runPy.disabled=b;runStream.disabled=b;status.textContent=b?"Ejecutando...":"Listo";}
    function setCoverage(p){
      if(p==null){ pct.textContent="--%"; bar.style.width="0%"; covMeta.textContent="Sin datos";
        arc.classList.remove("arc--good","arc--warn","arc--bad");
        covTitle.classList.remove("good","warn","bad"); return; }
      const maxCirc = 2*Math.PI*52; const dash = maxCirc*(1 - (p/100));
      arc.setAttribute("stroke-dasharray", maxCirc.toFixed(0)+" "+maxCirc.toFixed(0));
      arc.setAttribute("stroke-dashoffset", dash.toFixed(1));
      pct.textContent = p.toFixed(2) + "%";
      bar.style.width = p + "%";
      covMeta.textContent = "Cobertura de líneas";
      arc.classList.remove("arc--good","arc--warn","arc--bad");
      covTitle.classList.remove("good","warn","bad");
      if (p >= 80) { arc.classList.add("arc--good"); covTitle.classList.add("good");
        bar.style.background="linear-gradient(90deg,#22c55e,#84cc16)"; }
      else if (p >= 60) { arc.classList.add("arc--warn"); covTitle.classList.add("warn");
        bar.style.background="linear-gradient(90deg,#eab308,#f59e0b)"; }
      else { arc.classList.add("arc--bad"); covTitle.classList.add("bad");
        bar.style.background="linear-gradient(90deg,#f43f5e,#ef4444)"; }
    }
    async function fetchCoverage(){
      try{
        const tk=await getToken();
        const r=await fetch("/qa/coverage/summary",{headers:{"Authorization":"Bearer "+tk}});
        const j=await r.json();
        setCoverage(j && j.ok ? (j.percent||0) : null);
      }catch{ setCoverage(null); }
    }
    async function runOnce(mode){
      setBusy(true); out.textContent="";
      const tk=await getToken();
      const r=await fetch("/qa/run-tests?mode="+mode,{method:"POST",headers:{"Authorization":"Bearer "+tk}});
      const j=await r.json();
      out.textContent=j.output||"";
      status.innerHTML=(j.returncode===0)?"<span class='ok'>OK</span>":"<span class='err'>FALLÓ</span>";
      await fetchCoverage();
      setBusy(false);
    }
    runAI.addEventListener("click",()=>runOnce("ai"));
    runPy.addEventListener("click",()=>runOnce("pytest"));
    runStream.addEventListener("click",async()=>{
      setBusy(true); out.textContent="";
      const tk=await getToken();
      const r=await fetch("/qa/run-tests/stream?mode=ai",{method:"POST",headers:{"Authorization":"Bearer "+tk}});
      const rd=r.body.getReader(); const dec=new TextDecoder();
      while(true){ const {value,done}=await rd.read(); if(done)break; out.textContent+=dec.decode(value); out.scrollTop=out.scrollHeight; }
      status.innerHTML="<span class='ok'>Finalizado</span>";
      await fetchCoverage();
      setBusy(false);
    });

    // Cargar cobertura al abrir la página
    fetchCoverage();
  </script>
</body>
</html>
        """
    )