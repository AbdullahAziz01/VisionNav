"""Match OCR-style destination text against known Metrobus routes."""

from __future__ import annotations

import json
import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_ROUTES_PATH = Path(__file__).with_name("routes.json")
_WHITESPACE_RE = re.compile(r"\s+")

# Exact (normalized or compact) hits outrank a looser token-sequence hit.
_EXACT_CONFIDENCE = 1.0
_LOOSE_CONFIDENCE = 0.7

_WINDOW_SIZE = 5
_MIN_STABLE_HITS = 3


@dataclass(frozen=True)
class RouteMatch:
    route_line: str
    route_destination: str
    direction_id: str
    confidence: float
    raw_text: str


@dataclass(frozen=True)
class _AliasEntry:
    route_line: str
    route_destination: str
    direction_id: str
    alias_norm: str
    alias_compact: str
    alias_tokens: tuple[str, ...]


def normalize_text(raw_text: str) -> str:
    """Uppercase, strip, map hyphens to spaces, collapse repeated whitespace."""
    text = raw_text.upper().replace("-", " ").strip()
    return _WHITESPACE_RE.sub(" ", text)


def compact_text(raw_text: str) -> str:
    return normalize_text(raw_text).replace(" ", "")


def _tokens(raw_text: str) -> tuple[str, ...]:
    norm = normalize_text(raw_text)
    return tuple(norm.split()) if norm else ()


def _contains_token_sequence(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    n = len(needle)
    return any(haystack[i : i + n] == needle for i in range(len(haystack) - n + 1))


def _load_alias_index(path: Path = _ROUTES_PATH) -> tuple[_AliasEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries: list[_AliasEntry] = []
    for route in payload.get("routes", []):
        route_line = str(route["display_name"])
        for direction in route.get("directions", []):
            destination = str(direction["destination"])
            direction_id = str(direction["id"])
            for alias in direction.get("destination_aliases", []):
                entries.append(
                    _AliasEntry(
                        route_line=route_line,
                        route_destination=destination,
                        direction_id=direction_id,
                        alias_norm=normalize_text(alias),
                        alias_compact=compact_text(alias),
                        alias_tokens=_tokens(alias),
                    )
                )
    return tuple(entries)


_ALIAS_INDEX = _load_alias_index()


def _score_alias(raw_text: str, entry: _AliasEntry) -> float | None:
    """Return confidence if *raw_text* clearly matches this alias, else None."""
    norm = normalize_text(raw_text)
    compact = compact_text(raw_text)
    if not compact:
        return None

    if norm == entry.alias_norm or compact == entry.alias_compact:
        return _EXACT_CONFIDENCE

    raw_tokens = _tokens(raw_text)
    if _contains_token_sequence(raw_tokens, entry.alias_tokens):
        return _LOOSE_CONFIDENCE

    return None


def match_route_text(raw_text: str | None) -> RouteMatch | None:
    """Return a match only when the text is a clear known destination."""
    if raw_text is None:
        return None
    if not compact_text(raw_text):
        return None

    best: tuple[float, int, RouteMatch] | None = None
    for entry in _ALIAS_INDEX:
        score = _score_alias(raw_text, entry)
        if score is None:
            continue
        # Prefer higher confidence, then the longer (more specific) alias.
        key = (score, len(entry.alias_compact))
        candidate = RouteMatch(
            route_line=entry.route_line,
            route_destination=entry.route_destination,
            direction_id=entry.direction_id,
            confidence=score,
            raw_text=raw_text,
        )
        if best is None or key > (best[0], best[1]):
            best = (score, len(entry.alias_compact), candidate)

    return None if best is None else best[2]


class RouteStabilityTracker:
    """Require repeated agreement on route_line + direction_id per bus track."""

    def __init__(
        self,
        window_size: int = _WINDOW_SIZE,
        min_hits: int = _MIN_STABLE_HITS,
    ):
        if min_hits < 1:
            raise ValueError("min_hits must be at least 1")
        if window_size < min_hits:
            raise ValueError("window_size must be >= min_hits")
        self.window_size = window_size
        self.min_hits = min_hits
        self._history: dict[int, deque[tuple[str, str] | None]] = {}
        self._last_seen: dict[int, float] = {}
        self._latest_match: dict[int, dict[tuple[str, str], RouteMatch]] = {}

    def observe(self, track_id: int, match: RouteMatch | None) -> RouteMatch | None:
        """Record one observation. Return the match only once it is stable."""
        now = time.monotonic()
        history = self._history.setdefault(track_id, deque(maxlen=self.window_size))
        latest = self._latest_match.setdefault(track_id, {})
        self._last_seen[track_id] = now

        if match is None:
            history.append(None)
        else:
            key = (match.route_line, match.direction_id)
            history.append(key)
            latest[key] = match

        return self.get_stable(track_id)

    def get_stable(self, track_id: int) -> RouteMatch | None:
        history = self._history.get(track_id)
        if not history:
            return None

        counts: dict[tuple[str, str], int] = {}
        for item in history:
            if item is None:
                continue
            counts[item] = counts.get(item, 0) + 1

        winner: tuple[str, str] | None = None
        winner_hits = 0
        for key, hits in counts.items():
            if hits >= self.min_hits and hits > winner_hits:
                winner = key
                winner_hits = hits

        if winner is None:
            return None
        return self._latest_match.get(track_id, {}).get(winner)

    def clear_inactive(
        self,
        active_track_ids: Iterable[int] | None = None,
        max_age_s: float | None = None,
        now: float | None = None,
    ) -> None:
        """Drop tracks missing from *active_track_ids* and/or older than *max_age_s*."""
        if active_track_ids is not None:
            active = set(active_track_ids)
            for track_id in list(self._history):
                if track_id not in active:
                    self._forget(track_id)

        if max_age_s is None:
            return
        clock = time.monotonic() if now is None else now
        for track_id, seen_at in list(self._last_seen.items()):
            if clock - seen_at > max_age_s:
                self._forget(track_id)

    def _forget(self, track_id: int) -> None:
        self._history.pop(track_id, None)
        self._last_seen.pop(track_id, None)
        self._latest_match.pop(track_id, None)
