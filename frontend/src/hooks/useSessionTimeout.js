import { useEffect, useRef, useCallback, useState } from 'react'
import { useAuth } from '../context/AuthContext'

const WARNING_TIME = 25 * 60 * 1000  // 25 minutes
const LOGOUT_TIME = 30 * 60 * 1000   // 30 minutes
const ACTIVITY_EVENTS = ['mousemove', 'keypress', 'click', 'touchstart', 'scroll']

export function useSessionTimeout() {
  const { logout, isAuthenticated } = useAuth()
  const [showWarning, setShowWarning] = useState(false)
  const [remainingSeconds, setRemainingSeconds] = useState(300) // 5 min shown in warning

  const warningTimerRef = useRef(null)
  const logoutTimerRef = useRef(null)
  const countdownRef = useRef(null)
  const lastActivityRef = useRef(Date.now())

  const clearAllTimers = useCallback(() => {
    if (warningTimerRef.current) clearTimeout(warningTimerRef.current)
    if (logoutTimerRef.current) clearTimeout(logoutTimerRef.current)
    if (countdownRef.current) clearInterval(countdownRef.current)
  }, [])

  const startCountdown = useCallback(() => {
    let seconds = 300 // 5 minutes = 300 seconds
    setRemainingSeconds(seconds)

    countdownRef.current = setInterval(() => {
      seconds -= 1
      setRemainingSeconds(seconds)
      if (seconds <= 0) {
        clearInterval(countdownRef.current)
      }
    }, 1000)
  }, [])

  const resetTimer = useCallback(() => {
    if (!isAuthenticated) return

    lastActivityRef.current = Date.now()
    setShowWarning(false)
    clearAllTimers()

    warningTimerRef.current = setTimeout(() => {
      setShowWarning(true)
      startCountdown()

      logoutTimerRef.current = setTimeout(() => {
        setShowWarning(false)
        logout()
      }, LOGOUT_TIME - WARNING_TIME) // 5 more minutes after warning
    }, WARNING_TIME)
  }, [isAuthenticated, logout, clearAllTimers, startCountdown])

  const continueSession = useCallback(() => {
    resetTimer()
  }, [resetTimer])

  const immediateLogout = useCallback(() => {
    setShowWarning(false)
    clearAllTimers()
    logout()
  }, [logout, clearAllTimers])

  useEffect(() => {
    if (!isAuthenticated) {
      clearAllTimers()
      setShowWarning(false)
      return
    }

    resetTimer()

    const handleActivity = () => {
      if (showWarning) return // Don't reset when warning is shown
      resetTimer()
    }

    ACTIVITY_EVENTS.forEach((event) => {
      window.addEventListener(event, handleActivity, { passive: true })
    })

    return () => {
      clearAllTimers()
      ACTIVITY_EVENTS.forEach((event) => {
        window.removeEventListener(event, handleActivity)
      })
    }
  }, [isAuthenticated]) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    showWarning,
    remainingSeconds,
    continueSession,
    immediateLogout,
  }
}
