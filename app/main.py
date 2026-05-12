from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv()

from app.api import alerts, doctors, labs, patients, vitals, webhooks  # noqa: E402
from app.api.auth_router import router as auth_router  # noqa: E402
from app.auth import get_current_user  # noqa: E402

app = FastAPI(
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

# ── Register routers ─────────────────────────────────────────────────────────
# Auth routes are public (login, setup)
app.include_router(auth_router)

# All clinical routes require authentication
_auth = [Depends(get_current_user)]
app.include_router(patients.router, dependencies=_auth)
app.include_router(vitals.router,   dependencies=_auth)
app.include_router(labs.router,     dependencies=_auth)
app.include_router(alerts.router,   dependencies=_auth)
app.include_router(doctors.router,  dependencies=_auth)

# Webhooks use Twilio's own signature verification — no JWT needed
app.include_router(webhooks.router)


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "service": "sepsis-watch", "version": "0.4.0"}


# ── Dev server ───────────────────────────────────────────────────────────────
# Run:   uvicorn app.main:app --reload
# Docs:  http://localhost:8000/docs
