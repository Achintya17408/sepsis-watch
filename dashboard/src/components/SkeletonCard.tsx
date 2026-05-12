export function SkeletonCard({ lines = 2, className = '' }: { lines?: number; className?: string }) {
  return (
    <div className={`card space-y-3 ${className}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="h-4 w-32 animate-pulse rounded-full bg-slate-200" />
        <div className="h-5 w-16 animate-pulse rounded-full bg-slate-200" />
      </div>
      {Array.from({ length: lines - 1 }).map((_, i) => (
        <div
          key={i}
          className="h-3 animate-pulse rounded-full bg-slate-100"
          style={{ width: `${70 - i * 15}%` }}
        />
      ))}
    </div>
  );
}
