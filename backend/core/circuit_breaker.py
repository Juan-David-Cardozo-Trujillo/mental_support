"""
Circuit breaker implementation for external service calls.

States:
  CLOSED   → normal operation; failures are counted
  OPEN     → circuit tripped; requests fail-fast with cached/fallback response
  HALF_OPEN→ one probe request allowed; success closes, failure reopens

Configuration:
  FAILURE_THRESHOLD = 5  failures within FAILURE_WINDOW seconds → trip
  FAILURE_WINDOW    = 30 seconds
  RECOVERY_TIMEOUT  = 60 seconds in OPEN state before attempting HALF_OPEN

Usage::

    @circuit_breaker("sso_service")
    async def call_sso(url: str) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.get(url)
            return r.json()
"""
from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


FAILURE_THRESHOLD: int = 5
FAILURE_WINDOW: float = 30.0   # seconds
RECOVERY_TIMEOUT: float = 60.0  # seconds in OPEN before trying HALF_OPEN


@dataclass
class _CircuitData:
    state: CircuitState = CircuitState.CLOSED
    failure_timestamps: deque = field(default_factory=lambda: deque())
    opened_at: float = 0.0
    last_fallback: Any = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)


# Global registry keyed by service_name
_circuits: dict[str, _CircuitData] = defaultdict(_CircuitData)


class CircuitOpenError(Exception):
    """Raised when a circuit is open and the call is rejected."""


def _prune_old_failures(data: _CircuitData) -> None:
    """Remove failure timestamps older than the sliding window."""
    cutoff = time.monotonic() - FAILURE_WINDOW
    while data.failure_timestamps and data.failure_timestamps[0] < cutoff:
        data.failure_timestamps.popleft()


async def _record_failure(data: _CircuitData) -> None:
    async with data._lock:
        data.failure_timestamps.append(time.monotonic())
        _prune_old_failures(data)
        if len(data.failure_timestamps) >= FAILURE_THRESHOLD:
            if data.state != CircuitState.OPEN:
                logger.warning(
                    "Circuit breaker OPENED after %d failures in %.0fs window",
                    FAILURE_THRESHOLD,
                    FAILURE_WINDOW,
                )
            data.state = CircuitState.OPEN
            data.opened_at = time.monotonic()


async def _record_success(data: _CircuitData) -> None:
    async with data._lock:
        data.failure_timestamps.clear()
        if data.state != CircuitState.CLOSED:
            logger.info("Circuit breaker CLOSED after successful probe")
        data.state = CircuitState.CLOSED


async def _check_circuit(data: _CircuitData) -> None:
    """
    Raise CircuitOpenError if the circuit is open.
    Transition to HALF_OPEN if the recovery timeout has passed.
    """
    async with data._lock:
        if data.state == CircuitState.OPEN:
            elapsed = time.monotonic() - data.opened_at
            if elapsed >= RECOVERY_TIMEOUT:
                logger.info("Circuit breaker entering HALF_OPEN for probe")
                data.state = CircuitState.HALF_OPEN
            else:
                raise CircuitOpenError(
                    f"Circuit is OPEN ({elapsed:.0f}s / {RECOVERY_TIMEOUT:.0f}s recovery)"
                )


def circuit_breaker(
    service_name: str,
    fallback: Any = None,
) -> Callable:
    """
    Decorator that wraps an async function with circuit-breaker logic.

    Args:
        service_name: Logical name for the protected service (used as registry key).
        fallback: Value to return when the circuit is OPEN (instead of raising).
                  If None, raises CircuitOpenError.

    Example::

        @circuit_breaker("redis_cache", fallback={})
        async def get_from_cache(key: str) -> dict:
            ...
    """
    def decorator(func: Callable[..., Coroutine]) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            data = _circuits[service_name]
            try:
                await _check_circuit(data)
            except CircuitOpenError:
                logger.debug("Circuit %s is OPEN — returning fallback", service_name)
                if fallback is not None:
                    return fallback
                raise

            try:
                result = await func(*args, **kwargs)
                await _record_success(data)
                # Cache the last successful result as potential fallback
                data.last_fallback = result
                return result
            except Exception as exc:
                logger.warning(
                    "Circuit %s recorded failure: %s: %s",
                    service_name,
                    type(exc).__name__,
                    exc,
                )
                await _record_failure(data)
                raise

        return wrapper
    return decorator


def get_circuit_status(service_name: str) -> dict[str, Any]:
    """Return current state info for a named circuit (used by health checks)."""
    data = _circuits.get(service_name)
    if data is None:
        return {"service": service_name, "state": "UNKNOWN", "failures": 0}
    _prune_old_failures(data)
    return {
        "service": service_name,
        "state": data.state.name,
        "recent_failures": len(data.failure_timestamps),
        "threshold": FAILURE_THRESHOLD,
    }
