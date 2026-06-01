/**
 * Landing Page
 * 
 * Public page with SSO login button and platform information
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '../api/client';

export default function Landing() {
  const navigate = useNavigate();
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);

  const handleSSO = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Start SSO flow
      const response = await apiClient.get('/auth/sso/start');
      const { authorization_url } = response.data;
      
      // Redirect to university SSO
      window.location.href = authorization_url;
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Failed to start SSO');
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-600 to-purple-600">
      {/* Navigation */}
      <nav className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <h1 className="text-2xl font-bold text-gray-900">MindBridge</h1>
          <p className="text-sm text-gray-600">Student Mental Health Support Platform</p>
        </div>
      </nav>

      {/* Hero section */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="text-center">
          <h2 className="text-5xl font-bold text-white mb-6">
            Your Mental Health Matters
          </h2>
          <p className="text-xl text-blue-100 mb-8">
            Connect with peer counselors and mental health professionals.
            Completely anonymous. Always supportive.
          </p>

          {/* Features */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 my-12">
            <div className="bg-white rounded-lg shadow-lg p-6">
              <div className="text-4xl mb-4">🤝</div>
              <h3 className="text-xl font-semibold mb-2">Peer Support</h3>
              <p className="text-gray-600">
                Connect with trained peer counselors who understand student life.
              </p>
            </div>

            <div className="bg-white rounded-lg shadow-lg p-6">
              <div className="text-4xl mb-4">👨‍⚕️</div>
              <h3 className="text-xl font-semibold mb-2">Professional Help</h3>
              <p className="text-gray-600">
                Book appointments with licensed mental health professionals.
              </p>
            </div>

            <div className="bg-white rounded-lg shadow-lg p-6">
              <div className="text-4xl mb-4">🔒</div>
              <h3 className="text-xl font-semibold mb-2">Complete Privacy</h3>
              <p className="text-gray-600">
                Your conversations are encrypted and completely anonymous.
              </p>
            </div>
          </div>

          {/* Login button */}
          <div className="mt-12">
            {error && (
              <div className="mb-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
                {error}
              </div>
            )}
            <button
              onClick={handleSSO}
              disabled={loading}
              className="bg-white text-blue-600 px-8 py-3 rounded-lg font-semibold text-lg hover:bg-gray-50 disabled:opacity-50 transition"
            >
              {loading ? 'Connecting...' : 'Login with University SSO'}
            </button>
            <p className="text-blue-100 text-sm mt-4">
              Secure login through your university account
            </p>
          </div>
        </div>
      </div>

      {/* Footer info */}
      <div className="bg-white bg-opacity-10 text-white text-center py-6 mt-20">
        <p className="text-sm">
          🌍 100% Anonymous | 🔐 End-to-End Encrypted | ⚡ Always Available
        </p>
      </div>
    </div>
  );
}
