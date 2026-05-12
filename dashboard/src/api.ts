import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export const http = axios.create({ baseURL: API_BASE });

// Inject JWT token on every request
http.interceptors.request.use((config) => {
  const token = localStorage.getItem('sw_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Auto-logout on 401
http.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('sw_token');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

// ── Auth ─────────────────────────────────────────────────────────────────────
export async function login(username: string, password: string): Promise<string> {
  const form = new URLSearchParams({ username, password });
  const { data } = await http.post('/auth/token', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  localStorage.setItem('sw_token', data.access_token);
  return data.access_token;
}

export function logout() {
  localStorage.removeItem('sw_token');
  window.location.href = '/login';
}

export function isLoggedIn() {
  return !!localStorage.getItem('sw_token');
}

// ── Patients ─────────────────────────────────────────────────────────────────
export const fetchPatients = (params?: Record<string, unknown>) =>
  http.get('/patients/', { params }).then((r) => r.data);

export const fetchPatientRisk = (id: string) =>
  http.get(`/patients/${id}/risk`).then((r) => r.data);

// ── Alerts ───────────────────────────────────────────────────────────────────
// Returns SepsisAlert[] directly (extracted from { total, alerts } wrapper)
export const fetchAlerts = (unacknowledgedOnly = true): Promise<import('./types').SepsisAlert[]> =>
  http
    .get('/alerts/', { params: { unacknowledged_only: unacknowledgedOnly, limit: 100 } })
    .then((r) => r.data.alerts ?? r.data);

export const acknowledgeAlert = (id: string, acknowledged_by = 'dashboard') =>
  http.patch(`/alerts/${id}/acknowledge`, { acknowledged_by }).then((r) => r.data);

// ── Vitals ───────────────────────────────────────────────────────────────────
export const fetchVitals = (patientId: string, limit = 24) =>
  http.get(`/vitals/${patientId}`, { params: { limit } }).then((r) => r.data);

export const addVitals = (body: Record<string, unknown>) =>
  http.post('/vitals/', body).then((r) => r.data);

// ── Labs ─────────────────────────────────────────────────────────────────────
export const fetchLabs = (patientId: string, limit = 10) =>
  http.get(`/labs/${patientId}`, { params: { limit } }).then((r) => r.data);

export const addLabs = (body: Record<string, unknown>) =>
  http.post('/labs/', body).then((r) => r.data);

// ── Doctors ──────────────────────────────────────────────────────────────────
export const fetchDoctors = (params?: Record<string, unknown>) =>
  http.get('/doctors/', { params }).then((r) => r.data);

export const createDoctor = (body: Record<string, unknown>) =>
  http.post('/doctors/', body).then((r) => r.data);

export const updateDoctor = (id: string, body: Record<string, unknown>) =>
  http.patch(`/doctors/${id}`, body).then((r) => r.data);

// ── Patients (write) ────────────────────────────────────────────────────────
export const createPatient = (body: Record<string, unknown>) =>
  http.post('/patients/', body).then((r) => r.data);

/** Fire-and-forget bulk: resolves to { admitted, errors } */
export async function bulkAdmitPatients(
  rows: Record<string, unknown>[]
): Promise<{ admitted: number; errors: { row: number; name: unknown; error: string }[] }> {
  let admitted = 0;
  const errors: { row: number; name: unknown; error: string }[] = [];
  for (let i = 0; i < rows.length; i++) {
    try {
      await createPatient(rows[i]);
      admitted++;
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      errors.push({ row: i + 1, name: rows[i].name, error: detail ?? 'unknown error' });
    }
  }
  return { admitted, errors };
}
