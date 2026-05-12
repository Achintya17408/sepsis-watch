import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchDoctors, createDoctor, updateDoctor } from '../api';
import { Modal } from '../components/Modal';
import { Spinner } from '../components/Spinner';
import type { Doctor } from '../types';

const ROLES = ['DOCTOR', 'INTENSIVIST', 'RESIDENT', 'FELLOW', 'NURSE', 'ADMIN'];
const WARDS = ['All', 'MICU', 'SICU', 'CCU', 'CSRU', 'General'];

type DoctorForm = {
  name: string;
  role: string;
  ward_assignment: string;
  phone_whatsapp: string;
  specialization: string;
  is_on_call: boolean;
};

const EMPTY_FORM: DoctorForm = {
  name: '',
  role: 'DOCTOR',
  ward_assignment: 'All',
  phone_whatsapp: '',
  specialization: '',
  is_on_call: false,
};

function DoctorFormModal({
  initial,
  doctorId,
  onClose,
}: {
  initial?: Partial<DoctorForm>;
  doctorId?: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [form, setForm] = useState<DoctorForm>({ ...EMPTY_FORM, ...initial });
  const [error, setError] = useState('');

  const set = (field: keyof DoctorForm, value: string | boolean) =>
    setForm((f) => ({ ...f, [field]: value }));

  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        name: form.name.trim(),
        role: form.role,
        ward_assignment: form.ward_assignment || undefined,
        specialization: form.specialization.trim() || undefined,
        is_on_call: form.is_on_call,
      };
      if (form.phone_whatsapp.trim()) body.phone_whatsapp = form.phone_whatsapp.trim();
      return doctorId ? updateDoctor(doctorId, body) : createDoctor(body);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['doctors'] }); onClose(); },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Save failed — check phone format (+91XXXXXXXXXX)');
    },
  });

  return (
    <Modal title={doctorId ? 'Edit Doctor' : 'Register Doctor'} onClose={onClose}>
      <div className="space-y-4">
        <div>
          <label className="label">Full Name *</label>
          <input className="input" value={form.name}
            onChange={(e) => set('name', e.target.value)} placeholder="Dr. Priya Sharma" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Role *</label>
            <select className="input" value={form.role} onChange={(e) => set('role', e.target.value)}>
              {ROLES.map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Ward Assignment</label>
            <select className="input" value={form.ward_assignment} onChange={(e) => set('ward_assignment', e.target.value)}>
              {WARDS.map((w) => <option key={w}>{w}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label className="label">WhatsApp Number</label>
          <input className="input" type="tel" value={form.phone_whatsapp}
            onChange={(e) => set('phone_whatsapp', e.target.value)} placeholder="+919876543210" />
          <p className="mt-1 text-xs text-slate-400">E.164 format — country code + digits, no spaces</p>
        </div>
        <div>
          <label className="label">Specialization</label>
          <input className="input" value={form.specialization}
            onChange={(e) => set('specialization', e.target.value)} placeholder="Pulmonology, Critical Care…" />
        </div>
        <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 px-3 py-2.5">
          <input type="checkbox" className="h-4 w-4 rounded border-slate-300 accent-blue-600"
            checked={form.is_on_call} onChange={(e) => set('is_on_call', e.target.checked)} />
          <div>
            <p className="text-sm font-medium text-slate-800">Set on-call immediately</p>
            <p className="text-xs text-slate-400">Doctor will receive WhatsApp alerts for their ward right away</p>
          </div>
        </label>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">{error}</p>}
        <button className="btn-primary w-full" disabled={!form.name.trim() || save.isPending}
          onClick={() => save.mutate()}>
          {save.isPending ? 'Saving…' : doctorId ? 'Save Changes' : 'Register Doctor'}
        </button>
      </div>
    </Modal>
  );
}

function DoctorCard({ doctor }: { doctor: Doctor }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);

  const toggle = useMutation({
    mutationFn: () => updateDoctor(doctor.id, { is_on_call: !doctor.is_on_call }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['doctors'] }),
  });

  return (
    <>
      <div className="card flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-700">
          {(doctor.name ?? '?')[0].toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <p className="truncate font-medium text-slate-900">{doctor.name}</p>
            <button onClick={() => setEditing(true)} className="shrink-0 text-slate-300 hover:text-blue-500" title="Edit">✎</button>
          </div>
          <p className="truncate text-xs text-slate-500">
            {doctor.role}{doctor.ward_assignment ? ` · Ward ${doctor.ward_assignment}` : ''}
          </p>
          {doctor.phone_whatsapp ? (
            <p className="text-xs font-medium text-green-600">📱 {doctor.phone_whatsapp}</p>
          ) : (
            <button onClick={() => setEditing(true)} className="text-xs text-orange-500 underline underline-offset-2">
              + Set WhatsApp number to receive alerts
            </button>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <button
            onClick={() => toggle.mutate()}
            disabled={toggle.isPending}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
              doctor.is_on_call ? 'bg-blue-600' : 'bg-slate-300'
            }`}
            aria-label="Toggle on call"
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
              doctor.is_on_call ? 'translate-x-6' : 'translate-x-1'
            }`} />
          </button>
          <span className="text-xs text-slate-400">{doctor.is_on_call ? 'On call' : 'Off duty'}</span>
        </div>
      </div>
      {editing && (
        <DoctorFormModal
          doctorId={doctor.id}
          initial={{
            name: doctor.name,
            role: doctor.role,
            ward_assignment: doctor.ward_assignment ?? 'All',
            phone_whatsapp: doctor.phone_whatsapp ?? '',
            specialization: '',
            is_on_call: doctor.is_on_call,
          }}
          onClose={() => setEditing(false)}
        />
      )}
    </>
  );
}

export function DoctorsPage() {
  const [adding, setAdding] = useState(false);
  const { data: doctors, isLoading } = useQuery({
    queryKey: ['doctors'],
    queryFn: fetchDoctors,
  });

  const onCall  = (doctors ?? [] as Doctor[]).filter((d: Doctor) => d.is_on_call);
  const offDuty = (doctors ?? [] as Doctor[]).filter((d: Doctor) => !d.is_on_call);

  return (
    <div className="space-y-5 pb-24 pt-20">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-900">Doctors</h1>
        <button
          onClick={() => setAdding(true)}
          className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 text-lg font-light text-white shadow hover:bg-blue-700"
          title="Register new doctor"
        >
          +
        </button>
      </div>

      {isLoading && <div className="flex justify-center py-8"><Spinner /></div>}

      {onCall.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">On Call ({onCall.length})</h2>
          <div className="space-y-2">{onCall.map((d: Doctor) => <DoctorCard key={d.id} doctor={d} />)}</div>
        </section>
      )}

      {offDuty.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Off Duty ({offDuty.length})</h2>
          <div className="space-y-2">{offDuty.map((d: Doctor) => <DoctorCard key={d.id} doctor={d} />)}</div>
        </section>
      )}

      {!isLoading && !doctors?.length && (
        <div className="rounded-xl bg-slate-50 p-6 text-center">
          <p className="text-sm text-slate-500">No doctors registered yet.</p>
          <button onClick={() => setAdding(true)} className="mt-3 text-sm font-medium text-blue-600">
            Register the first doctor →
          </button>
        </div>
      )}

      {adding && <DoctorFormModal onClose={() => setAdding(false)} />}
    </div>
  );
}
