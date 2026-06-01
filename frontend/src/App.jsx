/**
 * Main Application Component
 * 
 * Routes:
 * - / → Landing page or redirect to portal
 * - /sso/callback → SSO callback handler
 * - /consent → Consent modal
 * - /student/* → Student portal
 * - /peer/* → Peer counselor portal
 * - /professional/* → Professional counselor portal
 * - /admin/* → Admin dashboard
 */

import React, { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';
import GlobalErrorBoundary from './components/GlobalErrorBoundary';
import SessionTimeoutWarning from './components/SessionTimeoutWarning';
import NavBar from './components/NavBar';
import LoadingSpinner from './components/LoadingSpinner';

// Landing & Auth
import Landing from './pages/Landing';
import SSOCallback from './pages/auth/SSOCallback';
import ConsentModal from './pages/auth/ConsentModal';

// Student Portal
import StudentDashboard from './pages/student/Dashboard';
import StudentAssessment from './pages/student/Assessment';
import StudentMatchingQueue from './pages/student/MatchingQueue';
import StudentChat from './pages/student/Chat';
import StudentAppointments from './pages/student/Appointments';
import StudentResources from './pages/student/Resources';
import StudentFeedback from './pages/student/Feedback';

// Peer Portal
import PeerDashboard from './pages/peer/Dashboard';
import PeerAvailability from './pages/peer/Availability';
import PeerSessions from './pages/peer/Sessions';
import PeerWellness from './pages/peer/Wellness';
import PeerBadges from './pages/peer/Badges';

// Professional Portal
import ProfessionalSchedule from './pages/professional/Schedule';
import ProfessionalAvailability from './pages/professional/Availability';
import ProfessionalAppointments from './pages/professional/Appointments';
import ProfessionalMetrics from './pages/professional/Metrics';

// Admin
import AdminDashboard from './pages/admin/Dashboard';

/**
 * Protected Route wrapper
 */
function ProtectedRoute({ children, requiredRole }) {
  const { user, loading } = useAuth();

  if (loading) return <LoadingSpinner />;
  
  if (!user) {
    return <Navigate to="/" replace />;
  }

  if (requiredRole && !requiredRole.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  return children;
}

/**
 * Main App Component
 */
function App() {
  const { user, loading, isAuthenticated } = useAuth();
  const [showSessionWarning, setShowSessionWarning] = useState(false);

  if (loading) {
    return <LoadingSpinner />;
  }

  return (
    <GlobalErrorBoundary>
      <BrowserRouter>
        <div className="min-h-screen bg-gray-50">
          {/* Session warning modal */}
          {isAuthenticated && <SessionTimeoutWarning />}
          
          {/* Navigation bar (only when authenticated) */}
          {isAuthenticated && <NavBar user={user} />}
          
          {/* Main content */}
          <main className={isAuthenticated ? 'pt-16' : ''}>
            <Routes>
              {/* Public routes */}
              <Route path="/" element={<Landing />} />
              <Route path="/sso/callback" element={<SSOCallback />} />
              <Route path="/consent" element={
                <ProtectedRoute>
                  <ConsentModal />
                </ProtectedRoute>
              } />

              {/* Student Portal */}
              <Route path="/student/dashboard" element={
                <ProtectedRoute requiredRole={['student']}>
                  <StudentDashboard />
                </ProtectedRoute>
              } />
              <Route path="/student/assessment" element={
                <ProtectedRoute requiredRole={['student']}>
                  <StudentAssessment />
                </ProtectedRoute>
              } />
              <Route path="/student/matching" element={
                <ProtectedRoute requiredRole={['student']}>
                  <StudentMatchingQueue />
                </ProtectedRoute>
              } />
              <Route path="/student/chat/:sessionId" element={
                <ProtectedRoute requiredRole={['student']}>
                  <StudentChat />
                </ProtectedRoute>
              } />
              <Route path="/student/appointments" element={
                <ProtectedRoute requiredRole={['student']}>
                  <StudentAppointments />
                </ProtectedRoute>
              } />
              <Route path="/student/resources" element={
                <ProtectedRoute requiredRole={['student']}>
                  <StudentResources />
                </ProtectedRoute>
              } />
              <Route path="/student/feedback/:sessionId" element={
                <ProtectedRoute requiredRole={['student']}>
                  <StudentFeedback />
                </ProtectedRoute>
              } />

              {/* Peer Counselor Portal */}
              <Route path="/peer/dashboard" element={
                <ProtectedRoute requiredRole={['peer_counselor']}>
                  <PeerDashboard />
                </ProtectedRoute>
              } />
              <Route path="/peer/availability" element={
                <ProtectedRoute requiredRole={['peer_counselor']}>
                  <PeerAvailability />
                </ProtectedRoute>
              } />
              <Route path="/peer/sessions" element={
                <ProtectedRoute requiredRole={['peer_counselor']}>
                  <PeerSessions />
                </ProtectedRoute>
              } />
              <Route path="/peer/wellness" element={
                <ProtectedRoute requiredRole={['peer_counselor']}>
                  <PeerWellness />
                </ProtectedRoute>
              } />
              <Route path="/peer/badges" element={
                <ProtectedRoute requiredRole={['peer_counselor']}>
                  <PeerBadges />
                </ProtectedRoute>
              } />

              {/* Professional Counselor Portal */}
              <Route path="/professional/schedule" element={
                <ProtectedRoute requiredRole={['professional_counselor']}>
                  <ProfessionalSchedule />
                </ProtectedRoute>
              } />
              <Route path="/professional/availability" element={
                <ProtectedRoute requiredRole={['professional_counselor']}>
                  <ProfessionalAvailability />
                </ProtectedRoute>
              } />
              <Route path="/professional/appointments" element={
                <ProtectedRoute requiredRole={['professional_counselor']}>
                  <ProfessionalAppointments />
                </ProtectedRoute>
              } />
              <Route path="/professional/metrics" element={
                <ProtectedRoute requiredRole={['professional_counselor']}>
                  <ProfessionalMetrics />
                </ProtectedRoute>
              } />

              {/* Admin Portal */}
              <Route path="/admin/dashboard" element={
                <ProtectedRoute requiredRole={['university_admin', 'platform_admin']}>
                  <AdminDashboard />
                </ProtectedRoute>
              } />

              {/* Catch all */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </GlobalErrorBoundary>
  );
}

export default App;
