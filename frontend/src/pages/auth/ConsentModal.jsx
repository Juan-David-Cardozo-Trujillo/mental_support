/**
 * Consent Modal (RULE-11)
 * 
 * Users must accept consent before using any platform features
 * Displays privacy policy and terms of service
 */

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { apiClient } from '../../api/client';

export default function ConsentModal() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [accepted, setAccepted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleConsent = async () => {
    try {
      setLoading(true);
      setError(null);

      // Submit consent
      await apiClient.post('/auth/consent', {
        accepted: true,
      });

      // Redirect to appropriate dashboard
      const dashboards = {
        student: '/student/dashboard',
        peer_counselor: '/peer/dashboard',
        professional_counselor: '/professional/schedule',
        university_admin: '/admin/dashboard',
        platform_admin: '/admin/dashboard',
      };

      navigate(dashboards[user?.role] || '/', { replace: true });
    } catch (err) {
      setError(err.response?.data?.error?.message || 'Failed to save consent');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-2xl w-full bg-white rounded-lg shadow-lg p-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-6">
          Welcome to MindBridge
        </h1>

        {/* Privacy Commitment */}
        <div className="bg-blue-50 border-l-4 border-blue-600 p-4 mb-6">
          <h2 className="font-semibold text-blue-900 mb-2">🔒 Your Privacy is Sacred</h2>
          <p className="text-blue-800 text-sm">
            We take your privacy seriously. All conversations are encrypted, 
            your identity remains completely anonymous, and your data is never shared.
          </p>
        </div>

        {/* Terms and Policy */}
        <div className="space-y-6 mb-8 max-h-96 overflow-y-auto">
          <div>
            <h3 className="font-semibold text-gray-900 mb-2">📋 Platform Terms</h3>
            <div className="text-sm text-gray-700 space-y-2">
              <p>✓ You understand that peer counselors are trained students, not licensed professionals</p>
              <p>✓ For emergencies, always contact emergency services (911) or crisis hotlines</p>
              <p>✓ All conversations are confidential and encrypted at rest</p>
              <p>✓ The platform logs minimal metadata for safety and legal compliance</p>
              <p>✓ You understand and accept our data retention policies</p>
            </div>
          </div>

          <div>
            <h3 className="font-semibold text-gray-900 mb-2">🛡️ Privacy Guarantees</h3>
            <div className="text-sm text-gray-700 space-y-2">
              <p>✓ Your real name and university ID are never stored</p>
              <p>✓ Chat messages are encrypted end-to-end (AES-256)</p>
              <p>✓ Short messages (24h) are auto-deleted; longer sessions archived securely</p>
              <p>✓ No tracking or analytics on your conversations</p>
              <p>✓ You can request your data or request deletion anytime</p>
            </div>
          </div>

          <div>
            <h3 className="font-semibold text-gray-900 mb-2">⚠️ Community Standards</h3>
            <div className="text-sm text-gray-700 space-y-2">
              <p>✓ Harassment, hate speech, or abuse is not tolerated</p>
              <p>✓ Peers and counselors can report concerning behavior</p>
              <p>✓ Repeated violations may result in account suspension</p>
              <p>✓ If you feel unsafe, report immediately or contact emergency services</p>
            </div>
          </div>
        </div>

        {/* Error message */}
        {error && (
          <div className="mb-6 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
            {error}
          </div>
        )}

        {/* Checkbox */}
        <div className="mb-6">
          <label className="flex items-start cursor-pointer">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
              className="mt-1 w-4 h-4 text-blue-600 rounded"
            />
            <span className="ml-3 text-sm text-gray-700">
              I understand and accept the terms and privacy policies. 
              I acknowledge that I will use this platform responsibly.
            </span>
          </label>
        </div>

        {/* Actions */}
        <div className="flex gap-4">
          <button
            onClick={() => navigate('/', { replace: true })}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50 transition"
          >
            Decline
          </button>
          <button
            onClick={handleConsent}
            disabled={!accepted || loading}
            className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 transition"
          >
            {loading ? 'Saving...' : 'Accept & Continue'}
          </button>
        </div>

        {/* Footer */}
        <p className="text-xs text-gray-500 text-center mt-4">
          By accepting, you agree to our Terms of Service and Privacy Policy.
          See help@mindbridge.edu for questions.
        </p>
      </div>
    </div>
  );
}
