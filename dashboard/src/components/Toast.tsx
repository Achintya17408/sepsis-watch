import { useEffect, useState, useCallback } from 'react';

export interface Toast {
  id: string;
  message: string;
  type: 'success' | 'error' | 'info';
}

// Module-level store — simple enough without a full context
let _listeners: Array<(t: Toast) => void> = [];

export function showToast(message: string, type: Toast['type'] = 'success') {
  const t: Toast = { id: Math.random().toString(36).slice(2), message, type };
  _listeners.forEach((fn) => fn(t));
}

const BG: Record<Toast['type'], string> = {
  success: 'bg-green-700',
  error: 'bg-red-600',
  info: 'bg-slate-800',
};

const ICON: Record<Toast['type'], string> = {
  success: '✓',
  error: '✕',
  info: 'ℹ',
};

export function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const add = useCallback((t: Toast) => {
    setToasts((prev) => [...prev, t]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== t.id));
    }, 3000);
  }, []);

  useEffect(() => {
    _listeners.push(add);
    return () => {
      _listeners = _listeners.filter((fn) => fn !== add);
    };
  }, [add]);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-24 left-1/2 z-50 flex -translate-x-1/2 flex-col items-center gap-2 px-4 w-full max-w-sm pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex w-full items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium text-white shadow-lg ${BG[t.type]} animate-fade-in`}
        >
          <span className="shrink-0 font-bold">{ICON[t.type]}</span>
          {t.message}
        </div>
      ))}
    </div>
  );
}
