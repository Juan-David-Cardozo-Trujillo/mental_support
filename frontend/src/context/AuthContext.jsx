import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { authApi } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null) // { profile_id, role, account_status, display_name }
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Hydrate user state on mount by calling /auth/me
  useEffect(() => {
    const hydrateUser = async () => {
      try {
        const response = await authApi.me()
        setUser(response.data)
      } catch (err) {
        // 401 means not authenticated — normal state on public pages
        if (err.response?.status !== 401) {
          setError(err.message)
        }
        setUser(null)
      } finally {
        setLoading(false)
      }
    }

    hydrateUser()
  }, [])

  const login = useCallback(async (redirectUrl) => {
    // SSO: backend redirects to university IdP
    // The redirect URL is provided by the backend
    if (redirectUrl) {
      window.location.href = redirectUrl
    } else {
      try {
        const response = await authApi.login({})
        if (response.data?.redirect_url) {
          window.location.href = response.data.redirect_url
        }
      } catch (err) {
        setError('Login failed. Please try again.')
      }
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } catch {
      // Best-effort logout
    } finally {
      setUser(null)
      window.location.href = '/login'
    }
  }, [])

  const refreshUser = useCallback(async () => {
    try {
      const response = await authApi.me()
      setUser(response.data)
    } catch {
      setUser(null)
    }
  }, [])

  const value = {
    user,
    loading,
    error,
    login,
    logout,
    refreshUser,
    isAuthenticated: !!user,
    isStudent: user?.role === 'student',
    isPeer: user?.role === 'peer_counselor',
    isProfessional: user?.role === 'professional_counselor',
    isUniversityAdmin: user?.role === 'university_admin',
    isPlatformAdmin: user?.role === 'platform_admin',
    needsConsent: user?.account_status === 'pending_consent',
    needsTraining: user?.account_status === 'pending_training',
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

export default AuthContext
