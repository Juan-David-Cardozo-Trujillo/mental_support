/**
 * Placeholder pages for remaining frontend routes
 * 
 * These provide the basic structure for all portals
 * Implementation can be completed incrementally based on API responses
 */

// ============================================================================
// STUDENT PAGES
// ============================================================================

export { default as StudentAssessment } from './assessment/Assessment';
export { default as StudentMatchingQueue } from './matching/Queue';
export { default as StudentChat } from './chat/Chat';
export { default as StudentAppointments } from './appointments/Appointments';
export { default as StudentResources } from './resources/Resources';
export { default as StudentFeedback } from './feedback/Feedback';

// ============================================================================
// PEER PAGES
// ============================================================================

export { default as PeerAvailability } from './availability/Availability';
export { default as PeerSessions } from './sessions/Sessions';
export { default as PeerWellness } from './wellness/Wellness';
export { default as PeerBadges } from './badges/Badges';

// ============================================================================
// PROFESSIONAL PAGES
// ============================================================================

export { default as ProfessionalSchedule } from './schedule/Schedule';
export { default as ProfessionalAvailability } from './availability/Availability';
export { default as ProfessionalAppointments } from './appointments/Appointments';
export { default as ProfessionalMetrics } from './metrics/Metrics';

// ============================================================================
// ADMIN PAGES
// ============================================================================

export { default as AdminDashboard } from './dashboard/Dashboard';
