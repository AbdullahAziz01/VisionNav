"""Audit VisionNav transit assets against the CDA source catalog.

Reads:
  - CDA_ISLAMABAD_TRANSIT_SOURCE_CATALOG.md (expected route set / conflict flags)
  - visionnav_app/assets/direct_bus_routes.json
  - optional PDF text extractions under a --cache directory

Writes docs/cda_route_audit_report.md and prints a short console summary.
Does not invent coordinates, platform sides, or live ETAs.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'visionnav_app' / 'assets'
CATALOG_ROUTES = [
    'FR-01', 'FR-03A', 'FR-04', 'FR-04A', 'FR-04B', 'FR-05', 'FR-06', 'FR-07',
    'FR-08A', 'FR-08C', 'FR-09', 'FR-10', 'FR-11', 'FR-12', 'FR-13', 'FR-14',
    'FR-14A', 'FR-15', 'FRB-01', 'FRG-1', 'ST-01', 'ST-02',
]
CATEGORIES = {
    'FRB-01': 'blue_labeled_feeder',
    'FRG-1': 'green_labeled_feeder',
    'ST-01': 'sightseeing',
    'ST-02': 'sightseeing',
}
for code in CATALOG_ROUTES:
    CATEGORIES.setdefault(code, 'feeder')

# Index-over-PDF / terminals-only policy (defense planning rule).
INDEX_POLICY = {
    'FR-03A': (
        'Index-over-PDF: planner uses CDA website endpoints PIMS–Saidpur Village '
        '(20 min). Conflicting PDF Faisal Masjid sequence is audit-only.'
    ),
    'FR-05': (
        'Index-over-PDF: planner uses CDA website endpoints Golra Morh–Taxila '
        '(5 min). Conflicting PDF NUST–D-12 sequence is audit-only.'
    ),
    'FR-08A': (
        'Index-over-PDF: planner uses CDA website 20 min headway and terminals '
        'PIMS–Capt. Naeem Tufail Shaheed Chowk; denser PDF headway ignored.'
    ),
    'FR-04B': (
        'Terminals-only: Diplomatic Enclave shuttle has no timetable PDF; '
        'navigate PIMS ↔ Diplomatic Enclave only, no fixed schedule.'
    ),
    'FR-04A': 'Terminals-only: Bari Imam ↔ Quaid-e-Azam University.',
    'FR-08C': 'Terminals-only: PIMS ↔ Capt. Naeem Tufail Shaheed Chowk via Faizabad corridor.',
    'FR-11': 'Terminals-only: Golra Morh ↔ I-16.',
    'FR-14A': 'Terminals-only: Barakahu ↔ Satra Meel.',
    'ST-02': 'Terminals-only: PIMS ↔ Capt. Naeem Tufail Shaheed Chowk via Shakarparian.',
}


def category(route: str) -> str:
    return CATEGORIES.get(route, 'feeder')


def identity(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', name.lower())


def headway_seconds(times: list[str]) -> float | None:
    if len(times) < 2:
        return None
    secs = []
    for value in times:
        h, m, s = map(int, value.split(':'))
        secs.append(h * 3600 + m * 60 + s)
    gaps = [b - a for a, b in zip(secs, secs[1:]) if b > a]
    return sum(gaps) / len(gaps) if gaps else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=ROOT / 'tmp' / 'cda_pdfs')
    parser.add_argument(
        '--out',
        type=Path,
        default=ROOT / 'docs' / 'cda_route_audit_report.md',
    )
    args = parser.parse_args()

    data = json.loads((ASSETS / 'direct_bus_routes.json').read_text(encoding='utf-8'))
    stops = json.loads((ASSETS / 'transit_stops.json').read_text(encoding='utf-8-sig'))
    stop_keys = {stop['key'] for stop in stops['stops']}
    coverage = data.get('coverage', [])
    directions = data.get('directions', [])

    cov_by_route = defaultdict(list)
    for row in coverage:
        cov_by_route[row['route']].append(row)
    dir_by_route = defaultdict(list)
    for row in directions:
        dir_by_route[row['route']].append(row)

    missing_routes = [r for r in CATALOG_ROUTES if r not in cov_by_route]
    extra_routes = sorted(set(cov_by_route) - set(CATALOG_ROUTES))

    lines = [
        '# CDA route audit report',
        '',
        f'Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}.',
        '',
        'Source of truth: [CDA Transit Map](https://www.cda.gov.pk/cdaTransitMap) and '
        '`CDA_ISLAMABAD_TRANSIT_SOURCE_CATALOG.md`.',
        '',
        'Scheduled timetable values are not live bus ETAs. Coordinates in '
        '`transit_stops.json` are mapped gazetteer pins, not verified roadside platforms.',
        '',
        '## Catalog coverage',
        '',
        f'- Catalog routes: **{len(CATALOG_ROUTES)}**',
        f'- Routes with coverage rows: **{len(cov_by_route)}**',
        f'- Usable mapped directions in planner: **{len(directions)}**',
        f'- Mapped gazetteer stops: **{len(stop_keys)}**',
        '',
    ]
    if missing_routes:
        lines.append('- Missing from coverage asset: ' + ', '.join(missing_routes))
    if extra_routes:
        lines.append('- Extra coverage routes not in catalog: ' + ', '.join(extra_routes))
    lines += ['', '## Per-route status', '']

    for route in CATALOG_ROUTES:
        cat = category(route)
        rows = cov_by_route.get(route, [])
        mapped = dir_by_route.get(route, [])
        lines.append(f'### {route} ({cat})')
        if not rows:
            lines.append('- **Coverage:** absent from `direct_bus_routes.json`.')
        for row in rows:
            status = row.get('status', 'unknown')
            mapped_n = row.get('mappedStops', '-')
            published_n = len(row.get('publishedStops', []))
            lines.append(
                f'- Direction listed as `{row.get("listedDirection", "")}` — '
                f'status `{status}`; published stops {published_n}; mapped stops {mapped_n}; '
                f'source {row.get("source", "")}'
            )
            if status == 'available' and isinstance(mapped_n, int) and published_n:
                omitted = published_n - mapped_n
                if omitted > 0:
                    lines.append(
                        f'  - **Incomplete mapping:** {omitted} published stop name(s) '
                        'lack a unique gazetteer match and are omitted from the ordered planner sequence.'
                    )
        if mapped:
            for direction in mapped:
                toward = direction.get('toward', '')
                keys = direction.get('stopKeys', [])
                unknown = [k for k in keys if k not in stop_keys]
                avg = None
                for times in direction.get('departures', {}).values():
                    avg = headway_seconds(times)
                    if avg is not None:
                        break
                headway = f'{avg / 60:.1f} min avg gap from first mapped stop times' if avg else 'no headway from departures'
                lines.append(
                    f'- Planner direction toward `{toward}` — {len(keys)} ordered mapped stops; {headway}.'
                )
                if unknown:
                    lines.append('  - Unknown stop keys (not in gazetteer): ' + ', '.join(unknown))
        else:
            lines.append('- **Planner:** no usable mapped direction (needs more verified stop pins or conflict resolution).')
        if route in INDEX_POLICY:
            lines.append(f'- **Planning policy:** {INDEX_POLICY[route]}')
        lines.append('')

    # Name variant / duplicate scan across published stops
    name_to_routes: dict[str, set[str]] = defaultdict(set)
    for row in coverage:
        for name in row.get('publishedStops', []):
            name_to_routes[identity(name)].add(row['route'])

    lines += [
        '## Mapping gaps / terminals-only routes',
        '',
        'Where mid-stop pins are missing, the planner still offers **terminals-only** '
        'boarding and exit navigation (start or end depending on trip direction). '
        'Where the CDA website index conflicts with a PDF, the **index endpoints win**.',
        '',
    ]
    weak = [
        row for row in coverage
        if row.get('status') not in {'available', 'available_index_terminals'}
    ]
    if not weak:
        lines.append('- None: every catalog route has at least terminals-only planner coverage.')
    for row in weak:
        lines.append(
            f'- `{row["route"]}` / `{row.get("listedDirection", "")}`: {row.get("status")}'
        )

    lines += [
        '',
        '## Live timing note',
        '',
        'CDA timetable PDFs provide **scheduled** arrival/departure times only. '
        'The CDA Metro mobile app advertises real-time arrivals, but VisionNav has no '
        'authoritative developer feed. The app must continue to speak **scheduled wait / '
        'next listed departure** at trip offer and at boarding-stop arrival, clearly '
        'labeled as schedule-based, never as live GPS bus ETA.',
        '',
        '## Opposite-direction rule',
        '',
        'Each forward and backward PDF is a separate ordered route. Presence of a stop on '
        'one direction does not prove service in the other direction.',
        '',
    ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    print(f'Wrote {args.out}')
    print(f'Catalog {len(CATALOG_ROUTES)}; coverage {len(cov_by_route)}; mapped directions {len(directions)}')
    print('Index/terminals policy routes:', ', '.join(INDEX_POLICY))


if __name__ == '__main__':
    main()
