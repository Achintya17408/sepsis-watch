"""
Pipeline: MIMIC-III → TimescaleDB / PostgreSQL

Reads raw MIMIC-III CSVs from data/raw/ and populates all clinical tables
in the correct dependency order:

  1. patients          ← PATIENTS.csv
  2. icu_admissions    ← ICUSTAYS.csv + ADMISSIONS.csv
  3. comorbidities     ← DIAGNOSES_ICD.csv + D_ICD_DIAGNOSES.csv
  4. lab_results       ← LABEVENTS.csv          (~1.5 GB — chunked)
  5. vital_readings    ← CHARTEVENTS.csv         (~33 GB — chunked, skippable in dev)

Required MIMIC-III files (download from PhysioNet after completing CITI training):
  https://physionet.org/content/mimiciii/1.4/

Usage:
  python scripts/load_mimic.py                    # full load
  python scripts/load_mimic.py --patients-only    # only load patients table
  python scripts/load_mimic.py --skip-chartevents # skip the 33 GB CHARTEVENTS file (dev mode)
  python scripts/load_mimic.py --skip-labs        # skip LABEVENTS

All inserts are idempotent — safe to run multiple times (ON CONFLICT DO NOTHING).
"""
import argparse
import logging
import os
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")
CHUNK_SIZE = 100_000  # rows per pandas chunk for large files


# ─── MIMIC-III LABEVENTS item IDs → our lab_results column names ─────────────
# Source: D_LABITEMS.csv from MIMIC-III
LAB_ITEM_MAP: Dict[int, str] = {
    # CBC
    51301: "wbc",              # White Blood Cells
    51222: "hemoglobin",       # Hemoglobin
    51221: "hematocrit",       # Hematocrit
    51265: "platelets",        # Platelet Count — SOFA coagulation
    # BMP
    50983: "sodium",           # Sodium
    50971: "potassium",        # Potassium
    50902: "chloride",         # Chloride
    50882: "bicarbonate",      # Bicarbonate
    51006: "bun",              # Urea Nitrogen (BUN)
    50912: "creatinine",       # Creatinine — SOFA renal
    50931: "glucose",          # Glucose
    # LFTs
    50885: "bilirubin_total",  # Bilirubin, Total — SOFA hepatic
    50883: "bilirubin_direct", # Bilirubin, Direct
    50878: "ast",              # Aspartate Aminotransferase (AST/SGOT)
    50861: "alt",              # Alanine Aminotransferase (ALT/SGPT)
    50863: "alkaline_phosphatase",
    50862: "albumin",
    # Coagulation
    51237: "inr",              # INR (PT)
    51274: "prothrombin_time", # Prothrombin Time
    51275: "aptt",             # PTT
    # ABG
    50820: "ph",               # pH
    50821: "pao2",             # pO2 — SOFA respiratory (with FiO2 ratio)
    50818: "paco2",            # pCO2
    50816: "fio2",             # Required FiO2 (%)
    50803: "base_excess",      # Base Excess
    # Sepsis-specific
    50813: "lactate",          # Lactate — tissue hypoperfusion / septic shock
}

# ─── MIMIC-III CHARTEVENTS item IDs → our vital_readings column names ─────────
# MetaVision item IDs (used in MIMIC-III 2008–2012 data, itemid >= 220000)
VITAL_ITEM_MAP: Dict[int, str] = {
    220045: "heart_rate",
    220179: "systolic_bp",       # Non-invasive BP systolic
    220050: "systolic_bp",       # Arterial BP systolic (takes precedence if both present)
    220180: "diastolic_bp",      # Non-invasive BP diastolic
    220051: "diastolic_bp",      # Arterial BP diastolic
    220181: "mean_arterial_bp",  # Non-invasive MAP
    220052: "mean_arterial_bp",  # Arterial MAP — SOFA cardiovascular
    220210: "respiratory_rate",
    220277: "spo2",              # O2 Saturation Pulseoxymetry
    223762: "temperature_c",     # Temperature Celsius
    223761: "temperature_f",     # Temperature Fahrenheit (converted to °C in pipeline)
    220739: "gcs_eye",           # GCS - Eye Opening
    223900: "gcs_verbal",        # GCS - Verbal Response
    223901: "gcs_motor",         # GCS - Motor Response
}

# ─── ICD-9 comorbidity prefix → (category, readable_name, is_chronic) ────────
ICD9_CATEGORY_MAP = [
    # Hypertension
    ("401", "CARDIOVASCULAR", "Essential Hypertension", True),
    ("402", "CARDIOVASCULAR", "Hypertensive Heart Disease", True),
    ("403", "CARDIOVASCULAR", "Hypertensive Renal Disease", True),
    ("404", "CARDIOVASCULAR", "Hypertensive Heart and Renal Disease", True),
    # Coronary / ischaemic heart disease
    ("410", "CARDIOVASCULAR", "Acute Myocardial Infarction", False),
    ("411", "CARDIOVASCULAR", "Other Acute Ischaemic Heart Disease", False),
    ("412", "CARDIOVASCULAR", "Old Myocardial Infarction", True),
    ("413", "CARDIOVASCULAR", "Angina Pectoris", True),
    ("414", "CARDIOVASCULAR", "Coronary Artery Disease", True),
    ("440", "CARDIOVASCULAR", "Atherosclerosis", True),
    ("443", "CARDIOVASCULAR", "Peripheral Vascular Disease", True),
    ("425", "CARDIOVASCULAR", "Cardiomyopathy", True),
    ("427", "CARDIOVASCULAR", "Cardiac Dysrhythmia / Atrial Fibrillation", True),
    ("428", "CARDIOVASCULAR", "Heart Failure / Congestive Cardiac Failure", True),
    # Diabetes
    ("250", "ENDOCRINE", "Diabetes Mellitus", True),
    ("244", "ENDOCRINE", "Hypothyroidism", True),
    ("278", "ENDOCRINE", "Obesity", True),
    # Respiratory
    ("490", "RESPIRATORY", "Bronchitis", False),
    ("491", "RESPIRATORY", "Chronic Bronchitis (COPD)", True),
    ("492", "RESPIRATORY", "Emphysema", True),
    ("493", "RESPIRATORY", "Asthma", True),
    ("494", "RESPIRATORY", "Bronchiectasis", True),
    ("496", "RESPIRATORY", "COPD", True),
    ("515", "RESPIRATORY", "Pulmonary Fibrosis", True),
    # Renal
    ("585", "RENAL", "Chronic Kidney Disease", True),
    ("586", "RENAL", "Renal Failure Unspecified", True),
    ("584", "RENAL", "Acute Kidney Failure", False),
    ("403", "RENAL", "Hypertensive Renal Disease", True),
    # Hepatic
    ("571", "HEPATIC", "Chronic Liver Disease / Cirrhosis", True),
    ("572", "HEPATIC", "Liver Abscess / Late Effects", True),
    ("573", "HEPATIC", "Other Disorders of Liver", True),
    ("070", "HEPATIC", "Viral Hepatitis", False),
    # Immunocompromised / oncology handled separately by numeric range check
    ("042", "IMMUNOCOMPROMISED", "HIV Disease (AIDS)", True),
    ("043", "IMMUNOCOMPROMISED", "HIV-related Illness", True),
    ("279", "IMMUNOCOMPROMISED", "Immune Deficiency / Immunosuppression", True),
    # Neurological
    ("430", "NEUROLOGICAL", "Subarachnoid Haemorrhage", False),
    ("431", "NEUROLOGICAL", "Intracerebral Haemorrhage", False),
    ("433", "NEUROLOGICAL", "Occlusion of Precerebral Arteries (Stroke)", False),
    ("434", "NEUROLOGICAL", "Cerebral Artery Occlusion (Stroke)", False),
    ("436", "NEUROLOGICAL", "Acute Cerebrovascular Disease", False),
    ("332", "NEUROLOGICAL", "Parkinson's Disease", True),
    ("294", "NEUROLOGICAL", "Persistent Dementia", True),
    # Metabolic / electrolyte
    ("276", "METABOLIC", "Fluid and Electrolyte Disorder", False),
    ("277", "METABOLIC", "Metabolic and Immunity Disorder", True),
    # Haematologic
    ("280", "HEMATOLOGIC", "Iron Deficiency Anaemia", True),
    ("281", "HEMATOLOGIC", "Other Deficiency Anaemias", True),
    ("282", "HEMATOLOGIC", "Haemolytic Anaemias", True),
    ("284", "HEMATOLOGIC", "Aplastic Anaemia", True),
    ("285", "HEMATOLOGIC", "Other and Unspecified Anaemia", True),
    ("286", "HEMATOLOGIC", "Coagulation Defects (Haemophilia / DIC)", True),
    # Rheumatologic
    ("710", "AUTOIMMUNE", "Systemic Lupus Erythematosus (SLE)", True),
    ("714", "AUTOIMMUNE", "Rheumatoid Arthritis", True),
    ("720", "AUTOIMMUNE", "Ankylosing Spondylitis", True),
    # GI
    ("531", "GASTROINTESTINAL", "Gastric Ulcer", True),
    ("532", "GASTROINTESTINAL", "Duodenal Ulcer", True),
    ("534", "GASTROINTESTINAL", "Gastrojejunal Ulcer", True),
    ("555", "GASTROINTESTINAL", "Regional Enteritis / Crohn's Disease", True),
    ("556", "GASTROINTESTINAL", "Ulcerative Colitis", True),
]

# Valid physiological ranges for outlier filtering in CHARTEVENTS
VITAL_VALID_RANGES: Dict[str, Tuple[float, float]] = {
    "heart_rate": (0.0, 300.0),
    "systolic_bp": (20.0, 300.0),
    "diastolic_bp": (0.0, 250.0),
    "mean_arterial_bp": (10.0, 250.0),
    "respiratory_rate": (0.0, 70.0),
    "spo2": (50.0, 100.0),
    "temperature_c": (25.0, 45.0),
}


# ─── Database connection ──────────────────────────────────────────────────────

def get_connection() -> psycopg2.extensions.connection:
    sync_url = os.getenv("SYNC_DATABASE_URL")
    if not sync_url:
        raise EnvironmentError("SYNC_DATABASE_URL not set in .env — see .env.example")
    return psycopg2.connect(sync_url)


# ─── Phase 1: Patients ────────────────────────────────────────────────────────

def load_patients(conn, raw_dir: Path) -> Dict[int, str]:
    """
    Load PATIENTS.csv → patients table.
    Returns dict mapping mimic_subject_id (int) → our internal UUID (str).
    """
    csv_path = raw_dir / "PATIENTS.csv"
    if not csv_path.exists():
        log.warning("PATIENTS.csv not found at %s — skipping patient load", csv_path)
        return {}

    df = pd.read_csv(csv_path, usecols=["subject_id", "gender", "dob", "expire_flag"])
    df["dob"] = pd.to_datetime(df["dob"], errors="coerce")

    rows = []
    for _, row in df.iterrows():
        age = None
        if pd.notna(row["dob"]):
            # MIMIC-III shifts DOB by 300 years for patients aged >89 (HIPAA de-identification).
            # We detect this by checking if the calculated age would exceed a plausible maximum.
            age_approx = 2012 - row["dob"].year  # MIMIC data ends ~2012
            if age_approx > 200:
                age = 91          # represents ">89 years"
            elif 0 <= age_approx <= 110:
                age = age_approx
            # else: leave as None (implausible value)
        rows.append((
            str(uuid.uuid4()),
            int(row["subject_id"]),
            None,                                  # hospital_id — not in MIMIC
            f"MIMIC-{int(row['subject_id'])}",    # placeholder name preserving subject_id
            age,
            None,                                  # ward — set when patient is admitted
        ))

    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO patients (id, mimic_subject_id, hospital_id, name, age, ward)
            VALUES %s
            ON CONFLICT (mimic_subject_id) DO NOTHING
            """,
            rows,
        )
    conn.commit()
    log.info("Patients: inserted %d rows", len(rows))

    # Build and return the subject_id → UUID lookup map
    with conn.cursor() as cur:
        cur.execute(
            "SELECT mimic_subject_id, id FROM patients WHERE mimic_subject_id IS NOT NULL"
        )
        return {row[0]: str(row[1]) for row in cur.fetchall()}


# ─── Phase 2: ICU Admissions ─────────────────────────────────────────────────

def load_icu_admissions(
    conn, raw_dir: Path, subject_to_uuid: Dict[int, str]
) -> Dict[int, str]:
    """
    Load ICUSTAYS.csv (joined with ADMISSIONS.csv) → icu_admissions table.
    Returns dict mapping mimic_icustay_id (int) → our admission UUID (str).
    """
    icustays_path = raw_dir / "ICUSTAYS.csv"
    if not icustays_path.exists():
        log.warning("ICUSTAYS.csv not found — skipping ICU admissions load")
        return {}

    icu = pd.read_csv(
        icustays_path,
        usecols=["subject_id", "hadm_id", "icustay_id", "first_careunit",
                 "first_wardid", "intime", "outtime", "los"],
    )
    icu["intime"] = pd.to_datetime(icu["intime"], errors="coerce")
    icu["outtime"] = pd.to_datetime(icu["outtime"], errors="coerce")

    # Load admissions for hospital-level data (optional — gracefully absent)
    adm_index: Optional[pd.DataFrame] = None
    admissions_path = raw_dir / "ADMISSIONS.csv"
    if admissions_path.exists():
        adm_df = pd.read_csv(
            admissions_path,
            usecols=["subject_id", "hadm_id", "admittime", "dischtime",
                     "admission_type", "admission_location", "discharge_location",
                     "insurance", "marital_status", "ethnicity", "diagnosis",
                     "hospital_expire_flag"],
        )
        adm_df["admittime"] = pd.to_datetime(adm_df["admittime"], errors="coerce")
        adm_df["dischtime"] = pd.to_datetime(adm_df["dischtime"], errors="coerce")
        # Use hadm_id as index; keep first row if any duplicates
        adm_df = adm_df.drop_duplicates(subset="hadm_id")
        adm_index = adm_df.set_index("hadm_id")
    else:
        log.warning("ADMISSIONS.csv not found — ICU admissions will lack hospital-level fields")

    rows = []
    for _, row in icu.iterrows():
        sid = int(row["subject_id"])
        if sid not in subject_to_uuid:
            continue

        hadm_id = int(row["hadm_id"]) if pd.notna(row["hadm_id"]) else None
        a: Optional[pd.Series] = None
        if adm_index is not None and hadm_id is not None and hadm_id in adm_index.index:
            a = adm_index.loc[hadm_id]

        # ICU LOS is stored in days in MIMIC — convert to hours
        icu_los_hours = float(row["los"]) * 24.0 if pd.notna(row["los"]) else None

        # Hospital LOS from admittime / dischtime
        hosp_los_days = None
        if a is not None:
            admit = a.get("admittime")
            disch = a.get("dischtime")
            if pd.notna(admit) and pd.notna(disch):
                delta = disch - admit
                hosp_los_days = delta.total_seconds() / 86400.0

        hospital_expire = bool(a["hospital_expire_flag"]) if a is not None and pd.notna(a.get("hospital_expire_flag")) else False

        # Age at ICU admission (compute from intime vs stored DOB — approximated)
        age_at_admit = None   # enriched later; PATIENTS.csv DOB + intime gives exact age

        rows.append((
            str(uuid.uuid4()),
            subject_to_uuid[sid],
            hadm_id,
            int(row["icustay_id"]) if pd.notna(row["icustay_id"]) else None,
            a["admission_type"] if a is not None and pd.notna(a.get("admission_type")) else None,
            a["admission_location"] if a is not None and pd.notna(a.get("admission_location")) else None,
            a["discharge_location"] if a is not None and pd.notna(a.get("discharge_location")) else None,
            str(row["first_careunit"]) if pd.notna(row["first_careunit"]) else None,
            int(row["first_wardid"]) if pd.notna(row["first_wardid"]) else None,
            a["admittime"] if a is not None and pd.notna(a.get("admittime")) else None,
            a["dischtime"] if a is not None and pd.notna(a.get("dischtime")) else None,
            hosp_los_days,
            row["intime"] if pd.notna(row["intime"]) else None,
            row["outtime"] if pd.notna(row["outtime"]) else None,
            icu_los_hours,
            False,        # died_in_icu (would need deathtime overlap with ICU window — enriched separately)
            hospital_expire,
            hospital_expire,  # hospital_expire_flag mirrors died_in_hospital for MIMIC
            None,         # sofa_score — derived from vitals + labs after load
            None,         # apache_ii_score — not directly in MIMIC CSVs
            age_at_admit,
            a["insurance"] if a is not None and pd.notna(a.get("insurance")) else None,
            a["marital_status"] if a is not None and pd.notna(a.get("marital_status")) else None,
            a["ethnicity"] if a is not None and pd.notna(a.get("ethnicity")) else None,
            None,         # primary_icd9_code — joined from DIAGNOSES_ICD separately
            str(a["diagnosis"])[:500] if a is not None and pd.notna(a.get("diagnosis")) else None,
        ))

    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO icu_admissions (
                id, patient_id, mimic_hadm_id, mimic_icustay_id,
                admission_type, admission_source, discharge_disposition, icu_unit,
                ward_bed_id, hospital_admitted_at, hospital_discharged_at, hospital_los_days,
                icu_admitted_at, icu_discharged_at, icu_los_hours,
                died_in_icu, died_in_hospital, hospital_expire_flag,
                sofa_score, apache_ii_score, age_at_admission,
                insurance_type, marital_status, ethnicity,
                primary_icd9_code, primary_diagnosis_text
            )
            VALUES %s
            ON CONFLICT (mimic_icustay_id) DO NOTHING
            """,
            rows,
        )
    conn.commit()
    log.info("ICU admissions: inserted %d rows", len(rows))

    with conn.cursor() as cur:
        cur.execute(
            "SELECT mimic_icustay_id, id FROM icu_admissions WHERE mimic_icustay_id IS NOT NULL"
        )
        return {row[0]: str(row[1]) for row in cur.fetchall()}


# ─── Phase 3: Comorbidities ───────────────────────────────────────────────────

def _categorize_icd9(
    icd9: str, icd_name_lookup: Dict[str, str]
) -> Tuple[Optional[str], str, bool]:
    """
    Map an ICD-9-CM code to (category, condition_name, is_chronic).
    Returns (None, name, True) for codes that don't match known comorbidity prefixes.
    Handles ICD-9 malignancy range (140–208) separately.
    """
    for prefix, category, name, chronic in ICD9_CATEGORY_MAP:
        if icd9.startswith(prefix):
            return category, name, chronic

    # Malignant neoplasms 140–208 and neoplasms of uncertain behaviour 209–239
    try:
        code_num = int(icd9[:3])
        if 140 <= code_num <= 208:
            return "IMMUNOCOMPROMISED", "Malignant Neoplasm", True
        if 209 <= code_num <= 239:
            return "IMMUNOCOMPROMISED", "Neoplasm of Uncertain Behaviour", True
    except (ValueError, TypeError):
        pass

    # Return with no category — we still store the diagnosis for completeness
    readable = icd_name_lookup.get(icd9, icd9)
    return None, readable, True


def load_comorbidities(
    conn,
    raw_dir: Path,
    subject_to_uuid: Dict[int, str],
    icustay_to_uuid: Dict[int, str],
):
    """
    Load DIAGNOSES_ICD.csv → comorbidities table.
    Stores all mapped comorbidity diagnoses (unknown categories are included with category=NULL).
    """
    dx_path = raw_dir / "DIAGNOSES_ICD.csv"
    if not dx_path.exists():
        log.warning("DIAGNOSES_ICD.csv not found — skipping comorbidities")
        return

    # Build ICD-9 code → short title lookup
    icd_names: Dict[str, str] = {}
    dict_path = raw_dir / "D_ICD_DIAGNOSES.csv"
    if dict_path.exists():
        d = pd.read_csv(dict_path, usecols=["icd9_code", "short_title"])
        d["icd9_code"] = d["icd9_code"].astype(str).str.strip()
        icd_names = dict(zip(d["icd9_code"], d["short_title"]))
    else:
        log.warning("D_ICD_DIAGNOSES.csv not found — condition names will be raw ICD-9 codes")

    df = pd.read_csv(
        dx_path,
        usecols=["subject_id", "hadm_id", "seq_num", "icd9_code"],
        dtype={"icd9_code": str},
    )
    df["icd9_code"] = df["icd9_code"].astype(str).str.strip()

    BATCH = 5_000
    buffer = []
    inserted = 0

    for _, row in df.iterrows():
        sid = int(row["subject_id"])
        if sid not in subject_to_uuid:
            continue

        icd9 = str(row["icd9_code"])
        category, name, is_chronic = _categorize_icd9(icd9, icd_names)

        # Skip codes that have no category AND no readable name (raw numeric junk)
        if category is None and name == icd9 and len(icd9) < 3:
            continue

        seq = int(row["seq_num"]) if pd.notna(row["seq_num"]) else None
        hadm_id = int(row["hadm_id"]) if pd.notna(row["hadm_id"]) else None

        buffer.append((
            str(uuid.uuid4()),
            subject_to_uuid[sid],
            None,                  # admission_id FK — would require hadm_id→icustay join (future enrichment)
            hadm_id,
            icd9,
            None,                  # icd10_code — not in MIMIC (ICD-9 era data)
            name[:255],
            category,
            is_chronic,
            seq == 1,              # is_primary_admission_dx
            seq,
            "mimic",
        ))

        if len(buffer) >= BATCH:
            _flush_comorbidities(conn, buffer)
            inserted += len(buffer)
            buffer = []

    if buffer:
        _flush_comorbidities(conn, buffer)
        inserted += len(buffer)

    log.info("Comorbidities: inserted %d rows", inserted)


def _flush_comorbidities(conn, rows: list):
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO comorbidities (
                id, patient_id, admission_id, mimic_hadm_id,
                icd9_code, icd10_code, condition_name, category,
                is_chronic, is_primary_admission_dx, seq_num, source
            )
            VALUES %s
            """,
            rows,
        )
    conn.commit()


# ─── Phase 4: Lab Results ─────────────────────────────────────────────────────

def load_lab_results(conn, raw_dir: Path, subject_to_uuid: Dict[int, str]):
    """
    Load LABEVENTS.csv → lab_results table.
    File is ~1.5 GB uncompressed — processed in 100k-row chunks.

    Strategy: pivot long-format LABEVENTS (one row per test) into wide-format rows
    grouped by (subject_id, hadm_id, charttime). Records drawn at the exact same
    timestamp become a single wide row with each test as a column.
    """
    csv_path = raw_dir / "LABEVENTS.csv"
    if not csv_path.exists():
        log.warning("LABEVENTS.csv not found — skipping lab results")
        return

    relevant_ids = set(LAB_ITEM_MAP.keys())
    known_subjects = set(subject_to_uuid.keys())
    inserted = 0

    for chunk_idx, chunk in enumerate(
        pd.read_csv(
            csv_path,
            usecols=["subject_id", "hadm_id", "itemid", "charttime", "valuenum"],
            chunksize=CHUNK_SIZE,
            low_memory=False,
        )
    ):
        chunk = chunk[chunk["itemid"].isin(relevant_ids)]
        chunk = chunk[chunk["subject_id"].isin(known_subjects)]
        chunk["charttime"] = pd.to_datetime(chunk["charttime"], errors="coerce")
        chunk = chunk.dropna(subset=["charttime", "valuenum"])

        if chunk.empty:
            continue

        chunk["col"] = chunk["itemid"].map(LAB_ITEM_MAP)

        # Pivot: aggregate by (subject_id, hadm_id, charttime)
        # For rare duplicate item draws at same time, take the mean
        pivoted = (
            chunk.groupby(["subject_id", "hadm_id", "charttime"])
            .apply(lambda x: {col: x[x["col"] == col]["valuenum"].mean() for col in x["col"].unique()})
            .reset_index(name="labs")
        )

        rows = []
        for _, row in pivoted.iterrows():
            sid = int(row["subject_id"])
            labs: Dict[str, float] = row["labs"]

            # FiO2 in MIMIC LABEVENTS is stored as percentage (21–100); normalise to fraction
            fio2 = labs.get("fio2")
            if fio2 is not None and fio2 > 1.5:
                fio2 = fio2 / 100.0
                labs["fio2"] = fio2

            # Derived: PaO2/FiO2 ratio — core SOFA respiratory component
            pao2 = labs.get("pao2")
            pao2_fio2 = (pao2 / fio2) if (pao2 is not None and fio2 is not None and fio2 > 0) else None

            hadm_id_val = int(row["hadm_id"]) if pd.notna(row["hadm_id"]) else None

            rows.append((
                str(uuid.uuid4()),
                subject_to_uuid[sid],
                None,           # admission_id FK — enrichable later via hadm_id→icustay join
                hadm_id_val,
                row["charttime"],
                # CBC
                labs.get("wbc"),
                labs.get("hemoglobin"),
                labs.get("hematocrit"),
                labs.get("platelets"),
                # BMP
                labs.get("sodium"),
                labs.get("potassium"),
                labs.get("chloride"),
                labs.get("bicarbonate"),
                labs.get("bun"),
                labs.get("creatinine"),
                labs.get("glucose"),
                # LFTs
                labs.get("bilirubin_total"),
                labs.get("bilirubin_direct"),
                labs.get("ast"),
                labs.get("alt"),
                labs.get("alkaline_phosphatase"),
                labs.get("albumin"),
                # Coagulation
                labs.get("inr"),
                labs.get("prothrombin_time"),
                labs.get("aptt"),
                # ABG
                labs.get("ph"),
                labs.get("pao2"),
                labs.get("paco2"),
                fio2,
                pao2_fio2,
                labs.get("base_excess"),
                # Sepsis markers
                labs.get("lactate"),
                None,           # procalcitonin — not in MIMIC (add for live Indian hospital feeds)
                None,           # crp — not in MIMIC
                None,           # urine_wbc
                None,           # urine_nitrites
                "mimic",
            ))

        if rows:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO lab_results (
                        id, patient_id, admission_id, mimic_hadm_id, collected_at,
                        wbc, hemoglobin, hematocrit, platelets,
                        sodium, potassium, chloride, bicarbonate, bun, creatinine, glucose,
                        bilirubin_total, bilirubin_direct, ast, alt, alkaline_phosphatase, albumin,
                        inr, prothrombin_time, aptt,
                        ph, pao2, paco2, fio2, pao2_fio2_ratio, base_excess,
                        lactate, procalcitonin, crp, urine_wbc, urine_nitrites, source
                    )
                    VALUES %s
                    ON CONFLICT DO NOTHING
                    """,
                    rows,
                )
            conn.commit()
            inserted += len(rows)

        if (chunk_idx + 1) % 20 == 0:
            log.info("  Lab results: chunk %d processed, total inserted so far: %d",
                     chunk_idx + 1, inserted)

    log.info("Lab results: %d wide-format rows inserted total", inserted)


# ─── Phase 5: Vital Readings (CHARTEVENTS) ───────────────────────────────────

def load_vital_readings(
    conn, raw_dir: Path, subject_to_uuid: Dict[int, str], skip: bool = False
):
    """
    Load CHARTEVENTS.csv → vital_readings table.

    WARNING: CHARTEVENTS.csv is ~330 million rows (~33 GB compressed).
    Set skip=True during development to save time.

    Strategy:
    - Filter to the ~14 relevant vital sign item IDs (drops ~99% of rows immediately)
    - Drop rows with charting errors (error column != 0)
    - Convert Fahrenheit temperature readings to Celsius
    - Pivot by (subject_id, icustay_id, charttime) for one row per monitoring snapshot
    - Apply physiological range filters to remove obvious charting errors
    - Compute GCS total where all three components are present
    """
    if skip:
        log.info("Skipping CHARTEVENTS.csv load (--skip-chartevents flag set)")
        return

    csv_path = raw_dir / "CHARTEVENTS.csv"
    if not csv_path.exists():
        log.warning("CHARTEVENTS.csv not found at %s — skipping vital readings", csv_path)
        return

    relevant_ids = set(VITAL_ITEM_MAP.keys())
    known_subjects = set(subject_to_uuid.keys())
    inserted = 0
    # Use larger chunks for CHARTEVENTS — we drop 99% of rows on the item ID filter
    CHART_CHUNK = CHUNK_SIZE * 5

    for chunk_idx, chunk in enumerate(
        pd.read_csv(
            csv_path,
            usecols=["subject_id", "icustay_id", "itemid", "charttime", "valuenum", "error"],
            chunksize=CHART_CHUNK,
            low_memory=False,
        )
    ):
        # Drop rows flagged as charting errors by the bedside nurse
        chunk = chunk[chunk["error"].isna() | (chunk["error"] == 0)]

        chunk = chunk[chunk["itemid"].isin(relevant_ids)]
        chunk = chunk[chunk["subject_id"].isin(known_subjects)]
        chunk["charttime"] = pd.to_datetime(chunk["charttime"], errors="coerce")
        chunk = chunk.dropna(subset=["charttime", "valuenum"])

        if chunk.empty:
            continue

        chunk["col"] = chunk["itemid"].map(VITAL_ITEM_MAP)

        # Convert Fahrenheit → Celsius for temperature_f items
        f_mask = chunk["itemid"] == 223761
        chunk.loc[f_mask, "valuenum"] = (chunk.loc[f_mask, "valuenum"] - 32.0) * 5.0 / 9.0
        chunk.loc[f_mask, "col"] = "temperature_c"

        # Pivot: group by monitoring snapshot (subject + ICU stay + timestamp)
        # For duplicates (e.g. both arterial and non-invasive BP at same time), take mean
        pivoted = (
            chunk.groupby(["subject_id", "icustay_id", "charttime"])
            .apply(
                lambda x: {
                    col: x[x["col"] == col]["valuenum"].mean()
                    for col in x["col"].unique()
                }
            )
            .reset_index(name="vitals")
        )

        rows = []
        for _, row in pivoted.iterrows():
            sid = int(row["subject_id"])
            vitals: Dict[str, float] = row["vitals"]

            # Apply physiological range filters — out-of-range values are charting errors
            for col, (lo, hi) in VITAL_VALID_RANGES.items():
                val = vitals.get(col)
                if val is not None and not (lo <= val <= hi):
                    vitals[col] = None

            # Compute GCS total if all three components were charted at this timestamp
            gcs_eye = vitals.get("gcs_eye")
            gcs_verbal = vitals.get("gcs_verbal")
            gcs_motor = vitals.get("gcs_motor")
            gcs_total = None
            if gcs_eye is not None and gcs_verbal is not None and gcs_motor is not None:
                raw_gcs = gcs_eye + gcs_verbal + gcs_motor
                if 3 <= raw_gcs <= 15:   # valid GCS range
                    gcs_total = int(raw_gcs)

            rows.append((
                str(uuid.uuid4()),
                subject_to_uuid[sid],
                row["charttime"],
                vitals.get("heart_rate"),
                vitals.get("systolic_bp"),
                vitals.get("diastolic_bp"),
                vitals.get("mean_arterial_bp"),
                vitals.get("spo2"),
                vitals.get("temperature_c"),
                vitals.get("respiratory_rate"),
                gcs_total,
            ))

        if rows:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO vital_readings (
                        id, patient_id, recorded_at,
                        heart_rate, systolic_bp, diastolic_bp, mean_arterial_bp,
                        spo2, temperature_c, respiratory_rate, gcs_total
                    )
                    VALUES %s
                    ON CONFLICT DO NOTHING
                    """,
                    rows,
                )
            conn.commit()
            inserted += len(rows)

        if (chunk_idx + 1) % 100 == 0:
            log.info(
                "  Vital readings: chunk %d (~%dM source rows scanned), inserted so far: %d",
                chunk_idx + 1,
                (chunk_idx + 1) * CHART_CHUNK // 1_000_000,
                inserted,
            )

    log.info("Vital readings: %d rows inserted total", inserted)


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Load MIMIC-III CSV data into sepsis-watch TimescaleDB"
    )
    parser.add_argument(
        "--patients-only",
        action="store_true",
        help="Only load the patients table (useful for initial setup / testing)",
    )
    parser.add_argument(
        "--skip-chartevents",
        action="store_true",
        help="Skip CHARTEVENTS.csv (~33 GB — use this flag during development)",
    )
    parser.add_argument(
        "--skip-labs",
        action="store_true",
        help="Skip LABEVENTS.csv",
    )
    args = parser.parse_args()

    log.info("Connecting to database (SYNC_DATABASE_URL)...")
    conn = get_connection()

    try:
        log.info("=== Phase 1: Patients ===")
        subject_to_uuid = load_patients(conn, RAW_DIR)
        log.info("Subject→UUID map: %d entries", len(subject_to_uuid))

        if args.patients_only:
            log.info("--patients-only flag set — stopping after patient load.")
            return

        log.info("=== Phase 2: ICU Admissions ===")
        icustay_to_uuid = load_icu_admissions(conn, RAW_DIR, subject_to_uuid)
        log.info("ICUstay→UUID map: %d entries", len(icustay_to_uuid))

        log.info("=== Phase 3: Comorbidities ===")
        load_comorbidities(conn, RAW_DIR, subject_to_uuid, icustay_to_uuid)

        if not args.skip_labs:
            log.info("=== Phase 4: Lab Results ===")
            load_lab_results(conn, RAW_DIR, subject_to_uuid)
        else:
            log.info("Phase 4 skipped (--skip-labs)")

        log.info("=== Phase 5: Vital Readings (CHARTEVENTS) ===")
        load_vital_readings(conn, RAW_DIR, subject_to_uuid, skip=args.skip_chartevents)

        log.info("=== MIMIC-III load complete ===")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
