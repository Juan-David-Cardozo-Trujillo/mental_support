/**
 * useAuth Hook
 * 
 * Manages authentication state and user information
 * Provides login/logout functionality and token management
 */

import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { apiClient } from '../api/client';

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  // Check if user is still authenticated on mount
  useEffect(() => {
    const checkAuth = async () => {
      try {
        // Try to get current user from /auth/me
        const response = await apiClient.get('/auth/me');
        if (response.data) {
          setUser(response.data);
          setIsAuthenticated(true);
        }
      } catch (err) {
        // Not authenticated
        setUser(null);
        setIsAuthenticated(false);
      } finally {
        setLoading(false);
      }
    };

    checkAuth();
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiClient.post('/auth/logout');
      setUser(null);
      setIsAuthenticated(false);
      // Redirect to landing page
      window.location.href = '/';
    } catch (err) {
      console.error('Logout error:', err);
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        setUser,
        loading,
        isAuthenticated,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
