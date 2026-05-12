"""add_clinical_tables

Adds all new clinical tables required by the full sepsis-watch data model:
  - icu_admissions
  - lab_results        (TimescaleDB hypertable — composite PK on collected_at)
  - doctors
  - alert_notifications
  - comorbidities
  - ml_model_versions

Also alters existing tables:
  - vital_readings: ADD COLUMN mean_arterial_bp, gcs_total
  - sepsis_alerts:  ADD COLUMN admission_id, model_version_id, acknowledged_at

Revision ID: f8a9b0c1d2e3
Revises: b306fa2375da
Create Date: 2026-04-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "b306fa2375da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ml_model_versions (no FKs — create first so SepsisAlert can reference it) ──
    op.create_table(
        "ml_model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("version_tag", sa.String(), nullable=False),
        sa.Column("framework", sa.String(), nullable=True),
        sa.Column("architecture", sa.String(), nullable=True),
        sa.Column("trained_at", sa.DateTime(), nullable=True),
        sa.Column("training_data_description", sa.String(), nullable=True),
        sa.Column("training_samples", sa.Integer(), nullable=True),
        sa.Column("validation_samples", sa.Integer(), nullable=True),
        sa.Column("input_features_json", sa.Text(), nullable=True),
        sa.Column("sequence_length_hours", sa.Integer(), nullable=True),
        sa.Column("auroc", sa.Float(), nullable=True),
        sa.Column("auprc", sa.Float(), nullable=True),
        sa.Column("sensitivity", sa.Float(), nullable=True),
        sa.Column("specificity", sa.Float(), nullable=True),
        sa.Column("ppv", sa.Float(), nullable=True),
        sa.Column("npv", sa.Float(), nullable=True),
        sa.Column("f1_score", sa.Float(), nullable=True),
        sa.Column("decision_threshold", sa.Float(), nullable=True),
        sa.Column("artifact_path", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_tag"),
    )

    # ── doctors ──
    op.create_table(
        "doctors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("specialization", sa.String(), nullable=True),
        sa.Column("phone_whatsapp", sa.String(), nullable=True),
        sa.Column("phone_backup", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("ward_assignment", sa.String(), nullable=True),
        sa.Column("is_on_call", sa.Boolean(), nullable=True),
        sa.Column("on_call_start", sa.DateTime(), nullable=True),
        sa.Column("on_call_end", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id"),
        sa.UniqueConstraint("email"),
    )

    # ── icu_admissions ──
    op.create_table(
        "icu_admissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mimic_hadm_id", sa.Integer(), nullable=True),
        sa.Column("mimic_icustay_id", sa.Integer(), nullable=True),
        sa.Column("admission_type", sa.String(), nullable=True),
        sa.Column("admission_source", sa.String(), nullable=True),
        sa.Column("discharge_disposition", sa.String(), nullable=True),
        sa.Column("icu_unit", sa.String(), nullable=True),
        sa.Column("ward_bed_id", sa.Integer(), nullable=True),
        sa.Column("hospital_admitted_at", sa.DateTime(), nullable=True),
        sa.Column("hospital_discharged_at", sa.DateTime(), nullable=True),
        sa.Column("hospital_los_days", sa.Float(), nullable=True),
        sa.Column("icu_admitted_at", sa.DateTime(), nullable=True),
        sa.Column("icu_discharged_at", sa.DateTime(), nullable=True),
        sa.Column("icu_los_hours", sa.Float(), nullable=True),
        sa.Column("died_in_icu", sa.Boolean(), nullable=True),
        sa.Column("died_in_hospital", sa.Boolean(), nullable=True),
        sa.Column("hospital_expire_flag", sa.Boolean(), nullable=True),
        sa.Column("sofa_score", sa.Integer(), nullable=True),
        sa.Column("apache_ii_score", sa.Integer(), nullable=True),
        sa.Column("age_at_admission", sa.Integer(), nullable=True),
        sa.Column("insurance_type", sa.String(), nullable=True),
        sa.Column("marital_status", sa.String(), nullable=True),
        sa.Column("ethnicity", sa.String(), nullable=True),
        sa.Column("primary_icd9_code", sa.String(), nullable=True),
        sa.Column("primary_diagnosis_text", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mimic_icustay_id"),
    )
    op.create_index("ix_icu_admissions_patient_id", "icu_admissions", ["patient_id"])
    op.create_index("ix_icu_admissions_mimic_hadm_id", "icu_admissions", ["mimic_hadm_id"])

    # ── lab_results — composite PK (id, collected_at) for TimescaleDB hypertable ──
    op.create_table(
        "lab_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("admission_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mimic_hadm_id", sa.Integer(), nullable=True),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        # CBC
        sa.Column("wbc", sa.Float(), nullable=True),
        sa.Column("hemoglobin", sa.Float(), nullable=True),
        sa.Column("hematocrit", sa.Float(), nullable=True),
        sa.Column("platelets", sa.Float(), nullable=True),
        # BMP
        sa.Column("sodium", sa.Float(), nullable=True),
        sa.Column("potassium", sa.Float(), nullable=True),
        sa.Column("chloride", sa.Float(), nullable=True),
        sa.Column("bicarbonate", sa.Float(), nullable=True),
        sa.Column("bun", sa.Float(), nullable=True),
        sa.Column("creatinine", sa.Float(), nullable=True),
        sa.Column("glucose", sa.Float(), nullable=True),
        # LFTs
        sa.Column("bilirubin_total", sa.Float(), nullable=True),
        sa.Column("bilirubin_direct", sa.Float(), nullable=True),
        sa.Column("ast", sa.Float(), nullable=True),
        sa.Column("alt", sa.Float(), nullable=True),
        sa.Column("alkaline_phosphatase", sa.Float(), nullable=True),
        sa.Column("albumin", sa.Float(), nullable=True),
        # Coagulation
        sa.Column("inr", sa.Float(), nullable=True),
        sa.Column("prothrombin_time", sa.Float(), nullable=True),
        sa.Column("aptt", sa.Float(), nullable=True),
        # ABG
        sa.Column("ph", sa.Float(), nullable=True),
        sa.Column("pao2", sa.Float(), nullable=True),
        sa.Column("paco2", sa.Float(), nullable=True),
        sa.Column("fio2", sa.Float(), nullable=True),
        sa.Column("pao2_fio2_ratio", sa.Float(), nullable=True),
        sa.Column("base_excess", sa.Float(), nullable=True),
        # Sepsis markers
        sa.Column("lactate", sa.Float(), nullable=True),
        sa.Column("procalcitonin", sa.Float(), nullable=True),
        sa.Column("crp", sa.Float(), nullable=True),
        # Urinalysis
        sa.Column("urine_wbc", sa.Float(), nullable=True),
        sa.Column("urine_nitrites", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["admission_id"], ["icu_admissions.id"]),
        sa.PrimaryKeyConstraint("id", "collected_at"),  # composite PK required by TimescaleDB
    )
    op.create_index("ix_lab_results_patient_id", "lab_results", ["patient_id"])
    op.create_index("ix_lab_results_mimic_hadm_id", "lab_results", ["mimic_hadm_id"])

    # ── comorbidities ──
    op.create_table(
        "comorbidities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("admission_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mimic_hadm_id", sa.Integer(), nullable=True),
        sa.Column("icd9_code", sa.String(), nullable=True),
        sa.Column("icd10_code", sa.String(), nullable=True),
        sa.Column("condition_name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("is_chronic", sa.Boolean(), nullable=True),
        sa.Column("is_primary_admission_dx", sa.Boolean(), nullable=True),
        sa.Column("seq_num", sa.Integer(), nullable=True),
        sa.Column("diagnosed_at", sa.DateTime(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["admission_id"], ["icu_admissions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comorbidities_patient_id", "comorbidities", ["patient_id"])

    # ── alert_notifications ──
    op.create_table(
        "alert_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("twilio_message_sid", sa.String(), nullable=True),
        sa.Column("twilio_account_sid", sa.String(), nullable=True),
        sa.Column("destination_number", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("delivery_status", sa.String(), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=True),
        sa.Column("last_retry_at", sa.DateTime(), nullable=True),
        sa.Column("message_preview", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["alert_id"], ["sepsis_alerts.id"]),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── Alter vital_readings: add MAP and GCS (work fine on TimescaleDB hypertables) ──
    op.add_column("vital_readings", sa.Column("mean_arterial_bp", sa.Float(), nullable=True))
    op.add_column("vital_readings", sa.Column("gcs_total", sa.Integer(), nullable=True))

    # ── Alter sepsis_alerts: add FKs to new tables + acknowledged_at ──
    op.add_column(
        "sepsis_alerts",
        sa.Column("admission_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "sepsis_alerts",
        sa.Column("model_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("sepsis_alerts", sa.Column("acknowledged_at", sa.DateTime(), nullable=True))
    op.create_foreign_key(
        "fk_sepsis_alerts_admission_id",
        "sepsis_alerts", "icu_admissions",
        ["admission_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_sepsis_alerts_model_version_id",
        "sepsis_alerts", "ml_model_versions",
        ["model_version_id"], ["id"],
    )
    # Change clinical_summary from VARCHAR to TEXT (no data loss — just removes length limit)
    op.alter_column("sepsis_alerts", "clinical_summary", type_=sa.Text())


def downgrade() -> None:
    # Reverse alert column additions
    op.drop_constraint("fk_sepsis_alerts_model_version_id", "sepsis_alerts", type_="foreignkey")
    op.drop_constraint("fk_sepsis_alerts_admission_id", "sepsis_alerts", type_="foreignkey")
    op.drop_column("sepsis_alerts", "acknowledged_at")
    op.drop_column("sepsis_alerts", "model_version_id")
    op.drop_column("sepsis_alerts", "admission_id")
    op.alter_column("sepsis_alerts", "clinical_summary", type_=sa.String())

    # Reverse vital_readings additions
    op.drop_column("vital_readings", "gcs_total")
    op.drop_column("vital_readings", "mean_arterial_bp")

    # Drop new tables in reverse FK dependency order
    op.drop_table("alert_notifications")
    op.drop_index("ix_comorbidities_patient_id", table_name="comorbidities")
    op.drop_table("comorbidities")
    op.drop_index("ix_lab_results_mimic_hadm_id", table_name="lab_results")
    op.drop_index("ix_lab_results_patient_id", table_name="lab_results")
    op.drop_table("lab_results")
    op.drop_index("ix_icu_admissions_mimic_hadm_id", table_name="icu_admissions")
    op.drop_index("ix_icu_admissions_patient_id", table_name="icu_admissions")
    op.drop_table("icu_admissions")
    op.drop_table("doctors")
    op.drop_table("ml_model_versions")


if __name__ == "__main__":
    upgrade()
