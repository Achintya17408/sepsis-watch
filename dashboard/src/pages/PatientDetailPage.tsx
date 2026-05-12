import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { fetchPatients, fetchVitals, fetchLabs, fetchAlerts, fetchPatientRisk, addVitals, addLabs } from '../api';
import { Modal } from '../components/Modal';
import { VitalCard } from '../components/VitalCard';
import { RiskGauge } from '../components/RiskGauge';
import { Spinner } from '../components/Spinner';
import type { Patient, VitalReading, LabResult, SepsisAlert } from '../types';

// ── Add Vitals Modal ──────────────────────────────────────────────────────────
function VitalsFormModal({ patientId, onClose }: { patientId: string; onClose: () => void }) {
  const qc = useQueryClient();
  type VForm = { heart_rate: string; respiratory_rate: string; temperature_c: string;
    systolic_bp: string; diastolic_bp: string; mean_arterial_bp: string; spo2: string; gcs_total: string; };
  const [form, setForm] = useState<VForm>({
    heart_rate: '', respiratory_rate: '', temperature_c: '', systolic_bp: '',
    diastolic_bp: '', mean_arterial_bp: '', spo2: '', gcs_total: '',
  });
  const [error, setError] = useState('');
  const set = (f: keyof VForm, v: string) => setForm((p) => ({ ...p, [f]: v }));
  const num = (v: string) => (v.trim() ? parseFloat(v) : undefined);
  const int = (v: string) => (v.trim() ? parseInt(v, 10) : undefined);

  const submit = useMutation({
    mutationFn: () => addVitals({
      patient_id: patientId,
      recorded_at: new Date().toISOString(),
      heart_rate: num(form.heart_rate),
      respiratory_rate: num(form.respiratory_rate),
      temperature_c: num(form.temperature_c),
      systolic_bp: num(form.systolic_bp),
      diastolic_bp: num(form.diastolic_bp),
      mean_arterial_bp: num(form.mean_arterial_bp),
      spo2: num(form.spo2),
      gcs_total: int(form.gcs_total),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vitals', patientId] });
      qc.invalidateQueries({ queryKey: ['risk', patientId] });
      onClose();
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Failed to record vitals');
    },
  });

  const hasAny = Object.values(form).some((v) => v.trim() !== '');

  return (
    <Modal title="Record Vitals" onClose={onClose}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          {([
            ['heart_rate',       'Heart Rate',        'bpm',        '60–100'],
            ['respiratory_rate', 'Resp. Rate',         'breaths/min','12–20'],
            ['temperature_c',    'Temperature',        '°C',         '36.1–37.2'],
            ['spo2',             'SpO₂',               '%',          '94–100'],
            ['systolic_bp',      'Systolic BP',        'mmHg',       '90–140'],
            ['diastolic_bp',     'Diastolic BP',       'mmHg',       '60–90'],
            ['mean_arterial_bp', 'MAP',                'mmHg',       '70–105'],
            ['gcs_total',        'GCS',                '3–15',       '15 = alert'],
          ] as [keyof VForm, string, string, string][]).map(([field, label, unit, hint]) => (
            <div key={field}>
              <label className="label">{label} <span className="text-slate-300">({unit})</span></label>
              <input className="input" type="number" step="0.1" value={form[field]}
                onChange={(e) => set(field, e.target.value)} placeholder={hint} />
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-400">Leave blank any values not measured. Scoring runs automatically after submission.</p>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">{error}</p>}
        <button className="btn-primary w-full" disabled={!hasAny || submit.isPending} onClick={() => submit.mutate()}>
          {submit.isPending ? 'Saving…' : 'Record Vitals'}
        </button>
      </div>
    </Modal>
  );
}

// ── Add Labs Modal ────────────────────────────────────────────────────────────
function LabsFormModal({ patientId, onClose }: { patientId: string; onClose: () => void }) {
  const qc = useQueryClient();
  type LForm = { wbc: string; hemoglobin: string; platelets: string; creatinine: string; bun: string;
    sodium: string; potassium: string; glucose: string; lactate: string;
    procalcitonin: string; crp: string; inr: string; bilirubin_total: string; };
  const [form, setForm] = useState<LForm>({
    wbc: '', hemoglobin: '', platelets: '', creatinine: '', bun: '',
    sodium: '', potassium: '', glucose: '', lactate: '', procalcitonin: '', crp: '', inr: '', bilirubin_total: '',
  });
  const [error, setError] = useState('');
  const set = (f: keyof LForm, v: string) => setForm((p) => ({ ...p, [f]: v }));
  const num = (v: string) => (v.trim() ? parseFloat(v) : undefined);

  const submit = useMutation({
    mutationFn: () => addLabs({
      patient_id: patientId,
      collected_at: new Date().toISOString(),
      wbc: num(form.wbc), hemoglobin: num(form.hemoglobin), platelets: num(form.platelets),
      creatinine: num(form.creatinine), bun: num(form.bun),
      sodium: num(form.sodium), potassium: num(form.potassium), glucose: num(form.glucose),
      lactate: num(form.lactate), procalcitonin: num(form.procalcitonin), crp: num(form.crp),
      inr: num(form.inr), bilirubin_total: num(form.bilirubin_total),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['labs', patientId] });
      qc.invalidateQueries({ queryKey: ['risk', patientId] });
      onClose();
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Failed to record labs');
    },
  });

  const hasAny = Object.values(form).some((v) => v.trim() !== '');

  const labFields: [keyof LForm, string, string][] = [
    ['wbc',           'WBC',           '×10³/μL'],
    ['hemoglobin',    'Hemoglobin',    'g/dL'],
    ['platelets',     'Platelets',     '×10³/μL'],
    ['creatinine',    'Creatinine',    'mg/dL'],
    ['bun',           'BUN',           'mg/dL'],
    ['sodium',        'Sodium',        'mEq/L'],
    ['potassium',     'Potassium',     'mEq/L'],
    ['glucose',       'Glucose',       'mg/dL'],
    ['lactate',       'Lactate',       'mmol/L'],
    ['procalcitonin', 'Procalcitonin', 'ng/mL'],
    ['crp',           'CRP',           'mg/L'],
    ['inr',           'INR',           ''],
    ['bilirubin_total','Bilirubin',    'mg/dL'],
  ];

  return (
    <Modal title="Record Lab Results" onClose={onClose}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          {labFields.map(([field, label, unit]) => (
            <div key={field}>
              <label className="label">{label}{unit ? ` (${unit})` : ''}</label>
              <input className="input" type="number" step="0.01" value={form[field]}
                onChange={(e) => set(field, e.target.value)} />
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-400">Leave blank any values not collected. Sepsis scoring reruns automatically.</p>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">{error}</p>}
        <button className="btn-primary w-full" disabled={!hasAny || submit.isPending} onClick={() => submit.mutate()}>
          {submit.isPending ? 'Saving…' : 'Record Labs'}
        </button>
      </div>
    </Modal>
  );
}

const LAB_FIELDS: Array<{ key: keyof LabResult; label: string; unit: string }> = [
  { key: 'lactate', label: 'Lactate', unit: 'mmol/L' },
  { key: 'procalcitonin', label: 'Procalcitonin', unit: 'ng/mL' },
  { key: 'crp', label: 'CRP', unit: 'mg/L' },
  { key: 'wbc', label: 'WBC', unit: '×10³/μL' },
  { key: 'hemoglobin', label: 'Hgb', unit: 'g/dL' },
  { key: 'platelets', label: 'Platelets', unit: '×10³/μL' },
  { key: 'creatinine', label: 'Creatinine', unit: 'mg/dL' },
  { key: 'bilirubin_total', label: 'Bilirubin', unit: 'mg/dL' },
  { key: 'inr', label: 'INR', unit: '' },
  { key: 'ph', label: 'pH', unit: '' },
  { key: 'pao2_fio2_ratio', label: 'P/F Ratio', unit: '' },
];

export function PatientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [showVitals, setShowVitals] = useState(false);
  const [showLabs, setShowLabs] = useState(false);

  const { data: patients } = useQuery<Patient[]>({
    queryKey: ['patients'],
    queryFn: fetchPatients,
  });
  const patient = patients?.find((p) => p.id === id);

  const { data: vitals, isLoading: vLoading } = useQuery<VitalReading[]>({
    queryKey: ['vitals', id],
    queryFn: () => fetchVitals(id!, 100),
    enabled: !!id,
  });

  const { data: labs } = useQuery<LabResult[]>({
    queryKey: ['labs', id],
    queryFn: () => fetchLabs(id!, 20),
    enabled: !!id,
  });

  // Fetch all alerts then filter client-side by patient_id (API has no patient filter)
  const { data: allAlerts } = useQuery<SepsisAlert[]>({
    queryKey: ['alerts', 'all'],
    queryFn: () => fetchAlerts(false),
    enabled: !!id,
  });
  const alerts = allAlerts?.filter((a) => a.patient_id === id);

  const { data: risk } = useQuery({
    queryKey: ['risk', id],
    queryFn: () => fetchPatientRisk(id!),
    enabled: !!id,
    refetchInterval: 60_000,
  });

  const latest = vitals?.[vitals.length - 1];

  // Re-score: hit the risk endpoint (it triggers background scoring) + refetch
  const rescore = useMutation({
    mutationFn: () => fetchPatientRisk(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['risk', id] });
      qc.invalidateQueries({ queryKey: ['alerts', 'all'] });
    },
  });

  const chartData = (vitals ?? []).slice(-60).map((v) => ({
    t: new Date(v.recorded_at + 'Z').toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    hr: v.heart_rate,
    map: v.mean_arterial_bp,
    spo2: v.spo2,
    resp: v.respiratory_rate,
    temp: v.temperature_c,
  }));

  // Flatten lab results into rows: each lab result has multiple test fields
  const labRows: Array<{ label: string; value: number; unit: string; time: string }> = [];
  (labs ?? []).forEach((lab) => {
    LAB_FIELDS.forEach(({ key, label, unit }) => {
      const val = lab[key];
      if (val != null) {
        labRows.push({ label, value: val as number, unit, time: lab.collected_at });
      }
    });
  });

  return (
    <div className="space-y-5 pb-24">
      {/* Back button */}
      <div className="pt-16">
        <button
          onClick={() => nav(-1)}
          className="text-sm text-blue-600 active:text-blue-800"
        >
          ← Back
        </button>
      </div>

      {/* Patient header */}
      <div className="card flex items-center gap-4">
        <RiskGauge score={risk?.latest_risk_score ?? 0} size={72} />
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-lg font-bold text-slate-900">
            {patient?.name ?? id?.slice(0, 8)}
          </h1>
          <p className="text-sm text-slate-500">
            {patient?.age ? `${patient.age}y · ` : ''}
            Ward {patient?.ward ?? '—'}
          </p>
          {risk?.sofa_score != null && (
            <p className="mt-1 text-xs text-slate-500">SOFA {risk.sofa_score}/24</p>
          )}
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex gap-2">
        <button
          className="btn-primary flex-1 py-2 text-xs"
          onClick={() => setShowVitals(true)}
        >
          + Vitals
        </button>
        <button
          className="btn-primary flex-1 py-2 text-xs"
          onClick={() => setShowLabs(true)}
        >
          + Labs
        </button>
        <button
          className="btn-ghost flex-1 py-2 text-xs disabled:opacity-50"
          disabled={rescore.isPending}
          onClick={() => rescore.mutate()}
          title="Re-run sepsis risk scoring for this patient"
        >
          {rescore.isPending ? 'Scoring…' : '↻ Re-score'}
        </button>
      </div>

      {showVitals && id && <VitalsFormModal patientId={id} onClose={() => setShowVitals(false)} />}
      {showLabs   && id && <LabsFormModal   patientId={id} onClose={() => setShowLabs(false)} />}

      {/* Current vitals */}
      {vLoading && <div className="flex justify-center py-4"><Spinner /></div>}
      {latest && (
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Latest Vitals
          </h2>
          <div className="grid grid-cols-3 gap-2">
            <VitalCard label="HR" value={latest.heart_rate ?? '—'} unit="bpm"
              status={(latest.heart_rate ?? 80) > 100 || (latest.heart_rate ?? 80) < 60 ? 'warning' : 'normal'} />
            <VitalCard label="MAP" value={latest.mean_arterial_bp ?? '—'} unit="mmHg"
              status={(latest.mean_arterial_bp ?? 80) < 65 ? 'critical' : 'normal'} />
            <VitalCard label="SpO₂" value={latest.spo2 ?? '—'} unit="%"
              status={(latest.spo2 ?? 98) < 94 ? 'critical' : 'normal'} />
            <VitalCard label="RR" value={latest.respiratory_rate ?? '—'} unit="/min"
              status={(latest.respiratory_rate ?? 16) > 22 ? 'warning' : 'normal'} />
            <VitalCard
              label="Temp"
              value={latest.temperature_c != null ? latest.temperature_c.toFixed(1) : '—'}
              unit="°C"
              status={
                latest.temperature_c != null && (latest.temperature_c > 38.3 || latest.temperature_c < 36)
                  ? 'warning'
                  : 'normal'
              }
            />
            <VitalCard label="GCS" value={latest.gcs_total ?? '—'}
              status={(latest.gcs_total ?? 15) < 13 ? 'critical' : 'normal'} />
          </div>
        </section>
      )}

      {/* Vitals trend */}
      {chartData.length > 1 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Vitals Trend
          </h2>
          <div className="card p-2">
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="t" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ fontSize: 11 }} />
                <Line type="monotone" dataKey="hr" stroke="#ef4444" dot={false} name="HR" />
                <Line type="monotone" dataKey="spo2" stroke="#3b82f6" dot={false} name="SpO₂" />
                <Line type="monotone" dataKey="map" stroke="#8b5cf6" dot={false} name="MAP" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {/* Recent labs */}
      {labRows.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Recent Labs
          </h2>
          <div className="card overflow-hidden p-0">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-2 text-left">Test</th>
                  <th className="px-4 py-2 text-right">Value</th>
                  <th className="px-4 py-2 text-right">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {labRows.slice(0, 24).map((row, i) => (
                  <tr key={i}>
                    <td className="px-4 py-2 font-medium text-slate-800">{row.label}</td>
                    <td className="px-4 py-2 text-right text-slate-600">
                      {typeof row.value === 'number' ? row.value.toFixed(2) : row.value}
                      {row.unit ? ` ${row.unit}` : ''}
                    </td>
                    <td className="px-4 py-2 text-right text-xs text-slate-400">
                      {new Date(row.time + 'Z').toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Alert history */}
      {alerts && alerts.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Alert History
          </h2>
          <div className="space-y-2">
            {alerts.slice(0, 10).map((a) => (
              <div key={a.id} className="card py-2">
                <div className="flex justify-between text-sm">
                  <span className={`font-medium ${a.alert_level === 'CRITICAL' ? 'text-red-600' : 'text-orange-600'}`}>
                    {a.alert_level}
                  </span>
                  <span className="text-slate-400 text-xs">
                    {new Date(a.triggered_at + 'Z').toLocaleString()}
                  </span>
                </div>
                {a.clinical_summary && (
                  <p className="mt-1 text-xs text-slate-500 line-clamp-2">{a.clinical_summary}</p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
