import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { fetchPatients, fetchAlerts, createPatient } from '../api';
import { Modal } from '../components/Modal';
import { BulkUploadModal } from '../components/BulkUploadModal';
import { Spinner } from '../components/Spinner';
import type { Patient, SepsisAlert } from '../types';

const WARDS_P = ['MICU', 'SICU', 'CCU', 'CSRU', 'General'];

type PatientForm = { name: string; age: string; ward: string; hospital_id: string };
const EMPTY_P: PatientForm = { name: '', age: '', ward: 'MICU', hospital_id: '' };

function AdmitPatientModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<PatientForm>(EMPTY_P);
  const [error, setError] = useState('');
  const set = (f: keyof PatientForm, v: string) => setForm((p) => ({ ...p, [f]: v }));

  const admit = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { name: form.name.trim(), ward: form.ward };
      if (form.age.trim()) body.age = parseInt(form.age, 10);
      if (form.hospital_id.trim()) body.hospital_id = form.hospital_id.trim();
      return createPatient(body);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['patients'] }); onClose(); },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Failed to admit patient');
    },
  });

  return (
    <Modal title="Admit Patient" onClose={onClose}>
      <div className="space-y-4">
        <div>
          <label className="label">Full Name *</label>
          <input className="input" value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="John Doe" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Age</label>
            <input className="input" type="number" min={0} max={130} value={form.age}
              onChange={(e) => set('age', e.target.value)} placeholder="58" />
          </div>
          <div>
            <label className="label">Ward *</label>
            <select className="input" value={form.ward} onChange={(e) => set('ward', e.target.value)}>
              {WARDS_P.map((w) => <option key={w}>{w}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label className="label">Hospital / MRN ID</label>
          <input className="input" value={form.hospital_id} onChange={(e) => set('hospital_id', e.target.value)} placeholder="MRN-1042" />
        </div>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">{error}</p>}
        <p className="text-xs text-slate-400">
          After admitting, open the patient's record to add vitals and lab results.
        </p>
        <button className="btn-primary w-full" disabled={!form.name.trim() || admit.isPending}
          onClick={() => admit.mutate()}>
          {admit.isPending ? 'Admitting…' : 'Admit Patient'}
        </button>
      </div>
    </Modal>
  );
}

const RISK_RING: Record<string, string> = {
  high: 'ring-red-400 bg-red-50',
  medium: 'ring-orange-300 bg-orange-50',
  low: 'ring-green-200 bg-green-50',
  none: 'ring-slate-200 bg-white',
};

const RISK_TEXT: Record<string, string> = {
  high: 'text-red-600',
  medium: 'text-orange-600',
  low: 'text-green-600',
  none: 'text-slate-400',
};

function riskBucket(score?: number) {
  if (score == null) return 'none';
  if (score >= 0.7) return 'high';
  if (score >= 0.4) return 'medium';
  return 'low';
}

export function PatientsPage() {
  const [search, setSearch] = useState('');
  const [admitting, setAdmitting] = useState(false);
  const [bulkUploading, setBulkUploading] = useState(false);

  const { data: patients, isLoading: pLoading } = useQuery<Patient[]>({
    queryKey: ['patients'],
    queryFn: fetchPatients,
    refetchInterval: 60_000,
  });

  const { data: allAlerts } = useQuery<SepsisAlert[]>({
    queryKey: ['alerts', 'all'],
    queryFn: () => fetchAlerts(false),
    refetchInterval: 60_000,
  });

  const riskByPatient = new Map<string, number>();
  (allAlerts ?? []).forEach((a) => {
    const existing = riskByPatient.get(a.patient_id);
    if (existing == null || a.risk_score > existing) {
      riskByPatient.set(a.patient_id, a.risk_score);
    }
  });

  const filtered = (patients ?? []).filter((p) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      p.name?.toLowerCase().includes(q) ||
      p.ward?.toLowerCase().includes(q) ||
      p.hospital_id?.toLowerCase().includes(q)
    );
  });

  const sorted = [...filtered].sort((a, b) => {
    const ra = riskByPatient.get(a.id) ?? 0;
    const rb = riskByPatient.get(b.id) ?? 0;
    return rb - ra || (a.name ?? '').localeCompare(b.name ?? '');
  });

  const criticalCount = filtered.filter((p) => (riskByPatient.get(p.id) ?? 0) >= 0.7).length;

  return (
    <div className="space-y-4 pb-24 pt-20">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-slate-900">Patients</h1>
          {!pLoading && (
            <p className="text-xs text-slate-500">
              {patients?.length ?? 0} total · {criticalCount} critical
            </p>
          )}
        </div>
        <button
          onClick={() => setAdmitting(true)}
          className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 text-lg font-light text-white shadow hover:bg-blue-700"
          title="Admit new patient"
        >
          +
        </button>
        <button
          onClick={() => setBulkUploading(true)}
          className="flex h-8 items-center gap-1.5 rounded-full bg-slate-700 px-3 text-xs font-medium text-white shadow hover:bg-slate-800"
          title="Bulk import from CSV"
        >
          📂 CSV
        </button>
      </div>
      {admitting && <AdmitPatientModal onClose={() => setAdmitting(false)} />}
      {bulkUploading && <BulkUploadModal onClose={() => setBulkUploading(false)} />}

      <div className="relative">
        <span className="absolute inset-y-0 left-3 flex items-center text-slate-400 pointer-events-none">🔍</span>
        <input
          type="search"
          placeholder="Search by name, ward, ID…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-xl border border-slate-200 py-2.5 pl-9 pr-4 text-sm shadow-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
      </div>

      {pLoading && <div className="flex justify-center py-8"><Spinner /></div>}

      {!pLoading && sorted.length === 0 && (
        <p className="rounded-xl bg-slate-50 p-6 text-center text-sm text-slate-400">
          {search ? 'No patients match your search.' : 'No patients loaded yet.'}
        </p>
      )}

      <div className="space-y-2">
        {sorted.map((p) => {
          const risk = riskByPatient.get(p.id);
          const bucket = riskBucket(risk);
          return (
            <Link
              key={p.id}
              to={`/patients/${p.id}`}
              className={`card flex items-center gap-3 ring-2 transition-all active:scale-[0.99] ${RISK_RING[bucket]}`}
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-slate-200 text-sm font-bold text-slate-600">
                {(p.name ?? '?')[0].toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold text-slate-900">{p.name ?? 'Unknown'}</p>
                <p className="text-xs text-slate-500">
                  {p.age ? `${p.age}y · ` : ''}Ward {p.ward ?? '—'}
                  {p.hospital_id ? ` · ${p.hospital_id}` : ''}
                </p>
              </div>
              <div className="shrink-0 text-right">
                {risk != null ? (
                  <>
                    <p className={`text-lg font-bold tabular-nums ${RISK_TEXT[bucket]}`}>
                      {Math.round(risk * 100)}%
                    </p>
                    <p className="text-xs text-slate-400">risk</p>
                  </>
                ) : (
                  <p className="text-xs text-slate-400">No data</p>
                )}
              </div>
              <span className="shrink-0 text-slate-300">›</span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
