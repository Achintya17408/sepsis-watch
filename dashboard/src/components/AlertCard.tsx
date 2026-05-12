import type { SepsisAlert } from '../types';
import { showToast } from './Toast';

const LEVEL_CLASSES: Record<string, string> = {
  CRITICAL: 'badge-critical',
  HIGH: 'badge-high',
  MEDIUM: 'badge-medium',
  LOW: 'badge-low',
};

const LEVEL_DOT: Record<string, string> = {
  CRITICAL: 'bg-red-500',
  HIGH: 'bg-orange-500',
  MEDIUM: 'bg-yellow-500',
  LOW: 'bg-green-500',
};

interface Props {
  alert: SepsisAlert;
  onAcknowledge: (id: string) => void;
}

export function AlertCard({ alert, onAcknowledge }: Props) {
  const relTime = new Date(alert.triggered_at + 'Z').toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <div
      className={`card space-y-3 transition-all ${
        alert.acknowledged ? 'opacity-60' : 'border-l-4 border-l-red-400'
      }`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${LEVEL_DOT[alert.alert_level] ?? 'bg-slate-400'}`} />
          <div className="min-w-0">
            <p className="truncate font-semibold text-slate-900">{alert.patient_name ?? alert.patient_id.slice(0, 8)}</p>
            <p className="text-xs text-slate-500">{alert.triggered_at ? relTime : '—'}</p>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className={LEVEL_CLASSES[alert.alert_level] ?? 'badge-low'}>
            {alert.alert_level}
          </span>
          <span className="text-xs text-slate-500">Risk {Math.round(alert.risk_score * 100)}%</span>
        </div>
      </div>

      {/* Clinical summary */}
      {alert.clinical_summary && (
        <p className="rounded-lg bg-slate-50 p-3 text-sm leading-relaxed text-slate-700">
          {alert.clinical_summary}
        </p>
      )}

      {/* SOFA + acknowledge */}
      <div className="flex items-center justify-between">
        {alert.sofa_score != null && (
          <span className="text-xs text-slate-500">SOFA {alert.sofa_score}/24</span>
        )}
        {!alert.acknowledged && (
          <button
            onClick={() => {
              onAcknowledge(alert.id);
              showToast('Alert acknowledged', 'success');
            }}
            className="ml-auto rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-medium text-white active:bg-slate-700"
          >
            Acknowledge
          </button>
        )}
        {alert.acknowledged && (
          <span className="ml-auto text-xs text-slate-400">
            Acked by {alert.acknowledged_by ?? 'someone'}
          </span>
        )}
      </div>
    </div>
  );
}
