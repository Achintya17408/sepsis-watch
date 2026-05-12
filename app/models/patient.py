from sqlalchemy import Column, String, Text, Float, DateTime, Integer, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
import uuid
from datetime import datetime


class Patient(Base):
    __tablename__ = "patients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mimic_subject_id = Column(Integer, unique=True, nullable=True)  # links to MIMIC-III
    hospital_id = Column(String, nullable=True)                      # hospital MRN (Indian hospital)
    name = Column(String, nullable=False)
    age = Column(Integer)
    ward = Column(String)                                            # ICU / CCU / General
    created_at = Column(DateTime, default=datetime.utcnow)


class IcuAdmission(Base):
    """
    One row per ICU stay. A patient can have multiple ICU admissions.
    Links MIMIC hadm_id (hospital admission) and icustay_id (ICU stay) to our patient UUID.
    """
    __tablename__ = "icu_admissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)

    # MIMIC-III identifiers (null for non-MIMIC / live Indian patients)
    mimic_hadm_id = Column(Integer, nullable=True, index=True)      # hospital admission ID from ADMISSIONS.csv
    mimic_icustay_id = Column(Integer, nullable=True, unique=True, index=True)  # ICU stay ID from ICUSTAYS.csv

    # Admission triage classification
    admission_type = Column(String, nullable=True)                  # EMERGENCY / ELECTIVE / URGENT / NEWBORN
    admission_source = Column(String, nullable=True)                # EMERGENCY ROOM / TRANSFER FROM HOSP/EXTRAM / CLINIC REFERRAL
    discharge_disposition = Column(String, nullable=True)           # HOME / DIED / SNF / REHAB / EXPIRED / LEFT AMA

    # ICU unit & physical location
    icu_unit = Column(String, nullable=True)                        # MICU / SICU / CSRU / CCU / TSICU / NICU
    ward_bed_id = Column(Integer, nullable=True)                    # physical ward/bed number in hospital

    # Admission & discharge timestamps (hospital-level)
    hospital_admitted_at = Column(DateTime, nullable=True)
    hospital_discharged_at = Column(DateTime, nullable=True)
    hospital_los_days = Column(Float, nullable=True)               # hospital length of stay in days

    # ICU-level timestamps
    icu_admitted_at = Column(DateTime, nullable=True)
    icu_discharged_at = Column(DateTime, nullable=True)
    icu_los_hours = Column(Float, nullable=True)                    # ICU length of stay in hours

    # Patient outcomes
    died_in_icu = Column(Boolean, default=False)
    died_in_hospital = Column(Boolean, default=False)
    hospital_expire_flag = Column(Boolean, default=False)           # raw MIMIC flag

    # Clinical severity scores on admission
    sofa_score = Column(Integer, nullable=True)                     # Sequential Organ Failure Assessment (0–24)
    apache_ii_score = Column(Integer, nullable=True)               # Acute Physiology and Chronic Health Evaluation II (0–71)

    # Demographics captured at admission time
    age_at_admission = Column(Integer, nullable=True)              # exact age on ICU admit day
    insurance_type = Column(String, nullable=True)                 # Medicare / Medicaid / Private / Government / Self Pay
    marital_status = Column(String, nullable=True)                 # MARRIED / SINGLE / WIDOWED / DIVORCED
    ethnicity = Column(String, nullable=True)                      # e.g. WHITE / BLACK/AFRICAN AMERICAN / ASIAN / HISPANIC

    # Primary diagnosis for this admission
    primary_icd9_code = Column(String, nullable=True)
    primary_diagnosis_text = Column(String, nullable=True)         # human-readable e.g. "SEPSIS" / "PNEUMONIA"

    created_at = Column(DateTime, default=datetime.utcnow)


class VitalReading(Base):
    """
    Time-series vitals table — converted to a TimescaleDB hypertable on recorded_at.

    TimescaleDB requires the partition column (recorded_at) to be part of any
    unique index including the primary key. We use a composite PK (id, recorded_at)
    to satisfy this constraint while still having a unique row identifier.

    Covers all parameters needed to compute SOFA cardiovascular + neurological scores.
    """
    __tablename__ = "vital_readings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    recorded_at = Column(DateTime, nullable=False, primary_key=True)  # composite PK + time dimension

    # Haemodynamic parameters
    heart_rate = Column(Float, nullable=True)                       # bpm (normal 60–100)
    systolic_bp = Column(Float, nullable=True)                      # mmHg (normal 90–140)
    diastolic_bp = Column(Float, nullable=True)                     # mmHg (normal 60–90)
    mean_arterial_bp = Column(Float, nullable=True)                 # mmHg (normal 70–105) — SOFA cardiovascular

    # Respiratory
    spo2 = Column(Float, nullable=True)                             # % peripheral O2 saturation (normal >94)
    respiratory_rate = Column(Float, nullable=True)                 # breaths/min (normal 12–20)

    # Temperature
    temperature_c = Column(Float, nullable=True)                    # Celsius — Indian standard (normal 36.1–37.2)

    # Neurological — SOFA neurological component
    gcs_total = Column(Integer, nullable=True)                      # Glasgow Coma Scale total (3–15; <15 = abnormal)


class LabResult(Base):
    """
    Wide-format lab results table — one row per (patient, draw-time) bundle.
    Converted to a TimescaleDB hypertable on collected_at.

    Covers all components needed for Sepsis-3 SOFA score:
      Respiratory  → PaO2/FiO2 ratio
      Coagulation  → Platelets
      Hepatic      → Bilirubin
      Renal        → Creatinine
      Neurological → (from vital_readings.gcs_total)
      Cardiovascular → (from vital_readings.mean_arterial_bp + vasopressors, future)
    Also includes lactate for septic shock assessment (lactate >2 mmol/L).
    """
    __tablename__ = "lab_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    admission_id = Column(UUID(as_uuid=True), ForeignKey("icu_admissions.id"), nullable=True)
    mimic_hadm_id = Column(Integer, nullable=True, index=True)

    collected_at = Column(DateTime, nullable=False, primary_key=True)  # composite PK for TimescaleDB hypertable

    # ── Complete Blood Count (CBC) ────────────────────────────────────────────
    wbc = Column(Float, nullable=True)                              # White blood cells, 10³/µL  (normal 4.5–11.0)
    hemoglobin = Column(Float, nullable=True)                       # g/dL                       (normal 12.0–17.5)
    hematocrit = Column(Float, nullable=True)                       # %                          (normal 36–50)
    platelets = Column(Float, nullable=True)                        # 10³/µL                     (normal 150–400) — SOFA coagulation

    # ── Basic Metabolic Panel (BMP) ───────────────────────────────────────────
    sodium = Column(Float, nullable=True)                           # mEq/L   (normal 136–145)
    potassium = Column(Float, nullable=True)                        # mEq/L   (normal 3.5–5.0)
    chloride = Column(Float, nullable=True)                         # mEq/L   (normal 98–107)
    bicarbonate = Column(Float, nullable=True)                      # mEq/L   (normal 22–29)
    bun = Column(Float, nullable=True)                              # Blood urea nitrogen, mg/dL (normal 7–25)
    creatinine = Column(Float, nullable=True)                       # mg/dL   (normal 0.6–1.3) — SOFA renal
    glucose = Column(Float, nullable=True)                          # mg/dL   (normal 70–100)

    # ── Liver Function Tests (LFTs) ───────────────────────────────────────────
    bilirubin_total = Column(Float, nullable=True)                  # mg/dL (normal 0.1–1.2) — SOFA hepatic
    bilirubin_direct = Column(Float, nullable=True)                 # mg/dL (normal <0.3)
    ast = Column(Float, nullable=True)                              # Aspartate aminotransferase, U/L (normal 10–40)
    alt = Column(Float, nullable=True)                              # Alanine aminotransferase, U/L   (normal 7–56)
    alkaline_phosphatase = Column(Float, nullable=True)             # U/L (normal 44–147)
    albumin = Column(Float, nullable=True)                          # g/dL (normal 3.5–5.0)

    # ── Coagulation Panel ─────────────────────────────────────────────────────
    inr = Column(Float, nullable=True)                              # International Normalized Ratio (normal 0.8–1.2)
    prothrombin_time = Column(Float, nullable=True)                 # seconds (normal 11.0–13.5)
    aptt = Column(Float, nullable=True)                             # Activated Partial Thromboplastin Time, sec (normal 25–35)

    # ── Arterial Blood Gas (ABG) ──────────────────────────────────────────────
    ph = Column(Float, nullable=True)                               # (normal 7.35–7.45)
    pao2 = Column(Float, nullable=True)                             # Partial pressure O2, mmHg (normal 75–100) — SOFA respiratory
    paco2 = Column(Float, nullable=True)                            # Partial pressure CO2, mmHg (normal 35–45)
    fio2 = Column(Float, nullable=True)                             # Fraction of inspired O2, 0.21–1.0
    pao2_fio2_ratio = Column(Float, nullable=True)                  # PaO2/FiO2 ratio (normal >400) — SOFA respiratory
    base_excess = Column(Float, nullable=True)                      # mEq/L (normal -2 to +2)

    # ── Sepsis-specific markers ───────────────────────────────────────────────
    lactate = Column(Float, nullable=True)                          # mmol/L (normal <2.0) — tissue hypoperfusion / septic shock marker
    procalcitonin = Column(Float, nullable=True)                    # ng/mL (normal <0.1) — bacterial infection marker (live hospitals)
    crp = Column(Float, nullable=True)                              # C-reactive protein, mg/L (normal <10) — inflammation marker

    # ── Urinalysis (relevant for UTI-related sepsis source) ──────────────────
    urine_wbc = Column(Float, nullable=True)                        # cells/HPF (normal <5)
    urine_nitrites = Column(String, nullable=True)                  # Positive / Negative

    source = Column(String, default="mimic")                        # mimic / live / manual
    created_at = Column(DateTime, default=datetime.utcnow)


class Doctor(Base):
    """
    Clinicians who can receive sepsis alerts — doctors, nurses, intensivists.
    Used for WhatsApp/SMS routing by the Twilio notification layer.
    """
    __tablename__ = "doctors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(String, unique=True, nullable=True)        # hospital staff ID / payroll number
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)                           # DOCTOR / NURSE / ADMIN / RESIDENT / FELLOW / INTENSIVIST
    specialization = Column(String, nullable=True)                  # Intensivist / Pulmonologist / Cardiologist / Nephrologist / etc.

    # Alert routing contact details
    phone_whatsapp = Column(String, nullable=True)                  # +91XXXXXXXXXX — primary WhatsApp alert channel
    phone_backup = Column(String, nullable=True)                    # fallback SMS number
    email = Column(String, unique=True, nullable=True)              # for email alerts

    # Ward assignment determines which patient alerts are routed here
    ward_assignment = Column(String, nullable=True)                 # MICU / SICU / CCU / CSRU / General / All

    # On-call state (updated by scheduling system or manually)
    is_on_call = Column(Boolean, default=False)
    on_call_start = Column(DateTime, nullable=True)
    on_call_end = Column(DateTime, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SepsisAlert(Base):
    __tablename__ = "sepsis_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    admission_id = Column(UUID(as_uuid=True), ForeignKey("icu_admissions.id"), nullable=True)
    model_version_id = Column(UUID(as_uuid=True), ForeignKey("ml_model_versions.id"), nullable=True)

    risk_score = Column(Float, nullable=False)                      # 0.0–1.0 from LSTM model
    alert_level = Column(String, nullable=True)                     # LOW / MEDIUM / HIGH / CRITICAL
    triggered_at = Column(DateTime, default=datetime.utcnow)
    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(String, nullable=True)                 # doctor name or ID (deprecated — use AlertNotification)
    acknowledged_at = Column(DateTime, nullable=True)
    clinical_summary = Column(Text, nullable=True)                  # LangGraph agent-generated clinical narrative


class AlertNotification(Base):
    """
    One row per (alert × doctor × channel) delivery attempt.
    Tracks the full Twilio delivery lifecycle: PENDING → SENT → DELIVERED → READ.
    """
    __tablename__ = "alert_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id = Column(UUID(as_uuid=True), ForeignKey("sepsis_alerts.id"), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("doctors.id"), nullable=False)

    channel = Column(String, nullable=False)                        # WHATSAPP / SMS / EMAIL / IN_APP / PAGER

    # Twilio delivery tracking
    twilio_message_sid = Column(String, nullable=True)              # e.g. SM1234abcd — used for status webhook lookups
    twilio_account_sid = Column(String, nullable=True)
    destination_number = Column(String, nullable=True)              # actual E.164 phone number used for send

    # Delivery lifecycle timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)                       # time we called Twilio API successfully
    delivered_at = Column(DateTime, nullable=True)                  # carrier delivery confirmation (Twilio webhook)
    read_at = Column(DateTime, nullable=True)                       # read receipt / seen (WhatsApp only)

    # Status
    delivery_status = Column(String, default="PENDING")            # PENDING / QUEUED / SENT / DELIVERED / READ / FAILED / UNDELIVERABLE
    failure_reason = Column(String, nullable=True)                  # e.g. "Invalid number" / "Twilio error 20003" / "Carrier unreachable"
    retry_count = Column(Integer, default=0)
    last_retry_at = Column(DateTime, nullable=True)

    # Audit — snapshot of what was sent (first 500 chars)
    message_preview = Column(String, nullable=True)


class Comorbidity(Base):
    """
    Pre-existing and chronic conditions per patient/admission.
    Loaded from MIMIC DIAGNOSES_ICD.csv; also supports live EHR entry.
    Used by the LangGraph agent to enrich clinical summaries and by the
    LSTM model as static patient features.
    """
    __tablename__ = "comorbidities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    admission_id = Column(UUID(as_uuid=True), ForeignKey("icu_admissions.id"), nullable=True)
    mimic_hadm_id = Column(Integer, nullable=True)                  # for cross-referencing without joining

    # Diagnosis coding
    icd9_code = Column(String, nullable=True)                       # ICD-9-CM code (MIMIC standard)
    icd10_code = Column(String, nullable=True)                      # ICD-10-CM code (live Indian hospitals)
    condition_name = Column(String, nullable=False)                 # human-readable name e.g. "Type 2 Diabetes Mellitus"

    # Clinical classification
    category = Column(String, nullable=True)                        # CARDIOVASCULAR / RESPIRATORY / RENAL / HEPATIC /
                                                                    # ENDOCRINE / IMMUNOCOMPROMISED / NEUROLOGICAL /
                                                                    # METABOLIC / HEMATOLOGIC
    is_chronic = Column(Boolean, default=True)                      # True = chronic comorbidity; False = acute condition
    is_primary_admission_dx = Column(Boolean, default=False)        # True if seq_num=1 in MIMIC (reason for admission)
    seq_num = Column(Integer, nullable=True)                        # MIMIC diagnosis sequence number (1 = primary)

    diagnosed_at = Column(DateTime, nullable=True)                  # date first recorded (hospital admission time for MIMIC)
    source = Column(String, default="mimic")                        # mimic / manual / ehr
    created_at = Column(DateTime, default=datetime.utcnow)


class MlModelVersion(Base):
    """
    Registry of trained ML model checkpoints.
    SepsisAlert.model_version_id FK links every prediction to the exact model
    that produced it — critical for clinical audit, debugging, and model comparison.
    """
    __tablename__ = "ml_model_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name = Column(String, nullable=False)                     # sepsis_lstm / retina_efficientnet
    version_tag = Column(String, unique=True, nullable=False)       # semantic version e.g. v1.0.0 / v1.2.1
    framework = Column(String, nullable=True)                       # pytorch / sklearn
    architecture = Column(String, nullable=True)                    # LSTM+Attention / BiGRU / EfficientNet-B4 / ViT-B16

    # Training provenance
    trained_at = Column(DateTime, nullable=True)
    training_data_description = Column(String, nullable=True)       # e.g. "MIMIC-III 2001–2012, 40k ICU stays, 36h sliding windows"
    training_samples = Column(Integer, nullable=True)               # number of training examples
    validation_samples = Column(Integer, nullable=True)
    input_features_json = Column(Text, nullable=True)               # JSON array of feature column names in exact model input order
    sequence_length_hours = Column(Integer, nullable=True)          # lookback window in hours (e.g. 24, 48)

    # Performance on held-out test set (Sepsis-3 positive vs negative)
    auroc = Column(Float, nullable=True)                            # Area under ROC curve — target >0.85
    auprc = Column(Float, nullable=True)                            # Area under Precision-Recall curve
    sensitivity = Column(Float, nullable=True)                      # True positive rate at decision_threshold
    specificity = Column(Float, nullable=True)                      # True negative rate at decision_threshold
    ppv = Column(Float, nullable=True)                              # Positive predictive value (precision)
    npv = Column(Float, nullable=True)                              # Negative predictive value
    f1_score = Column(Float, nullable=True)

    decision_threshold = Column(Float, nullable=True, default=0.5)  # risk score above this triggers a SepsisAlert
    artifact_path = Column(String, nullable=True)                   # path to .pt / .pkl checkpoint relative to workspace root

    is_active = Column(Boolean, default=False)                      # only one model per model_name should be active at a time
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
