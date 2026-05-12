interface Props {
  label: string;
  value: string | number;
  unit?: string;
  status?: 'normal' | 'warning' | 'critical';
}

const STATUS_RING: Record<string, string> = {
  normal: 'ring-green-200',
  warning: 'ring-yellow-300',
  critical: 'ring-red-400',
};

const STATUS_VALUE: Record<string, string> = {
  normal: 'text-green-700',
  warning: 'text-yellow-700',
  critical: 'text-red-600',
};

export function VitalCard({ label, value, unit, status = 'normal' }: Props) {
  return (
    <div className={`card ring-2 ${STATUS_RING[status]} py-3 text-center`}>
      <p className="mb-1 text-xs text-slate-500">{label}</p>
      <p className={`text-xl font-bold tabular-nums ${STATUS_VALUE[status]}`}>
        {value}
        {unit && <span className="ml-0.5 text-sm font-normal">{unit}</span>}
      </p>
    </div>
  );
}
