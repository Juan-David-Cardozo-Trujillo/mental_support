/**
 * SSO Callback Handler
 * 
 * Handles OAuth 2.0 callback from university SSO
 * Exchanges authorization code for JWT token
 */

import React, { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import LoadingSpinner from '../../components/LoadingSpinner';
import { apiClient } from '../../api/client';

export default function SSOCallback() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { setUser } = useAuth();
  const [error, setError] = React.useState(null);

  useEffect(() => {
    const handleCallback = async () => {
      try {
        const code = searchParams.get('code');
        const state = searchParams.get('state');

        if (!code) {
          setError('Missing authorization code from SSO provider');
          return;
        }

        // Exchange code for token
        const response = await apiClient.post('/auth/sso/callback', {
          code,
          state,
        });

        // Save JWT token (from cookie, but also store in localStorage for API calls)
        const { profile } = response.data;
        setUser(profile);

        // Redirect based on role and consent status
        if (!profile.consented) {
          navigate('/consent', { replace: true });
        } else {
          const dashboards = {
            student: '/student/dashboard',
            peer_counselor: '/peer/dashboard',
            professional_counselor: '/professional/schedule',
            university_admin: '/admin/dashboard',
            platform_admin: '/admin/dashboard',
          };
          navigate(dashboards[profile.role] || '/', { replace: true });
        }
      } catch (err) {
        console.error('SSO callback error:', err);
        setError(err.response?.data?.error?.message || 'Authentication failed');
        setTimeout(() => navigate('/', { replace: true }), 3000);
      }
    };

    handleCallback();
  }, [searchParams, navigate, setUser]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      {error ? (
        <div className="text-center">
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
            <p className="font-bold">Authentication Error</p>
            <p>{error}</p>
            <p className="text-sm mt-2">Redirecting to login...</p>
          </div>
        </div>
      ) : (
        <div className="text-center">
          <LoadingSpinner />
          <p className="mt-4 text-gray-600">Completing authentication...</p>
        </div>
      )}
    </div>
  );
}
