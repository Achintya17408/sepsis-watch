import { useState, useCallback } from 'react';
import { login as apiLogin, logout as apiLogout, isLoggedIn } from '../api';

export function useAuth() {
  const [loggedIn, setLoggedIn] = useState(isLoggedIn);
  const [error, setError] = useState('');

  const login = useCallback(async (username: string, password: string) => {
    setError('');
    try {
      await apiLogin(username, password);
      setLoggedIn(true);
    } catch {
      setError('Invalid username or password');
    }
  }, []);

  const logout = useCallback(() => {
    apiLogout();
    setLoggedIn(false);
  }, []);

  return { loggedIn, login, logout, error };
}
