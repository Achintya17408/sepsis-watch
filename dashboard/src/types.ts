// PatientResponse  (GET /patients/)
export interface Patient {
  id: string;
  name: string;
  age?: number;
  ward?: string;
  hospital_id?: string;
  mimic_subject_id?: number;
  created_at?: string;
}

// PatientRiskResponse  (GET /patients/{id}/risk)
export interface PatientRisk {
  patient_id: string;
  patient_name: string;
  ward?: string;
  latest_risk_score?: number;
  latest_alert_level?: string;
  sofa_score?: number;
  qsofa_score?: number;
  last_assessed_at?: string;
  confidence?: number;
}

// AlertResponse  (GET /alerts/)
export interface SepsisAlert {
  id: string;
  patient_id: string;
  patient_name?: string;   // may be joined server-side
  risk_score: number;
  alert_level: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  sofa_score?: number;
  clinical_summary?: string;
  acknowledged: boolean;
  acknowledged_by?: string;
  acknowledged_at?: string;
  triggered_at: string;
}

// VitalResponse  (GET /vitals/)
export interface VitalReading {
  id: string;
  patient_id: string;
  recorded_at: string;
  heart_rate?: number;
  systolic_bp?: number;
  diastolic_bp?: number;
  mean_arterial_bp?: number;
  spo2?: number;
  respiratory_rate?: number;
  temperature_c?: number;
  gcs_total?: number;
  urine_output?: number;
}

// LabResponse  (GET /labs/)
export interface LabResult {
  id: string;
  patient_id: string;
  collected_at: string;
  // CBC
  wbc?: number;
  hemoglobin?: number;
  hematocrit?: number;
  platelets?: number;
  // BMP
  sodium?: number;
  potassium?: number;
  creatinine?: number;
  glucose?: number;
  bun?: number;
  // LFTs
  bilirubin_total?: number;
  ast?: number;
  alt?: number;
  albumin?: number;
  // Coagulation
  inr?: number;
  prothrombin_time?: number;
  // ABG
  ph?: number;
  pao2_fio2_ratio?: number;
  // Sepsis markers
  lactate?: number;
  procalcitonin?: number;
  crp?: number;
}

// DoctorResponse  (GET /doctors/)
export interface Doctor {
  id: string;
  name: string;
  role: string;
  employee_id?: string;
  phone_whatsapp?: string;
  ward_assignment?: string;
  is_on_call: boolean;
  is_active: boolean;
  on_call_start?: string;
  on_call_end?: string;
}
