/**
 * API Client for Mental Health Platform
 * 
 * Features:
 * - JWT token management (HttpOnly cookies + localStorage)
 * - Automatic retry on 5xx and network errors
 * - Global error handling
 * - Consent gate enforcement
 * - Request/response logging
 */

import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'

const apiClient = axios.create({
  baseURL: BASE_URL,
  withCredentials: true, // Send HttpOnly cookie JWT automatically
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 15000,
})

// ──────────────────────────────────────────────────────────────────────────
// Request Interceptor - Add JWT token to Authorization header
// ──────────────────────────────────────────────────────────────────────────

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('jwt_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ──────────────────────────────────────────────────────────────────────────
// Response Interceptor - Handle errors and retries
// ──────────────────────────────────────────────────────────────────────────

// Exponential backoff helper
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const MAX_RETRIES = 3

apiClient.interceptors.response.use(
  (response) => {
    // Store JWT token from response if provided
    if (response.data?.token) {
      localStorage.setItem('jwt_token', response.data.token)
    }
    return response
  },
  async (error) => {
    const config = error.config

    // Initialize retry count
    if (!config) return Promise.reject(error)
    config._retryCount = config._retryCount || 0

    const status = error.response?.status

    // 401 - Authentication required
    if (status === 401) {
      localStorage.removeItem('jwt_token')
      if (!config.url?.includes('/auth')) {
        window.location.href = '/'
      }
      return Promise.reject(error)
    }

    // 403 - Check for CONSENT_REQUIRED
    if (status === 403 && error.response?.data?.error?.code === 'CONSENT_REQUIRED') {
      window.location.href = '/consent'
      return Promise.reject(error)
    }

    // Retry on 5xx or network errors
    const isNetworkError = !error.response
    const isServerError = status >= 500 && status <= 599

    if ((isNetworkError || isServerError) && config._retryCount < MAX_RETRIES) {
      config._retryCount += 1
      const backoffMs = Math.pow(2, config._retryCount - 1) * 1000 // 1s, 2s, 4s
      await delay(backoffMs)
      return apiClient(config)
    }

    return Promise.reject(error)
  }
)

export default apiClient

// Auth endpoints
export const authApi = {
  me: () => apiClient.get('/auth/me'),
  login: (data) => apiClient.post('/auth/sso/initiate', data),
  logout: () => apiClient.post('/auth/logout'),
  refreshToken: () => apiClient.post('/auth/token/refresh'),
}

// Student endpoints
export const studentApi = {
  submitConsent: (data) => apiClient.post('/student/consent', data),
  submitAssessment: (data) => apiClient.post('/student/assessment', data),
  getMatchingStatus: () => apiClient.get('/student/matching/status'),
}

// Session/Chat endpoints
export const sessionApi = {
  getSession: (sessionId) => apiClient.get(`/session/${sessionId}`),
  sendMessage: (sessionId, data) => apiClient.post(`/session/${sessionId}/message`, data),
  endSession: (sessionId) => apiClient.post(`/session/${sessionId}/end`),
  escalateSession: (sessionId) => apiClient.post(`/session/${sessionId}/escalate`),
  reportConcern: (sessionId, data) => apiClient.post(`/session/${sessionId}/report`, data),
  submitFeedback: (sessionId, data) => apiClient.post(`/session/${sessionId}/feedback`, data),
}

// Appointments endpoints
export const appointmentApi = {
  getAvailableSlots: (month, year) =>
    apiClient.get('/appointments/available', { params: { month, year } }),
  bookAppointment: (data) => apiClient.post('/appointments', data),
  getMyAppointments: () => apiClient.get('/appointments/my'),
  confirmAppointment: (id) => apiClient.post(`/appointments/${id}/confirm`),
  declineAppointment: (id) => apiClient.post(`/appointments/${id}/decline`),
}

// Resources endpoints
export const resourceApi = {
  getResources: (params) => apiClient.get('/resources', { params }),
  getResource: (id) => apiClient.get(`/resources/${id}`),
  createResource: (data) => apiClient.post('/resources', data),
  updateResource: (id, data) => apiClient.put(`/resources/${id}`, data),
  deactivateResource: (id) => apiClient.post(`/resources/${id}/deactivate`),
}

// Peer counselor endpoints
export const peerApi = {
  getTrainingStatus: () => apiClient.get('/peer/training/status'),
  submitTrainingAnswer: (data) => apiClient.post('/peer/training/answer', data),
  completeTraining: (data) => apiClient.post('/peer/training/complete', data),
  getDashboard: () => apiClient.get('/peer/dashboard'),
  toggleAvailability: (available) => apiClient.post('/peer/availability', { available }),
  submitWellnessCheckin: (data) => apiClient.post('/peer/wellness', data),
}

// Professional counselor endpoints
export const professionalApi = {
  getSchedule: () => apiClient.get('/professional/schedule'),
  updateAvailability: (data) => apiClient.put('/professional/availability', data),
  getAppointments: (status) =>
    apiClient.get('/professional/appointments', { params: { status } }),
}

// University admin endpoints
export const uniAdminApi = {
  getDashboard: () => apiClient.get('/admin/university/dashboard'),
  getCounselors: () => apiClient.get('/admin/university/counselors'),
  addCounselor: (data) => apiClient.post('/admin/university/counselors', data),
  deactivateCounselor: (id) => apiClient.post(`/admin/university/counselors/${id}/deactivate`),
  getCalendarPeaks: () => apiClient.get('/admin/university/calendar-peaks'),
  addCalendarPeak: (data) => apiClient.post('/admin/university/calendar-peaks', data),
  getComplianceReport: (params) =>
    apiClient.get('/admin/university/compliance-report', { params }),
}

// Platform admin endpoints
export const platformAdminApi = {
  getMetrics: () => apiClient.get('/admin/platform/metrics'),
  getIncidents: (params) => apiClient.get('/admin/platform/incidents', { params }),
  updateIncident: (id, data) => apiClient.patch(`/admin/platform/incidents/${id}`, data),
  getPeerReports: () => apiClient.get('/admin/platform/peer-reports'),
  suspendPeer: (id) => apiClient.post(`/admin/platform/peers/${id}/suspend`),
  reinstatePeer: (id) => apiClient.post(`/admin/platform/peers/${id}/reinstate`),
  dismissReport: (id) => apiClient.post(`/admin/platform/peer-reports/${id}/dismiss`),
  getSystemHealth: () => apiClient.get('/admin/platform/system-health'),
}
