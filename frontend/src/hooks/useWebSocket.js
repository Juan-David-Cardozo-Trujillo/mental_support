import { useEffect, useRef, useCallback, useState } from 'react'

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000, 30000] // exponential backoff caps at 30s
const FALLBACK_POLL_INTERVAL = 30000 // 30 seconds polling fallback

export function useWebSocket({ url, onMessage, onOpen, onClose, enabled = true }) {
  const wsRef = useRef(null)
  const reconnectAttemptRef = useRef(0)
  const reconnectTimerRef = useRef(null)
  const pollTimerRef = useRef(null)
  const messageQueueRef = useRef([])
  const isMountedRef = useRef(true)

  const [isConnected, setIsConnected] = useState(false)
  const [isDegraded, setIsDegraded] = useState(false)
  const [connectionState, setConnectionState] = useState('disconnected') // 'connecting' | 'connected' | 'disconnected' | 'degraded'

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    if (pollTimerRef.current) clearInterval(pollTimerRef.current)
  }, [])

  const flushMessageQueue = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      while (messageQueueRef.current.length > 0) {
        const msg = messageQueueRef.current.shift()
        wsRef.current.send(JSON.stringify(msg))
      }
    }
  }, [])

  const startPollingFallback = useCallback(() => {
    if (!enabled || !onMessage) return
    setIsDegraded(true)
    setConnectionState('degraded')

    // Poll via an HTTP endpoint derived from the WebSocket URL
    // The caller should handle onMessage for both WS and polling data
    pollTimerRef.current = setInterval(() => {
      if (onMessage) {
        onMessage({ type: 'poll_tick', timestamp: Date.now() })
      }
    }, FALLBACK_POLL_INTERVAL)
  }, [enabled, onMessage])

  const connect = useCallback(() => {
    if (!enabled || !url || !isMountedRef.current) return

    try {
      setConnectionState('connecting')
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        if (!isMountedRef.current) return
        reconnectAttemptRef.current = 0
        setIsConnected(true)
        setIsDegraded(false)
        setConnectionState('connected')
        clearTimers()
        flushMessageQueue()
        onOpen?.()
      }

      ws.onmessage = (event) => {
        if (!isMountedRef.current) return
        try {
          const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data
          onMessage?.(data)
        } catch {
          onMessage?.(event.data)
        }
      }

      ws.onerror = () => {
        // Let onclose handle reconnection
      }

      ws.onclose = (event) => {
        if (!isMountedRef.current) return
        setIsConnected(false)
        setConnectionState('disconnected')
        onClose?.(event)

        // Attempt reconnect with exponential backoff
        const attempt = reconnectAttemptRef.current
        const delayMs = RECONNECT_DELAYS[Math.min(attempt, RECONNECT_DELAYS.length - 1)]
        reconnectAttemptRef.current += 1

        // After 5 failed attempts, switch to polling fallback
        if (attempt >= 5) {
          startPollingFallback()
          return
        }

        reconnectTimerRef.current = setTimeout(() => {
          if (isMountedRef.current) connect()
        }, delayMs)
      }
    } catch {
      // WebSocket not available — go to polling fallback immediately
      startPollingFallback()
    }
  }, [url, enabled, onMessage, onOpen, onClose, clearTimers, flushMessageQueue, startPollingFallback])

  const disconnect = useCallback(() => {
    clearTimers()
    if (wsRef.current) {
      wsRef.current.onclose = null // Prevent reconnect
      wsRef.current.close()
      wsRef.current = null
    }
    setIsConnected(false)
    setConnectionState('disconnected')
  }, [clearTimers])

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    } else {
      // Queue the message for when connection is restored
      messageQueueRef.current.push(data)
    }
  }, [])

  useEffect(() => {
    isMountedRef.current = true

    if (enabled && url) {
      connect()
    }

    return () => {
      isMountedRef.current = false
      clearTimers()
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
      }
    }
  }, [url, enabled]) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    isConnected,
    isDegraded,
    connectionState,
    send,
    disconnect,
    reconnect: connect,
  }
}
