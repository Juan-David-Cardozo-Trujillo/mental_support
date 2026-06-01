/**
 * Student Dashboard
 * 
 * Main hub for student users with quick access to:
 * - Latest assessment results
 * - Matching queue status
 * - Upcoming appointments
 * - Resources
 * - Recent chat sessions
 */

import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiClient } from '../../api/client';
import LoadingSpinner from '../../components/LoadingSpinner';

export default function StudentDashboard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState({
    assessment: null,
    appointments: [],
    chatSessions: [],
  });

  useEffect(() => {
    const loadDashboardData = async () => {
      try {
        setLoading(true);
        
        // Load assessment
        const assessmentRes = await apiClient.get('/assessment');
        
        // Load appointments
        const appointmentsRes = await apiClient.get('/appointments/my');
        
        // Load chat sessions (if available)
        let chatSessions = [];
        try {
          const chatRes = await apiClient.get('/chat/my');
          chatSessions = chatRes.data;
        } catch (err) {
          // Chat sessions might not be available
        }

        setData({
          assessment: assessmentRes.data,
          appointments: appointmentsRes.data.slice(0, 3), // Next 3
          chatSessions: chatSessions.slice(0, 3), // Recent 3
        });
      } catch (err) {
        console.error('Failed to load dashboard:', err);
        setError(err.response?.data?.error?.message || 'Failed to load dashboard');
      } finally {
        setLoading(false);
      }
    };

    loadDashboardData();
  }, []);

  if (loading) return <LoadingSpinner />;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Welcome Back</h1>
        <p className="text-gray-600 mt-2">
          Your mental health matters. We're here to support you.
        </p>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-yellow-100 border border-yellow-400 text-yellow-700 rounded">
          {error}
        </div>
      )}

      {/* Quick Actions */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <Link
          to="/student/assessment"
          className="bg-blue-600 text-white p-6 rounded-lg hover:bg-blue-700 transition shadow"
        >
          <div className="text-2xl mb-2">📋</div>
          <h3 className="font-semibold">Take Assessment</h3>
          <p className="text-sm mt-1 text-blue-100">
            Tell us how you're feeling
          </p>
        </Link>

        <Link
          to="/student/matching"
          className="bg-purple-600 text-white p-6 rounded-lg hover:bg-purple-700 transition shadow"
        >
          <div className="text-2xl mb-2">🤝</div>
          <h3 className="font-semibold">Find Peer Support</h3>
          <p className="text-sm mt-1 text-purple-100">
            Connect with a counselor now
          </p>
        </Link>

        <Link
          to="/student/appointments"
          className="bg-green-600 text-white p-6 rounded-lg hover:bg-green-700 transition shadow"
        >
          <div className="text-2xl mb-2">📅</div>
          <h3 className="font-semibold">Book Appointment</h3>
          <p className="text-sm mt-1 text-green-100">
            Schedule with a professional
          </p>
        </Link>

        <Link
          to="/student/resources"
          className="bg-orange-600 text-white p-6 rounded-lg hover:bg-orange-700 transition shadow"
        >
          <div className="text-2xl mb-2">📚</div>
          <h3 className="font-semibold">Explore Resources</h3>
          <p className="text-sm mt-1 text-orange-100">
            Learn and grow at your pace
          </p>
        </Link>
      </div>

      {/* Latest Assessment */}
      {data.assessment && (
        <div className="bg-white rounded-lg shadow p-6 mb-8">
          <h2 className="text-xl font-semibold mb-4">📊 Latest Assessment</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <p className="text-gray-600">Stress Level</p>
              <p className="text-3xl font-bold text-blue-600">
                {data.assessment.stress_level}/5
              </p>
            </div>
            <div>
              <p className="text-gray-600">Support Type</p>
              <p className="text-lg font-semibold text-purple-600">
                {data.assessment.support_type}
              </p>
            </div>
            <div>
              <p className="text-gray-600">Urgency</p>
              <span className={`inline-block px-3 py-1 rounded-full text-sm font-semibold ${
                data.assessment.urgency_flag 
                  ? 'bg-red-100 text-red-700' 
                  : 'bg-green-100 text-green-700'
              }`}>
                {data.assessment.urgency_flag ? '🔴 Urgent' : '✓ Normal'}
              </span>
            </div>
          </div>
          <Link
            to="/student/assessment"
            className="mt-4 inline-block text-blue-600 hover:underline text-sm"
          >
            Update Assessment →
          </Link>
        </div>
      )}

      {/* Upcoming Appointments */}
      {data.appointments.length > 0 && (
        <div className="bg-white rounded-lg shadow p-6 mb-8">
          <h2 className="text-xl font-semibold mb-4">📅 Upcoming Appointments</h2>
          <div className="space-y-4">
            {data.appointments.map((appt) => (
              <div key={appt.id} className="border-l-4 border-blue-600 pl-4 py-2">
                <p className="font-semibold text-gray-900">
                  {new Date(appt.appointment_datetime).toLocaleDateString()} at{' '}
                  {new Date(appt.appointment_datetime).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </p>
                <p className="text-sm text-gray-600">
                  Status: <span className="font-semibold">{appt.status}</span>
                </p>
              </div>
            ))}
          </div>
          <Link
            to="/student/appointments"
            className="mt-4 inline-block text-blue-600 hover:underline text-sm"
          >
            View All Appointments →
          </Link>
        </div>
      )}

      {/* Information Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg p-6">
          <h3 className="font-semibold text-gray-900 mb-2">💬 How It Works</h3>
          <p className="text-sm text-gray-700">
            Take an assessment to get matched with a peer counselor or book a professional appointment.
          </p>
        </div>

        <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-lg p-6">
          <h3 className="font-semibold text-gray-900 mb-2">🔒 Your Privacy</h3>
          <p className="text-sm text-gray-700">
            Everything is anonymous and encrypted. We never share your information.
          </p>
        </div>

        <div className="bg-gradient-to-br from-green-50 to-green-100 rounded-lg p-6">
          <h3 className="font-semibold text-gray-900 mb-2">⚡ Crisis Support</h3>
          <p className="text-sm text-gray-700">
            For emergencies, call 911 or text HOME to 741741 (Crisis Text Line).
          </p>
        </div>
      </div>
    </div>
  );
}
