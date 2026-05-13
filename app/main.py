from fastapi import FastAPI, Depends, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import asyncio
import logging
import os
import pathlib

load_dotenv()

from app.api import alerts, doctors, labs, patients, vitals, webhooks  # noqa: E402
from app.api.auth_router import router as auth_router  # noqa: E402
from app.auth import get_current_user  # noqa: E402

log = logging.getLogger(__name__)


async def _keepalive_loop():
    """
    On Render free tier, services sleep after 15 min of inactivity.
    Self-ping every 10 min prevents cold starts during active demos.
    Only runs when APP_ENV=production and a PUBLIC_URL is set.
    """
    import httpx
    url = os.getenv("PUBLIC_URL", "").rstrip("/") + "/health"
    while True:
        await asyncio.sleep(600)  # 10 minutes
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.get(url)
            log.debug("Keepalive ping sent to %s", url)
        except Exception:
            pass  # non-critical


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("APP_ENV") == "production" and os.getenv("PUBLIC_URL"):
        task = asyncio.create_task(_keepalive_loop())
    else:
        task = None
    yield
    if task:
        task.cancel()

app = FastAPI(
    lifespan=lifespan,
    title="Sepsis Watch API",
    description=(
        "Real-time ICU sepsis early warning system — Indian hospital market.\n\n"
        "Monitors patient vitals and labs, scores sepsis risk using a Bidirectional "
        "LSTM + temporal attention model, generates LangGraph clinical summaries via "
        "Ollama / Anthropic Claude, and routes WhatsApp alerts to on-call clinicians via Twilio.\n\n"
        "**Authentication**: All endpoints except `/health`, `/auth/*`, and `/webhooks/*` "
        "require a JWT bearer token. Use `POST /auth/setup` on first run, then "
        "`POST /auth/token` to get your token."
    ),
    version="0.4.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — in production set ALLOWED_ORIGINS to your dashboard URL(s)
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
_origins = [o.strip() for o in _raw_origins.split(",")] if _raw_origins != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers under /api prefix ───────────────────────────────────────
# Grouping under /api keeps API routes separate from React Router client paths
# (e.g. /patients is a React page; /api/patients is the REST endpoint)
_api = APIRouter(prefix="/api")

# Auth routes are public (login, setup)
_api.include_router(auth_router)

# All clinical routes require authentication
_auth = [Depends(get_current_user)]
_api.include_router(patients.router, dependencies=_auth)
_api.include_router(vitals.router,   dependencies=_auth)
_api.include_router(labs.router,     dependencies=_auth)
_api.include_router(alerts.router,   dependencies=_auth)
_api.include_router(doctors.router,  dependencies=_auth)

# Webhooks use Twilio's own signature verification — no JWT needed
_api.include_router(webhooks.router)

app.include_router(_api)


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "service": "sepsis-watch", "version": "0.4.0"}


# ── Serve React frontend (single-URL deployment) ─────────────────────────────
# When dashboard/dist exists (Docker build bakes it in), FastAPI serves the
# React SPA for any path not matched by an API route above.
# In local dev, dashboard/dist won't exist — run Vite dev server instead.
_dist = pathlib.Path(__file__).parent.parent / "dashboard" / "dist"

if _dist.is_dir():
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        candidate = _dist / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_dist / "index.html"))


# ── Dev server ───────────────────────────────────────────────────────────────
# Run:   uvicorn app.main:app --reload
# Docs:  http://localhost:8000/docs
