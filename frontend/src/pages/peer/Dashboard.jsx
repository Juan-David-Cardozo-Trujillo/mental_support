/**
 * Peer Counselor Dashboard
 * 
 * Hub for peer counselors with:
 * - Burnout indicator (green/yellow/red levels)
 * - Session statistics
 * - Badges earned
 * - Wellness recommendations
 * - Toggle availability
 */

import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../../api/client';
import LoadingSpinner from '../../components/LoadingSpinner';

export default function PeerDashboard() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [wellness, setWellness] = useState(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        
        // Load dashboard
        const dashRes = await apiClient.get('/peer/dashboard');
        setDashboard(dashRes.data);

        // Load wellness check
        const wellRes = await apiClient.get('/peer/wellness');
        setWellness(wellRes.data);
      } catch (err) {
        console.error('Failed to load dashboard:', err);
        setError(err.response?.data?.error?.message || 'Failed to load dashboard');
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, []);

  if (loading) return <LoadingSpinner />;

  if (!dashboard || !wellness) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-yellow-100 border border-yellow-400 text-yellow-700 p-4 rounded">
          {error || 'Failed to load dashboard data'}
        </div>
      </div>
    );
  }

  const burnoutLevel = wellness.burnout_indicator.level;
  const burnoutColor = {
    green: { bg: 'bg-green-100', text: 'text-green-700', border: 'border-green-400' },
    yellow: { bg: 'bg-yellow-100', text: 'text-yellow-700', border: 'border-yellow-400' },
    red: { bg: 'bg-red-100', text: 'text-red-700', border: 'border-red-400' },
  }[burnoutLevel];

  const burnoutEmoji = {
    green: '✓',
    yellow: '⚠️',
    red: '🔴',
  }[burnoutLevel];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Peer Counselor Dashboard</h1>
        <p className="text-gray-600 mt-2">
          Thank you for supporting your peers!
        </p>
      </div>

      {/* BURNOUT INDICATOR - CRITICAL */}
      <div className={`${burnoutColor.bg} ${burnoutColor.text} border-l-4 ${burnoutColor.border} p-6 rounded-lg mb-8 shadow-lg`}>
        <div className="flex items-start justify-between">
          <div>
            <div className="text-4xl font-bold mb-2">
              {burnoutEmoji} {burnoutLevel.toUpperCase()}
            </div>
            <p className="text-lg font-semibold mb-3">
              {wellness.burnout_indicator.message}
            </p>
            <p className="mb-4">
              {wellness.burnout_indicator.recommendation}
            </p>
            <div className="text-sm space-y-1">
              <p>📊 Session Risk: {(wellness.burnout_indicator.session_risk * 100).toFixed(0)}%</p>
              <p>📅 Daily Risk: {(wellness.burnout_indicator.daily_risk * 100).toFixed(0)}%</p>
              <p>📢 Report Risk: {(wellness.burnout_indicator.report_risk * 100).toFixed(0)}%</p>
            </div>
          </div>
          <Link
            to="/peer/wellness"
            className="bg-white px-4 py-2 rounded font-semibold hover:bg-gray-50 transition whitespace-nowrap ml-4"
          >
            Learn More
          </Link>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-gray-600 text-sm">Sessions Completed</p>
          <p className="text-3xl font-bold text-blue-600">
            {dashboard.stats.sessions_completed}
          </p>
          <p className="text-xs text-gray-500 mt-2">
            Goal: 20 sessions threshold
          </p>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-gray-600 text-sm">Average Rating</p>
          <p className="text-3xl font-bold text-yellow-600">
            {dashboard.stats.average_rating?.toFixed(1) || 'N/A'}/5
          </p>
          <p className="text-xs text-gray-500 mt-2">
            From student feedback
          </p>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-gray-600 text-sm">Total Messages</p>
          <p className="text-3xl font-bold text-purple-600">
            {dashboard.stats.total_messages}
          </p>
          <p className="text-xs text-gray-500 mt-2">
            Across all sessions
          </p>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-gray-600 text-sm">Reports (7d)</p>
          <p className="text-3xl font-bold text-red-600">
            {dashboard.stats.reports_7d}
          </p>
          <p className="text-xs text-gray-500 mt-2">
            Max 3 before suspension
          </p>
        </div>
      </div>

      {/* Actions */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <Link
          to="/peer/availability"
          className="bg-gradient-to-br from-blue-600 to-blue-700 text-white p-6 rounded-lg hover:shadow-lg transition"
        >
          <div className="text-3xl mb-2">📅</div>
          <h3 className="font-semibold text-lg">Availability</h3>
          <p className="text-sm mt-2 text-blue-100">
            Toggle availability and view schedule
          </p>
        </Link>

        <Link
          to="/peer/sessions"
          className="bg-gradient-to-br from-purple-600 to-purple-700 text-white p-6 rounded-lg hover:shadow-lg transition"
        >
          <div className="text-3xl mb-2">💬</div>
          <h3 className="font-semibold text-lg">Sessions</h3>
          <p className="text-sm mt-2 text-purple-100">
            View your chat history and feedback
          </p>
        </Link>

        <Link
          to="/peer/badges"
          className="bg-gradient-to-br from-amber-600 to-amber-700 text-white p-6 rounded-lg hover:shadow-lg transition"
        >
          <div className="text-3xl mb-2">🏆</div>
          <h3 className="font-semibold text-lg">Badges</h3>
          <p className="text-sm mt-2 text-amber-100">
            View milestones and achievements
          </p>
        </Link>
      </div>

      {/* Badges Section */}
      {dashboard.badges_earned > 0 && (
        <div className="bg-white rounded-lg shadow p-6 mb-8">
          <h2 className="text-xl font-semibold mb-4">🏆 Earned Badges</h2>
          <div className="flex flex-wrap gap-4">
            {dashboard.badges_earned >= 1 && (
              <div className="text-center">
                <div className="text-4xl mb-2">🥉</div>
                <p className="text-sm font-semibold">10 Sessions</p>
              </div>
            )}
            {dashboard.badges_earned >= 2 && (
              <div className="text-center">
                <div className="text-4xl mb-2">🥈</div>
                <p className="text-sm font-semibold">25 Sessions</p>
              </div>
            )}
            {dashboard.badges_earned >= 3 && (
              <div className="text-center">
                <div className="text-4xl mb-2">🥇</div>
                <p className="text-sm font-semibold">50 Sessions</p>
              </div>
            )}
            {dashboard.badges_earned >= 4 && (
              <div className="text-center">
                <div className="text-4xl mb-2">👑</div>
                <p className="text-sm font-semibold">100 Sessions</p>
              </div>
            )}
          </div>
          <Link
            to="/peer/badges"
            className="mt-4 inline-block text-blue-600 hover:underline text-sm"
          >
            View All Achievements →
          </Link>
        </div>
      )}

      {/* Training Status */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold mb-4">📚 Training Progress</h2>
        <div className="bg-gray-100 rounded p-4">
          <p className="text-sm font-semibold text-gray-700 mb-2">
            {dashboard.training_status}
          </p>
          <Link
            to="/student/training"
            className="text-blue-600 hover:underline text-sm"
          >
            View Training Modules →
          </Link>
        </div>
      </div>
    </div>
  );
}
