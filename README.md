# Sepsis Watch 🩺

**Real-time ICU Sepsis Early Warning System — Indian Hospital Market**

An end-to-end production Python system that monitors ICU patient vitals, scores sepsis risk using a temporal deep learning model (LSTM + Attention), and routes alerts to doctors via a multi-step agentic pipeline. Doctors receive evidence-based clinical summaries — the AI never touches treatment decisions.

Built on MIMIC-III (free, 40,000 ICU stays, MIT License from PhysioNet).

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Database | TimescaleDB (PostgreSQL + time-series extension) |
| Cache / Queue | Redis + Celery |
| ML | PyTorch (LSTM / Temporal Attention) |
| Agents | LangChain + LangGraph |
| Alerts | Twilio WhatsApp API |
| Migrations | Alembic |
| Retina (Problem 5) | EfficientNet / ViT via `timm` |

---

## Project Structure

```
sepsis-watch/
├── app/
│   ├── api/           ← FastAPI route handlers
│   ├── models/        ← SQLAlchemy table definitions
│   ├── services/      ← Business logic (scoring, alert routing)
│   ├── agents/        ← Agentic watch loop
│   └── db/            ← DB engine, session factory
├── ml/
│   ├── sepsis/        ← LSTM model, training scripts, inference
│   └── retina/        ← EfficientNet model for retinopathy (Problem 5)
├── data/
│   ├── raw/           ← MIMIC-III CSVs (never committed to git)
│   └── processed/     ← Feature-engineered data
├── notebooks/         ← Jupyter exploration notebooks
├── scripts/           ← One-off scripts (data loading, DB seeding)
├── tests/             ← pytest test suite
├── docker-compose.yml ← TimescaleDB + Redis containers
└── requirements.txt
```

---

## Setup

### 1. Prerequisites
- Python 3.9+
- Docker Desktop
- DBeaver (for DB inspection)

### 2. Clone & create virtual environment
```bash
git clone https://github.com/Achintya17408/sepsis-watch.git
cd sepsis-watch
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Start databases
```bash
docker compose up -d
docker ps   # verify sepsis_db and sepsis_redis are running
```

### 4. Environment variables
Copy `.env.example` to `.env` and fill in your API keys:
```bash
cp .env.example .env
```

### 5. Run migrations
```bash
alembic upgrade head
```

### 6. Enable TimescaleDB hypertable (run once in DBeaver)
```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
SELECT create_hypertable('vital_readings', 'recorded_at');
```

### 7. Start the API
```bash
uvicorn app.main:app --reload
```
Open **http://localhost:8000/docs** for interactive Swagger UI.

---

## Data Access

MIMIC-III is free from [PhysioNet](https://physionet.org/content/mimiciii/1.4/).  
Registration takes 2–3 days. Once approved, download CSVs into `data/raw/`.

---

## Roadmap

- [ ] Phase 1 — Data pipeline: MIMIC-III → TimescaleDB ingestion
- [ ] Phase 2 — Signal processing: FFT + wavelet features on vitals
- [ ] Phase 3 — LSTM model: temporal risk scoring 0–1
- [ ] Phase 4 — Agentic loop: alert generation + clinical summary
- [ ] Phase 5 — WhatsApp alert delivery (Twilio)
- [ ] Problem 5 — Diabetic Retinopathy: EfficientNet inference pipeline

---

## License

MIT
