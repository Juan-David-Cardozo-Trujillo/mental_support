import { Component } from 'react'

class GlobalErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo })
    // In production you'd send to an error reporting service here
    console.error('GlobalErrorBoundary caught:', error, errorInfo)
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null, errorInfo: null })
  }

  handleGoHome = () => {
    window.location.href = '/login'
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="min-h-screen bg-navy-950 flex items-center justify-center p-6"
          role="alert"
          aria-live="assertive"
        >
          <div className="glass-card max-w-lg w-full p-8 text-center animate-fade-in">
            {/* Error icon */}
            <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-red-500/20 flex items-center justify-center">
              <svg
                className="w-10 h-10 text-red-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.07 16.5C2.3 17.333 3.262 19 4.802 19z"
                />
              </svg>
            </div>

            <h1 className="text-2xl font-bold text-white mb-2">Something went wrong</h1>
            <p className="text-slate-400 mb-2">
              We encountered an unexpected error. Your privacy and session data are safe.
            </p>

            {/* Crisis reminder */}
            <div className="bg-teal-500/10 border border-teal-500/20 rounded-xl p-4 mb-6 text-left">
              <p className="text-teal-300 text-sm font-medium mb-1">
                🆘 If you need immediate support:
              </p>
              <p className="text-teal-400 text-sm">
                National crisis line Colombia:{' '}
                <a
                  href="tel:106"
                  className="underline hover:text-teal-200 focus:outline-none focus:ring-1 focus:ring-teal-400 rounded"
                >
                  106
                </a>{' '}
                (24/7, free)
              </p>
            </div>

            {process.env.NODE_ENV === 'development' && this.state.error && (
              <details className="mb-4 text-left">
                <summary className="text-sm text-slate-400 cursor-pointer hover:text-slate-300 mb-2">
                  Technical details (dev mode)
                </summary>
                <pre className="text-xs text-red-400 bg-navy-900/60 p-3 rounded-lg overflow-auto max-h-40">
                  {this.state.error.toString()}
                  {this.state.errorInfo?.componentStack}
                </pre>
              </details>
            )}

            <div className="flex gap-3 justify-center">
              <button
                id="error-retry-btn"
                onClick={this.handleRetry}
                className="btn-primary"
                aria-label="Retry — attempt to reload the current page"
              >
                Try Again
              </button>
              <button
                id="error-home-btn"
                onClick={this.handleGoHome}
                className="btn-secondary"
                aria-label="Return to the login page"
              >
                Go to Login
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

export default GlobalErrorBoundary
