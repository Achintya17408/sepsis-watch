interface Props {
  score: number; // 0–1
  size?: number;
}

export function RiskGauge({ score, size = 80 }: Props) {
  const pct = Math.max(0, Math.min(1, score));
  const radius = 32;
  const circ = 2 * Math.PI * radius;

  const color =
    pct >= 0.7
      ? '#ef4444' // red-500
      : pct >= 0.4
      ? '#f97316' // orange-500
      : pct >= 0.2
      ? '#eab308' // yellow-500
      : '#22c55e'; // green-500

  return (
    <svg width={size} height={size} viewBox="0 0 80 80" className="shrink-0 -rotate-[135deg]">
      <circle
        cx="40"
        cy="40"
        r={radius}
        fill="none"
        stroke="#e2e8f0"
        strokeWidth="8"
        strokeDasharray={`${circ * 0.75} ${circ * 0.25}`}
        strokeLinecap="round"
      />
      <circle
        cx="40"
        cy="40"
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth="8"
        strokeDasharray={`${circ * pct * 0.75} ${circ * (1 - pct * 0.75)}`}
        strokeLinecap="round"
        style={{ transition: 'stroke-dasharray 0.5s ease' }}
      />
      <text
        x="40"
        y="44"
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize="14"
        fontWeight="700"
        fill={color}
        style={{ rotate: '135deg', transformOrigin: '40px 40px' }}
      >
        {Math.round(pct * 100)}%
      </text>
    </svg>
  );
}
