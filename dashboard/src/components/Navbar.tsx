import { Link, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { logout, fetchAlerts } from '../api';
import type { SepsisAlert } from '../types';

const NAV = [
  { to: '/', label: 'Dashboard', icon: '⚡' },
  { to: '/patients', label: 'Patients', icon: '🏥' },
  { to: '/alerts', label: 'Alerts', icon: '🔔' },
  { to: '/doctors', label: 'Doctors', icon: '👨‍⚕️' },
];

export function Navbar() {
  const { pathname } = useLocation();

  const { data: unacked } = useQuery<SepsisAlert[]>({
    queryKey: ['alerts', 'unacked'],
    queryFn: () => fetchAlerts(true),
    refetchInterval: 30_000,
  });
  const alertCount = unacked?.filter((a) => !a.acknowledged).length ?? 0;

  return (
    <>
      {/* Top bar */}
      <header className="fixed top-0 z-30 w-full border-b border-slate-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-2xl items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <span className="font-bold tracking-tight text-slate-900">🩺 SepsisWatch</span>
            {alertCount > 0 && (
              <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-xs font-bold text-white">
                {alertCount > 99 ? '99+' : alertCount}
              </span>
            )}
          </div>
          <button
            onClick={logout}
            className="rounded-lg px-3 py-1.5 text-sm text-slate-500 hover:bg-slate-100 active:bg-slate-200"
          >
            Log out
          </button>
        </div>
      </header>

      {/* Bottom tab bar (mobile nav) */}
      <nav className="fixed bottom-0 z-30 w-full border-t border-slate-200 bg-white/90 backdrop-blur">
        <ul className="mx-auto flex max-w-2xl justify-around">
          {NAV.map(({ to, label, icon }) => {
            const active = to === '/' ? pathname === '/' : pathname.startsWith(to);
            const showBadge = to === '/alerts' && alertCount > 0;
            return (
              <li key={to} className="flex-1">
                <Link
                  to={to}
                  className={`relative flex flex-col items-center py-2 text-xs transition-colors ${
                    active ? 'text-blue-600 font-semibold' : 'text-slate-500'
                  }`}
                >
                  <span className="relative text-xl leading-none">
                    {icon}
                    {showBadge && (
                      <span className="absolute -right-1 -top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-red-500 px-0.5 text-[9px] font-bold text-white leading-none">
                        {alertCount > 9 ? '9+' : alertCount}
                      </span>
                    )}
                  </span>
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </>
  );
}
