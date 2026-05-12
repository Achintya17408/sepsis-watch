import { type FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { login } from '../api';
import { Spinner } from '../components/Spinner';

export function LoginPage() {
  const nav = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    const fd = new FormData(e.currentTarget);
    const username = fd.get('username') as string;
    const password = fd.get('password') as string;
    setLoading(true);
    try {
      await login(username, password);
      nav('/');
    } catch {
      setError('Invalid username or password');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-100 to-blue-50 px-4">
      <div className="w-full max-w-sm space-y-6">
        {/* Logo */}
        <div className="text-center">
          <span className="text-4xl">🩺</span>
          <h1 className="mt-2 text-2xl font-bold text-slate-900">SepsisWatch</h1>
          <p className="mt-1 text-sm text-slate-500">Clinical Decision Support</p>
        </div>

        {/* Card */}
        <form onSubmit={handleSubmit} className="card space-y-4">
          {error && (
            <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>
          )}
          <div className="space-y-1">
            <label className="block text-sm font-medium text-slate-700" htmlFor="username">
              Username
            </label>
            <input
              id="username"
              name="username"
              type="text"
              required
              autoComplete="username"
              className="block w-full rounded-xl border border-slate-300 px-4 py-2.5 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div className="space-y-1">
            <label className="block text-sm font-medium text-slate-700" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              required
              autoComplete="current-password"
              className="block w-full rounded-xl border border-slate-300 px-4 py-2.5 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 py-2.5 text-sm font-semibold text-white shadow hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50"
          >
            {loading && <Spinner className="h-4 w-4 border-white border-t-blue-200" />}
            Sign in
          </button>
        </form>
      </div>
    </div>
  );
}
