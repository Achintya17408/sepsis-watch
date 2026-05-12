import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchAlerts, acknowledgeAlert } from '../api';
import { AlertCard } from '../components/AlertCard';
import { Spinner } from '../components/Spinner';
import type { SepsisAlert } from '../types';

export function AlertsPage() {
  const [showAll, setShowAll] = useState(false);
  const qc = useQueryClient();

  // unacknowledged_only=true when NOT showing all, false when showing all
  const { data: alerts, isLoading } = useQuery({
    queryKey: ['alerts', showAll ? 'all' : 'unacked'],
    queryFn: () => fetchAlerts(!showAll),
    refetchInterval: 20_000,
  });

  const ack = useMutation({
    mutationFn: (id: string) => acknowledgeAlert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });

  return (
    <div className="space-y-4 pb-24 pt-20">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-900">Alerts</h1>
        <button
          onClick={() => setShowAll((v) => !v)}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 active:bg-slate-100"
        >
          {showAll ? 'Show active' : 'Show all'}
        </button>
      </div>

      {isLoading && <div className="flex justify-center py-8"><Spinner /></div>}

      {!isLoading && (!alerts || alerts.length === 0) && (
        <p className="rounded-xl bg-green-50 p-6 text-center text-sm text-green-700">
          {showAll ? 'No alerts found.' : 'No active alerts 🎉'}
        </p>
      )}

      <div className="space-y-3">
        {(alerts ?? [] as SepsisAlert[]).map((a: SepsisAlert) => (
          <AlertCard key={a.id} alert={a} onAcknowledge={(id) => ack.mutate(id)} />
        ))}
      </div>
    </div>
  );
}
