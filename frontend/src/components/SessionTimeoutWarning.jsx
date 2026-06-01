import { useEffect, useState } from 'react'

function SessionTimeoutWarning({ remainingSeconds, onContinue, onLogout }) {
  const [show, setShow] = useState(false)

  useEffect(() => {
    // Animate in
    const t = setTimeout(() => setShow(true), 50)
    return () => clearTimeout(t)
  }, [])

  const minutes = Math.floor(remainingSeconds / 60)
  const seconds = remainingSeconds % 60
  const timeStr =
    minutes > 0
      ? `${minutes}:${String(seconds).padStart(2, '0')} minutes`
      : `${seconds} seconds`

  const urgency = remainingSeconds <= 60

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="timeout-title"
      aria-describedby="timeout-description"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onContinue}
        aria-hidden="true"
      />

      {/* Modal */}
      <div
        className={`relative glass-card max-w-md w-full p-8 text-center transition-all duration-300 ${
          show ? 'opacity-100 scale-100' : 'opacity-0 scale-95'
        } ${urgency ? 'border-red-500/40' : 'border-amber-500/30'}`}
      >
        {/* Icon */}
        <div
          className={`w-16 h-16 mx-auto mb-5 rounded-full flex items-center justify-center ${
            urgency ? 'bg-red-500/20' : 'bg-amber-500/20'
          }`}
        >
          <svg
            className={`w-8 h-8 ${urgency ? 'text-red-400' : 'text-amber-400'}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>

        <h2
          id="timeout-title"
          className="text-xl font-bold text-white mb-2"
        >
          Session Expiring Soon
        </h2>

        <p
          id="timeout-description"
          className={`text-base mb-2 ${urgency ? 'text-red-300' : 'text-slate-300'}`}
        >
          Your session will expire in
        </p>

        {/* Countdown */}
        <div
          className={`text-4xl font-bold mb-4 tabular-nums ${
            urgency ? 'text-red-400 animate-pulse' : 'text-amber-400'
          }`}
          role="timer"
          aria-live="polite"
          aria-atomic="true"
        >
          {timeStr}
        </div>

        <p className="text-slate-400 text-sm mb-6">
          For your privacy and security, you will be automatically logged out due to inactivity.
          Any active session data will be preserved.
        </p>

        <div className="flex gap-3">
          <button
            id="timeout-continue-btn"
            onClick={onContinue}
            className="btn-primary flex-1"
            autoFocus
            aria-label="Continue session — reset the inactivity timer"
          >
            Continue Session
          </button>
          <button
            id="timeout-logout-btn"
            onClick={onLogout}
            className="btn-secondary flex-1"
            aria-label="Log out now"
          >
            Log Out
          </button>
        </div>
      </div>
    </div>
  )
}

export default SessionTimeoutWarning
