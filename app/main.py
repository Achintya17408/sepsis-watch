from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Sepsis Watch API",
    description="Real-time ICU sepsis early warning system — Indian hospital market",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Lock this down to your frontend domain in production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "service": "sepsis-watch", "version": "0.1.0"}


# Run with:
#   uvicorn app.main:app --reload
# Then open: http://localhost:8000/docs  (auto-generated Swagger UI)
