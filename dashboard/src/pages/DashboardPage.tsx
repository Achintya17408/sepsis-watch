import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { fetchAlerts, acknowledgeAlert, fetchPatients } from '../api';
import { AlertCard } from '../components/AlertCard';
import { SkeletonCard } from '../components/SkeletonCard';
import type { SepsisAlert } from '../types';

export function DashboardPage() {
  const qc = useQueryClient();

  const { data: alerts, isLoading: alertsLoading, dataUpdatedAt } = useQuery({
    queryKey: ['alerts', 'unacked'],
    queryFn: () => fetchAlerts(true),
    refetchInterval: 30_000,
  });

  const { data: allAlerts } = useQuery({
    queryKey: ['alerts', 'all'],
    queryFn: () => fetchAlerts(false),
    refetchInterval: 60_000,
  });

  const { data: patients } = useQuery({
    queryKey: ['patients'],
    queryFn: fetchPatients,
    refetchInterval: 120_000,
  });

  const ack = useMutation({
    mutationFn: (id: string) => acknowledgeAlert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });

  const unacked: SepsisAlert[] = (alerts ?? []).filter((a: SepsisAlert) => !a.acknowledged);

  const recentByPatient = new Map<string, SepsisAlert>();
  (allAlerts ?? []).forEach((a: SepsisAlert) => {
    const existing = recentByPatient.get(a.patient_id);
    if (!existing || a.triggered_at > existing.triggered_at) {
      recentByPatient.set(a.patient_id, a);
    }
  });
  const highRisk = Array.from(recentByPatient.values())
    .filter((a) => a.risk_score >= 0.4)
    .sort((a, b) => b.risk_score - a.risk_score)
    .slice(0, 8);

  const criticalCount = (allAlerts ?? []).filter(
    (a: SepsisAlert) => a.alert_level === 'CRITICAL' && !a.acknowledged,
  ).length;

  const updatedTime = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : null;

  return (
    <div className="space-y-5 pb-24 pt-20">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <h1 className="font-bold text-slate-900">Overview</h1>
        <div className="flex items-center gap-2">
          {updatedTime && <span className="text-xs text-slate-400">Updated {updatedTime}</span>}
          <span className="inline-flex h-2 w-2 rounded-full bg-green-400 animate-pulse" title="Live" />
        </div>
      </div>

      {/* Stats row: 3 columns */}
      <div className="grid grid-cols-3 gap-2">
        <div className="card text-center py-3">
          <p className="text-2xl font-bold text-red-600">{criticalCount}</p>
          <p className="mt-0.5 text-xs text-slate-500">Critical</p>
        </div>
        <div className="card text-center py-3">
          <p className="text-2xl font-bold text-orange-500">{unacked.length}</p>
          <p className="mt-0.5 text-xs text-slate-500">Unacked</p>
        </div>
        <div className="card text-center py-3">
          <p className="text-2xl font-bold text-slate-700">{patients?.length ?? '—'}</p>
          <p className="mt-0.5 text-xs text-slate-500">Patients</p>
        </div>
      </div>

      {/* Active alerts */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold text-slate-900">Active Alerts</h2>
          <Link to="/alerts" className="text-sm text-blue-600">See all →</Link>
        </div>
        {alertsLoading && (
          <div className="space-y-3">
            {[1,2,3].map(i => <SkeletonCard key={i} lines={3} />)}
          </div>
        )}
        {!alertsLoading && unacked.length === 0 && (
          <p className="rounded-xl bg-green-50 p-4 text-center text-sm text-green-700">
            No active alerts 🎉
          </p>
        )}
        <div className="space-y-3">
          {unacked.slice(0, 5).map((alert) => (
            <AlertCard key={alert.id} alert={alert} onAcknowledge={(id) => ack.mutate(id)} />
          ))}
        </div>
      </section>

      {/* High-risk patients */}
      {highRisk.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold text-slate-900">High-Risk Patients</h2>
          <div className="space-y-2">
            {highRisk.map((a) => {
              const risk = a.risk_score;
              const color =
                risk >= 0.7 ? 'text-red-600' : risk >= 0.4 ? 'text-orange-600' : 'text-yellow-600';
              return (
                <Link
                  key={a.patient_id}
                  to={`/patients/${a.patient_id}`}
                  className="card flex items-center justify-between gap-4 active:bg-slate-50"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-slate-900">
                      {a.patient_name ?? a.patient_id.slice(0, 8)}
                    </p>
                    <p className="text-xs text-slate-500">{a.alert_level}</p>
                  </div>
                  <span className={`shrink-0 text-lg font-bold tabular-nums ${color}`}>
                    {Math.round(risk * 100)}%
                  </span>
                </Link>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
