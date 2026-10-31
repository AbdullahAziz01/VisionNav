"""Session management for single active phone streaming and state isolation.

Provides a shared processing guard that serialises session validation, frame
inference, takeover/release, and pipeline/calibration resets so they cannot
overlap.
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
from typing import Any, Iterator, Optional


class SessionManager:
    """Manages phone sessions to guarantee single-device access and prevent

    different phone sessions from corrupting shared tracker, smoothing,
    and calibration state.

    The processing guard (``_processing_lock``) is a *non-reentrant* lock that
    is held for the duration of a frame inference pass.  Callers that need to
    mutate shared pipeline state (reset, takeover, release) must also acquire
    this lock, which means they block until any in-flight inference finishes,
    and any new inference attempt while they hold it will be rejected with a
    clear 409 response.
    """

    def __init__(self, lease_timeout_s: float | None = None):
        if lease_timeout_s is None:
            raw = os.environ.get("SESSION_TIMEOUT_SECONDS", "30.0")
            try:
                lease_timeout_s = float(raw)
            except ValueError:
                lease_timeout_s = 30.0

        self.lease_timeout_s = max(5.0, float(lease_timeout_s))

        # Protects all session bookkeeping fields below.
        self._lock = threading.Lock()

        # Held for the duration of inference or any state-mutating operation
        # (takeover, release, reset).  Non-reentrant on purpose: a second
        # frame request that arrives while one is being processed will fail
        # to acquire and be rejected immediately.
        self._processing_lock = threading.Lock()

        self.active_session_id: str | None = None
        self.last_heartbeat: float = 0.0
        self.created_at: float = 0.0
        self.device_info: str | None = None

    # ── Internal helpers ─────────────────────────────────────────────────

    def _is_active_unlocked(self, ts: float) -> bool:
        """Check liveness *without* acquiring ``_lock`` (caller already holds it)."""
        if not self.active_session_id:
            return False
        return (ts - self.last_heartbeat) < self.lease_timeout_s

    # ── Public read-only queries ─────────────────────────────────────────

    def is_active(self, now: float | None = None) -> bool:
        """Return True if an active session exists and has not timed out."""
        with self._lock:
            ts = time.monotonic() if now is None else now
            return self._is_active_unlocked(ts)

    @contextlib.contextmanager
    def processing_guard(self, blocking: bool = True, timeout: float = -1) -> Iterator[bool]:
        """Context manager for the shared processing guard.

        Acquires the processing lock (blocking or non-blocking, with optional timeout).
        If acquisition succeeds, yields True, and releases the lock exactly once in finally.
        If acquisition fails, yields False, and DOES NOT release the lock.
        Never suppresses lock ownership errors or any other exception.
        """
        acquired = self._processing_lock.acquire(blocking=blocking, timeout=timeout)
        if not acquired:
            yield False
            return
        try:
            yield True
        finally:
            self._processing_lock.release()

    def is_processing(self) -> bool:
        """Return True if the processing guard is currently held (inference in progress)."""
        if self._processing_lock.acquire(blocking=False):
            self._processing_lock.release()
            return False
        return True

    # ── Session acquire / validate ───────────────────────────────────────

    def acquire_session(
        self,
        session_id: str,
        force: bool = False,
        device_info: str | None = None,
        now: float | None = None,
    ) -> tuple[bool, str, dict[str, Any]]:
        """Acquire or take over the active session.

        Returns (success, message, session_details).
        """
        if not session_id or not session_id.strip():
            return False, "session_id cannot be empty", {}

        session_id = session_id.strip()
        ts = time.monotonic() if now is None else now

        with self._lock:
            active = self._is_active_unlocked(ts)

            if active and self.active_session_id != session_id:
                if not force:
                    remaining = round(self.lease_timeout_s - (ts - self.last_heartbeat), 1)
                    return (
                        False,
                        f"Another phone session ('{self.active_session_id}') is currently active "
                        f"({remaining}s lease remaining). Wait or acquire with force=true.",
                        {
                            "active_session_id": self.active_session_id,
                            "remaining_s": remaining,
                        },
                    )

            # Determine whether temporal state must be reset.
            # Reset is needed when:
            #   1. A *different* session ID is taking over, OR
            #   2. The *same* session ID is reconnecting after its lease expired.
            was_different = self.active_session_id != session_id
            was_expired = not active and self.active_session_id is not None
            reset_needed = was_different or was_expired

            self.active_session_id = session_id
            self.last_heartbeat = ts
            if was_different or was_expired:
                self.created_at = ts
            if device_info:
                self.device_info = device_info

            msg = "Session acquired (taken over)" if (active and was_different and force) else "Session acquired"
            return (
                True,
                msg,
                {
                    "session_id": self.active_session_id,
                    "lease_timeout_s": self.lease_timeout_s,
                    "was_reset_needed": reset_needed,
                },
            )

    def validate_or_auto_acquire(
        self,
        session_id: str | None,
        now: float | None = None,
        *,
        require_explicit: bool = False,
    ) -> tuple[bool, str, bool]:
        """Validate an incoming frame/calibration request.

        Args:
            session_id: The X-Session-ID header value (may be None).
            now: Override for the monotonic clock (testing).
            require_explicit: If True (production), reject requests without
                an explicit session ID even when no session is active.

        Returns:
            (allowed: bool, reason: str, state_reset_required: bool)
        """
        ts = time.monotonic() if now is None else now

        with self._lock:
            active = self._is_active_unlocked(ts)

            # Case 1: No session ID provided by client
            if not session_id or not session_id.strip():
                if require_explicit:
                    return (
                        False,
                        "Production mode requires an explicit X-Session-ID header on every request.",
                        False,
                    )
                if active:
                    return (
                        False,
                        f"Request rejected: An active session ('{self.active_session_id}') is running. "
                        f"Provide matching X-Session-ID header.",
                        False,
                    )
                # No active session: assign anonymous default
                self.active_session_id = "anonymous-default"
                self.last_heartbeat = ts
                self.created_at = ts
                return True, "Auto-acquired default anonymous session", False

            session_id = session_id.strip()

            # Case 2: Matching active session — extend lease
            if active and self.active_session_id == session_id:
                self.last_heartbeat = ts
                return True, "Session matched", False

            # Case 3: No active session or existing session has expired
            if not active:
                # Even the *same* session ID reconnecting after expiry requires
                # a temporal state reset to prevent stale tracker IDs / smoothing.
                was_same_but_expired = self.active_session_id == session_id
                self.active_session_id = session_id
                self.last_heartbeat = ts
                self.created_at = ts
                return True, f"Auto-acquired session '{session_id}'", True

            # Case 4: Different session ID while active session is running
            remaining = round(self.lease_timeout_s - (ts - self.last_heartbeat), 1)
            return (
                False,
                f"Session conflict: Request session '{session_id}' conflicts with active session "
                f"'{self.active_session_id}' ({remaining}s lease remaining).",
                False,
            )

    # ── Lease refresh ────────────────────────────────────────────────────

    def refresh_lease(self, session_id: str, now: float | None = None) -> None:
        """Extend the lease for the given session after processing completes."""
        ts = time.monotonic() if now is None else now
        with self._lock:
            if self.active_session_id == session_id:
                self.last_heartbeat = ts

    # ── Release ──────────────────────────────────────────────────────────

    def release_session(self, session_id: str) -> bool:
        """Explicitly release the session."""
        with self._lock:
            if self.active_session_id and self.active_session_id == session_id.strip():
                self.active_session_id = None
                self.last_heartbeat = 0.0
                self.created_at = 0.0
                self.device_info = None
                return True
            return False

    # ── Status ───────────────────────────────────────────────────────────

    def status(self, now: float | None = None) -> dict[str, Any]:
        """Return the current session status."""
        ts = time.monotonic() if now is None else now
        with self._lock:
            active = self._is_active_unlocked(ts)
            remaining = (
                max(0.0, round(self.lease_timeout_s - (ts - self.last_heartbeat), 1))
                if active
                else 0.0
            )
            return {
                "active": active,
                "active_session_id": self.active_session_id if active else None,
                "remaining_seconds": remaining,
                "lease_timeout_seconds": self.lease_timeout_s,
                "device_info": self.device_info if active else None,
                "processing": self.is_processing(),
            }
