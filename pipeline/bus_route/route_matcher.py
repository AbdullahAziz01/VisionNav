"""Match OCR text to Metrobus and Islamabad feeder routes.

Route codes use bounded patterns, so FR-1 is not read out of FR-10 and a
suffix stays attached to its own route. Destination words are used only when
they identify one route. Shared names such as PIMS, Barakahu, Tramri, Khanna
Pul, and Golra Mor do not pick a route by themselves.
"""

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
_CANON_CODE_RE = re.compile(r"^(FRG|EXP|FR)-(\d+)([A-Z])?$")
_CODE_RE = re.compile(
    r"(?<![A-Z0-9])"
    r"(?P<prefix>FRG|EXP|FR)"
    r"(?P<sep>[\s-]*)"
    r"(?P<digits>\d+)"
    r"(?:[\s-]*(?P<suffix>[A-Z]))?"
    r"(?![A-Z0-9])"
)

_EXACT_CONFIDENCE = 1.0
_LOOSE_CONFIDENCE = 0.7

_WINDOW_SIZE = 5
_MIN_STABLE_HITS = 3


@dataclass(frozen=True)
class RouteMatch:
    route_line: str
    route_destination: str | None
    direction_id: str | None
    confidence: float
    raw_text: str
    route_code: str | None = None
    tts_message: str | None = None

    @property
    def direction_known(self) -> bool:
        return self.direction_id is not None


@dataclass(frozen=True)
class RouteInterpretation:
    """Production reading of one bus crop's OCR evidence."""

    status: str
    match: RouteMatch | None = None
    detail: str = ""

    @property
    def ambiguous(self) -> bool:
        return self.status in {"ambiguous", "conflict"}

    @property
    def route_code(self) -> str | None:
        return None if self.match is None else self.match.route_code

    @property
    def direction_known(self) -> bool:
        return self.match is not None and self.match.direction_id is not None

    @property
    def speech(self) -> str | None:
        return None if self.match is None else self.match.tts_message


@dataclass(frozen=True)
class _Direction:
    direction_id: str
    destination: str
    tts_message: str
    compacts: frozenset[str]


@dataclass(frozen=True)
class _Route:
    route_id: str
    route_code: str | None
    route_line: str
    route_only_tts: str
    code_prefix: str | None
    code_number: int | None
    code_width: int
    code_suffix: str
    directions: tuple[_Direction, ...]
    compacts: frozenset[str]


@dataclass(frozen=True)
class _Alias:
    route_id: str
    direction_id: str
    compact: str
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class _Hit:
    route_id: str
    direction_id: str
    compact: str
    span: tuple[int, int]


def normalize_text(raw_text: str) -> str:
    """Uppercase, strip, map hyphens to spaces, collapse repeated whitespace."""
    text = raw_text.upper().replace("-", " ").strip()
    return _WHITESPACE_RE.sub(" ", text)


def compact_text(raw_text: str) -> str:
    return normalize_text(raw_text).replace(" ", "")


def _tokens(raw_text: str) -> tuple[str, ...]:
    norm = normalize_text(raw_text)
    return tuple(norm.split()) if norm else ()


def _parse_canonical_code(code: str) -> tuple[str, int, int, str] | None:
    match = _CANON_CODE_RE.fullmatch(code.strip().upper())
    if match is None:
        return None
    digits = match.group(2)
    return match.group(1), int(digits), len(digits), match.group(3) or ""


def _load_database(path: Path = _ROUTES_PATH):
    payload = json.loads(path.read_text(encoding="utf-8"))
    routes: list[_Route] = []
    aliases: list[_Alias] = []
    substations: list[tuple[str, ...]] = []
    seen_stops: set[tuple[str, ...]] = set()

    for raw in payload.get("routes", []):
        directions: list[_Direction] = []
        route_compacts: set[str] = set()
        for direction in raw.get("directions", []):
            dir_compacts: set[str] = set()
            for alias in direction.get("destination_aliases", []):
                tokens = _tokens(str(alias))
                compact = compact_text(str(alias))
                if not tokens or not compact:
                    continue
                dir_compacts.add(compact)
                route_compacts.add(compact)
                aliases.append(
                    _Alias(
                        route_id=str(raw["id"]),
                        direction_id=str(direction["id"]),
                        compact=compact,
                        tokens=tokens,
                    )
                )
            directions.append(
                _Direction(
                    direction_id=str(direction["id"]),
                    destination=str(direction["destination"]),
                    tts_message=str(direction["tts_message"]),
                    compacts=frozenset(dir_compacts),
                )
            )

        if raw.get("substations_available") and raw.get("substations"):
            for stop in raw["substations"]:
                phrase = _tokens(str(stop))
                if phrase and phrase not in seen_stops:
                    seen_stops.add(phrase)
                    substations.append(phrase)

        code = raw.get("route_code")
        parsed = _parse_canonical_code(str(code)) if code else None
        if code and parsed is None:
            raise ValueError(f"Unrecognized route code: {code}")
        routes.append(
            _Route(
                route_id=str(raw["id"]),
                route_code=str(code) if code else None,
                route_line=str(raw["display_name"]),
                route_only_tts=str(raw["route_only_tts"]),
                code_prefix=None if parsed is None else parsed[0],
                code_number=None if parsed is None else parsed[1],
                code_width=0 if parsed is None else parsed[2],
                code_suffix="" if parsed is None else parsed[3],
                directions=tuple(directions),
                compacts=frozenset(route_compacts),
            )
        )

    code_index: dict[tuple[str, int, str], tuple[_Route, ...]] = {}
    grouped: dict[tuple[str, int, str], list[_Route]] = {}
    for route in routes:
        if route.code_prefix is None or route.code_number is None:
            continue
        key = (route.code_prefix, route.code_number, route.code_suffix)
        grouped.setdefault(key, []).append(route)
    for key, group in grouped.items():
        code_index[key] = tuple(group)

    return tuple(routes), tuple(aliases), tuple(substations), code_index


_ROUTES, _ALIASES, _SUBSTATIONS, _CODE_INDEX = _load_database()


def _resolve_code(
    prefix: str,
    digits: str,
    suffix: str,
    had_separator: bool,
) -> tuple[str, tuple[_Route, ...]]:
    """Map one code token to a route, or to the routes it cannot choose between.

    A glued code with no leading zero is ambiguous when both FR-4 and FR-04
    exist: "FR4" must not choose. "FR-4" and "FR 04" stay distinct.
    """
    key = (prefix.upper(), int(digits), (suffix or "").upper())
    routes = _CODE_INDEX.get(key, ())
    if not routes:
        return "none", ()

    if len(digits) > 1 and digits.startswith("0"):
        padded = tuple(route for route in routes if route.code_width == len(digits))
        if len(padded) == 1:
            return "matched", padded
        if len(padded) > 1:
            return "ambiguous", padded
        return "none", ()

    if not had_separator and len(routes) > 1:
        return "ambiguous", routes

    exact_width = tuple(route for route in routes if route.code_width == len(digits))
    if len(exact_width) == 1:
        return "matched", exact_width
    if len(exact_width) > 1:
        return "ambiguous", exact_width
    if len(routes) == 1:
        return "matched", routes
    return "ambiguous", routes


def _codes_in(text: str) -> tuple[list[_Route], list[tuple[_Route, ...]]]:
    matched: list[_Route] = []
    ambiguous: list[tuple[_Route, ...]] = []
    for found in _CODE_RE.finditer(text.upper()):
        status, routes = _resolve_code(
            found.group("prefix"),
            found.group("digits"),
            found.group("suffix") or "",
            had_separator=bool(found.group("sep")),
        )
        if status == "matched":
            matched.append(routes[0])
        elif status == "ambiguous":
            ambiguous.append(routes)
    return matched, ambiguous


def _find_hits(tokens: tuple[str, ...]) -> list[_Hit]:
    hits: list[_Hit] = []
    if not tokens:
        return hits
    seen: set[tuple[str, str, str, tuple[int, int]]] = set()
    for alias in _ALIASES:
        spans: set[tuple[int, int]] = set()
        width = len(alias.tokens)
        if width and width <= len(tokens):
            for index in range(len(tokens) - width + 1):
                if tokens[index : index + width] == alias.tokens:
                    spans.add((index, index + width))
        target = alias.compact
        for start in range(len(tokens)):
            compact = ""
            for end in range(start, len(tokens)):
                compact += tokens[end]
                if len(compact) > len(target):
                    break
                if compact == target:
                    spans.add((start, end + 1))
        for span in spans:
            key = (alias.route_id, alias.direction_id, alias.compact, span)
            if key in seen:
                continue
            seen.add(key)
            hits.append(
                _Hit(
                    route_id=alias.route_id,
                    direction_id=alias.direction_id,
                    compact=alias.compact,
                    span=span,
                )
            )
    return hits


def _drop_subsumed(hits: list[_Hit]) -> list[_Hit]:
    """Drop a short alias whose span sits inside a longer matched alias."""
    kept: list[_Hit] = []
    for hit in hits:
        hit_len = hit.span[1] - hit.span[0]
        covered = False
        for other in hits:
            if other.span == hit.span:
                continue
            other_len = other.span[1] - other.span[0]
            if (
                other_len > hit_len
                and other.span[0] <= hit.span[0]
                and other.span[1] >= hit.span[1]
            ):
                covered = True
                break
        if not covered:
            kept.append(hit)
    return kept


def _substation_spans(tokens: tuple[str, ...]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for phrase in _SUBSTATIONS:
        width = len(phrase)
        if not width or width > len(tokens):
            continue
        for index in range(len(tokens) - width + 1):
            if tokens[index : index + width] == phrase:
                spans.append((index, index + width))
    return spans


def _drop_substation_inners(hits: list[_Hit], tokens: tuple[str, ...]) -> list[_Hit]:
    """Ignore a destination word that is only part of a longer listed substation.

    G-11 Markaz is a stop, not the G-11 destination. A phrase that equals a
    destination alias is kept.
    """
    containers = _substation_spans(tokens)
    if not containers:
        return hits
    kept: list[_Hit] = []
    for hit in hits:
        hit_len = hit.span[1] - hit.span[0]
        covered = False
        for start, end in containers:
            if (end - start) > hit_len and start <= hit.span[0] and end >= hit.span[1]:
                covered = True
                break
        if not covered:
            kept.append(hit)
    return kept


def _prepare_hits(tokens: tuple[str, ...]) -> list[_Hit]:
    return _drop_substation_inners(_drop_subsumed(_find_hits(tokens)), tokens)


def _candidate_routes(hits: list[_Hit]) -> list[_Route]:
    seen = {hit.compact for hit in hits}
    if not seen:
        return []
    return [route for route in _ROUTES if seen <= route.compacts]


def _directions_for(route: _Route, hits: list[_Hit]) -> list[_Direction]:
    found: list[_Direction] = []
    for direction in route.directions:
        if any(
            hit.route_id == route.route_id and hit.direction_id == direction.direction_id
            for hit in hits
        ):
            found.append(direction)
    return found


def _confidence(tokens: tuple[str, ...], hits: list[_Hit], from_code: bool) -> float:
    if from_code:
        return _EXACT_CONFIDENCE
    if tokens and any(hit.span == (0, len(tokens)) for hit in hits):
        return _EXACT_CONFIDENCE
    return _LOOSE_CONFIDENCE


def _full_match(
    route: _Route,
    direction: _Direction,
    confidence: float,
    evidence: str,
) -> RouteMatch:
    return RouteMatch(
        route_line=route.route_line,
        route_destination=direction.destination,
        direction_id=direction.direction_id,
        confidence=confidence,
        raw_text=evidence,
        route_code=route.route_code,
        tts_message=direction.tts_message,
    )


def _route_only_match(route: _Route, confidence: float, evidence: str) -> RouteMatch:
    return RouteMatch(
        route_line=route.route_line,
        route_destination=None,
        direction_id=None,
        confidence=confidence,
        raw_text=evidence,
        route_code=route.route_code,
        tts_message=route.route_only_tts,
    )


def _matched(match: RouteMatch, detail: str) -> RouteInterpretation:
    return RouteInterpretation(status="matched", match=match, detail=detail)


def _decide(
    route: _Route,
    hits: list[_Hit],
    tokens: tuple[str, ...],
    evidence: str,
    from_code: bool,
) -> RouteInterpretation:
    seen = {hit.compact for hit in hits}
    if seen - route.compacts:
        return RouteInterpretation(
            status="conflict",
            detail="Destination evidence conflicts with the route code.",
        )

    directions = _directions_for(route, hits)
    confidence = _confidence(tokens, hits, from_code)
    if len(directions) == 1:
        detail = (
            "Route code and destination agree."
            if from_code
            else "Destination identifies one route and direction."
        )
        return _matched(_full_match(route, directions[0], confidence, evidence), detail)
    if len(directions) >= 2:
        return _matched(
            _route_only_match(route, confidence, evidence),
            "Both corridor endpoints are visible, so direction is not assigned.",
        )
    if from_code:
        return _matched(
            _route_only_match(route, _EXACT_CONFIDENCE, evidence),
            "Route code recognized. Direction could not be read.",
        )
    return RouteInterpretation(status="unidentified", detail="No route evidence.")


def _evidence(texts: Iterable[str | None]) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if text is None:
            continue
        cleaned = str(text).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        parts.append(cleaned)
    return " ".join(parts)


def interpret_ocr_evidence(texts: Iterable[str | None] | None) -> RouteInterpretation:
    """Read every OCR string from one bus crop with the production rules."""
    evidence = _evidence(texts or [])
    if not evidence or not compact_text(evidence):
        return RouteInterpretation(status="unidentified", detail="No route evidence.")

    tokens = _tokens(evidence)
    hits = _prepare_hits(tokens)
    matched_routes, ambiguous_groups = _codes_in(evidence)
    unique = {route.route_id: route for route in matched_routes}

    if len(unique) > 1:
        return RouteInterpretation(status="conflict", detail="Conflicting route codes.")
    if len(unique) == 1:
        route = next(iter(unique.values()))
        for group in ambiguous_groups:
            if route.route_id not in {item.route_id for item in group}:
                return RouteInterpretation(
                    status="conflict",
                    detail="Conflicting route codes.",
                )
        return _decide(route, hits, tokens, evidence, from_code=True)
    if ambiguous_groups:
        return RouteInterpretation(status="ambiguous", detail="Route code is ambiguous.")
    if not hits:
        return RouteInterpretation(status="unidentified", detail="No route evidence.")

    candidates = _candidate_routes(hits)
    if len(candidates) == 1:
        return _decide(candidates[0], hits, tokens, evidence, from_code=False)
    if not candidates:
        return RouteInterpretation(
            status="conflict",
            detail="Destination evidence does not fit one route.",
        )
    return RouteInterpretation(
        status="ambiguous",
        detail="Destination text is shared by more than one route.",
    )


def match_route_text(raw_text: str | None) -> RouteMatch | None:
    """Return a match when the text identifies one route. Ambiguity returns None."""
    if raw_text is None:
        return None
    return interpret_ocr_evidence([raw_text]).match


def format_route_interpretation(result: RouteInterpretation) -> str:
    """Report code, direction, ambiguity, and the speech text for one reading."""
    if result.match is None:
        code = "(none)"
        route = "(none)"
        direction = "(none)"
        known = "no"
        speech = "(none)"
    else:
        code = result.match.route_code or "(none)"
        route = result.match.route_line
        if result.match.direction_id is None:
            direction = "(unknown)"
            known = "no"
        else:
            destination = result.match.route_destination or result.match.direction_id
            direction = f"{result.match.direction_id} ({destination})"
            known = "yes"
        speech = result.speech or "(none)"
    lines = [
        f"Matched code: {code}",
        f"Route: {route}",
        f"Direction: {direction}",
        f"Direction known: {known}",
        f"Ambiguous: {'yes' if result.ambiguous else 'no'}",
        f"Speech: {speech}",
    ]
    if result.detail:
        lines.append(f"Detail: {result.detail}")
    return "\n".join(lines)


def _identity(match: RouteMatch) -> tuple[str, str]:
    """Stability key: route code (or line) plus direction once it is known.

    An empty direction means the route is known and the direction is not.
    A later direction is a different identity, and an old direction leaves
    the window instead of sticking to the track.
    """
    return (match.route_code or match.route_line, match.direction_id or "")


class RouteStabilityTracker:
    """Require repeated agreement on route code and, when known, direction."""

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
            key = _identity(match)
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
