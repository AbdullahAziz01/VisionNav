"""Build direct bus planning data from CDA timetables and mapped stops.

Install pypdf and beautifulsoup4, then run:
    python tools/build_direct_bus_routes.py --cache PATH_TO_PDF_CACHE

Policy for defense / usable planning:
  - Where the CDA website index conflicts with a linked PDF, use the index
    endpoints and headway; do not feed the conflicting PDF stop sequence into
    the planner (PDF names stay in coverage for audit only).
  - Where a route has no uniquely mapped mid-stop pins, emit terminals-only
    directions (start ↔ end) so the app can still navigate boarding/exit ends.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from build_transit_gazetteer import core_tokens

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'visionnav_app' / 'assets'
SOURCE = 'https://www.cda.gov.pk/cdaTransitMap'
ROUTE_CODE = re.compile(r'(?:FR[A-Z]?|ST)-[0-9]+[A-Z]?')
TIME = r'\d{2}:\d{2}:\d{2}'
TRIP = re.compile(rf'\b(\d{{4,}}(?:-\d+)?)\s+{TIME}\s+stop_name\s+arrival_time\s+departure_time\s*', re.I)
ROW = re.compile(rf'\s*(.*?)\s*({TIME})\s+({TIME})(?=\D|$)', re.S)
GENERIC = {'bus', 'metro', 'station', 'stop', 'stand', 'terminal'}

# CDA website index endpoints. Used when PDF conflicts with the index, or when
# mid-route gazetteer pins are missing (terminals-only navigation).
INDEX_TERMINALS = {
    'FR-03A': {
        'start': 'PIMS Hospital',
        'end': 'Saidpur Village',
        'start_key': 'pims',
        'end_key': 'saidpur village',
        'headway_min': 20,
        'policy': 'index_over_pdf',
        'note': (
            'CDA index endpoints PIMS–Saidpur Village (20 min) used; conflicting '
            'PDF Faisal Masjid / Flower Market sequence ignored for planner.'
        ),
    },
    'FR-05': {
        'start': 'Golra Morh Metro Station',
        'end': 'Taxila',
        'start_key': 'golra mor',
        'end_key': 'taxila',
        'headway_min': 5,
        'policy': 'index_over_pdf',
        'note': (
            'CDA index endpoints Golra Morh–Taxila (5 min) used; conflicting PDF '
            'NUST–D-12 stop sequence ignored for planner.'
        ),
    },
    'FR-08A': {
        'start': 'PIMS Hospital',
        'end': 'Capt. Naeem Tufail Shaheed Chowk',
        'start_key': 'pims',
        'end_key': 'capt naeem tufail shaheed chowk',
        'headway_min': 20,
        'policy': 'index_over_pdf',
        'note': (
            'CDA index headway 20 minutes used; denser PDF headway ignored. '
            'Terminals only until mid-stop pins exist.'
        ),
    },
    'FR-04B': {
        'start': 'PIMS Hospital',
        'end': 'Diplomatic Enclave',
        'start_key': 'pims',
        'end_key': 'diplomatic enclave gate 4',
        'headway_min': None,
        'policy': 'index_terminals',
        'note': (
            'CDA lists Diplomatic Enclave shuttle with no fixed headway and no '
            'timetable PDF; terminals-only guidance between PIMS and Diplomatic Enclave.'
        ),
    },
    'FR-04A': {
        'start': 'Bari Imam',
        'end': 'Quaid Azam University',
        'start_key': 'bari imam',
        'end_key': 'quaid azam university',
        'headway_min': 30,
        'policy': 'terminals_only',
        'note': 'No mid-stop pins; terminals-only boarding/exit navigation.',
    },
    'FR-08C': {
        'start': 'PIMS Hospital',
        'end': 'Capt. Naeem Tufail Shaheed Chowk',
        'start_key': 'pims',
        'end_key': 'capt naeem tufail shaheed chowk',
        'headway_min': 20,
        'policy': 'terminals_only',
        'note': 'No mid-stop pins; terminals-only boarding/exit navigation.',
    },
    'FR-11': {
        'start': 'Golra Morh Metro Station',
        'end': 'I-16',
        'start_key': 'golra mor',
        'end_key': 'i 16',
        'headway_min': 60,
        'policy': 'terminals_only',
        'note': 'No mid-stop pins; terminals-only boarding/exit navigation.',
    },
    'FR-14A': {
        'start': 'Barakahu',
        'end': 'Satra Meel',
        'start_key': 'barakahu',
        'end_key': 'satra meel',
        'headway_min': 15,
        'policy': 'terminals_only',
        'note': 'No mid-stop pins; terminals-only boarding/exit navigation.',
    },
    'ST-02': {
        'start': 'PIMS Hospital',
        'end': 'Capt. Naeem Tufail Shaheed Chowk',
        'start_key': 'pims',
        'end_key': 'capt naeem tufail shaheed chowk',
        'headway_min': 60,
        'policy': 'terminals_only',
        'note': 'No mid-stop pins; terminals-only boarding/exit navigation.',
    },
}

# Landmark pins for index terminals missing from the OSM gazetteer export.
# Coords from OpenStreetMap Nominatim place centroids (not curb platforms).
CURATED_TERMINALS = [
    {
        'name': 'Saidpur Village',
        'key': 'saidpur village',
        'lat': 33.754157,
        'lon': 73.069938,
        'metro': False,
        'curated': True,
    },
    {
        # CDA PDF spelling (no hyphenated "e"); keep alias for Quaid-e-Azam.
        'name': 'Quaid Azam University',
        'key': 'quaid azam university',
        'lat': 33.743736,
        'lon': 73.158582,
        'metro': False,
        'curated': True,
    },
    {
        # CDA end name; place pin near Taramri / Tramri on Lehtrar Road.
        'name': 'Capt. Naeem Tufail Shaheed Chowk',
        'key': 'capt naeem tufail shaheed chowk',
        'lat': 33.643198,
        'lon': 73.161500,
        'metro': False,
        'curated': True,
    },
    {
        'name': 'Barakahu',
        'key': 'barakahu',
        'lat': 33.738068,
        'lon': 73.185495,
        'metro': False,
        'curated': True,
    },
    {
        'name': 'I-16',
        'key': 'i 16',
        'lat': 33.593578,
        'lon': 72.932944,
        'metro': False,
        'curated': True,
    },
]

NAME_ALIASES = {
    'hassan abdal': 'hasaan abdal',
    'golra morh': 'golra mor',
    'golra morh metro station': 'golra mor',
    'golra mor station': 'golra mor',
    'golra mor metro station': 'golra mor',
    'pims hospital': 'pims',
    'pims metro station': 'pims',
    'said pur village': 'saidpur village',
    'saidpur village': 'saidpur village',
    'qa university': 'quaid azam university',
    'qau': 'quaid azam university',
    'quaid azam university': 'quaid azam university',
    'quaid e azam university': 'quaid azam university',
    'capt naeem tufail shaheed chowk': 'capt naeem tufail shaheed chowk',
    'capt naeem t shaheed chowk': 'capt naeem tufail shaheed chowk',
    'capt tufail shaheed chowk': 'capt naeem tufail shaheed chowk',
    'tramri': 'capt naeem tufail shaheed chowk',
    'taramri': 'capt naeem tufail shaheed chowk',
    'barakahu': 'barakahu',
    'bhara kahu': 'barakahu',
    'barahkahu': 'barakahu',
    'bahra kahu': 'barakahu',
    'i 16': 'i 16',
    'i16': 'i 16',
    'diplomatic enclave': 'diplomatic enclave gate 4',
}


def route_category(code: str) -> str:
    if code == 'FRB-01':
        return 'blue_labeled_feeder'
    if code == 'FRG-1':
        return 'green_labeled_feeder'
    if code.startswith('ST-'):
        return 'sightseeing'
    return 'feeder'


def fetch(url: str) -> bytes:
    request = Request(url, headers={'User-Agent': 'VisionNav-FYP/1.0'})
    with urlopen(request, timeout=25) as response:
        return response.read()


def parse_index_html(html: str) -> list[tuple[str, str, str]]:
    page = BeautifulSoup(html, 'html.parser')
    directions = []
    code = None
    for row in page.select('tr'):
        cells = [' '.join(cell.stripped_strings) for cell in row.find_all('td', recursive=False)]
        if len(cells) > 1 and ROUTE_CODE.fullmatch(cells[1]):
            code = cells[1]
        links = [urljoin(SOURCE, a['href']) for a in row.select('a[href]')
                 if '/metro_transit_route' in a['href']]
        if code and len(cells) >= 3 and links:
            directions.append((code, cells[-3], links[0]))
    return directions


def index_from_pdf_cache(cache: Path) -> list[tuple[str, str, str]]:
    """Offline fallback when the CDA website is unreachable."""
    rows = []
    for pdf in sorted(cache.glob('*.pdf')):
        match = re.match(r'((?:FR[A-Z]?|ST)-[0-9]+[A-Z]?)_(Forward|Backward)\.pdf$', pdf.name, re.I)
        if not match:
            continue
        code, direction = match.group(1), match.group(2)
        spec = INDEX_TERMINALS.get(code)
        if spec:
            label = (
                f"{spec['end']} - {spec['start']}"
                if direction.lower() == 'backward'
                else f"{spec['start']} - {spec['end']}"
            )
        else:
            label = f'{code} {direction}'
        rows.append((code, label, f'https://www.cda.gov.pk/Assets/metro_transit_route/{pdf.name}'))
    return rows


def read_index(cache: Path, index_cache: Path) -> list[tuple[str, str, str]]:
    html = None
    try:
        html = fetch(SOURCE).decode('utf-8', errors='replace')
        index_cache.parent.mkdir(parents=True, exist_ok=True)
        index_cache.write_text(html, encoding='utf-8')
    except OSError as error:
        if index_cache.exists():
            print(f'CDA index fetch failed ({error}); using cached HTML {index_cache}')
            html = index_cache.read_text(encoding='utf-8')
        else:
            print(f'CDA index fetch failed ({error}); reconstructing from PDF cache')
            directions = index_from_pdf_cache(cache)
            if directions:
                return directions
            raise
    directions = parse_index_html(html or '')
    if not directions:
        directions = index_from_pdf_cache(cache)
    if not directions:
        raise ValueError('CDA route table is empty')
    return directions


def tokens(name: str) -> list[str]:
    return [str(int(word)) if word.isdigit() else word
            for word in re.findall(r'[a-z0-9]+', name.lower())]


def identity(name: str) -> str:
    return ''.join(word for word in tokens(name) if word not in GENERIC)


def synthesize_headway(interval_min: int | None) -> list[str]:
    if not interval_min or interval_min <= 0:
        return []
    times = []
    for mins in range(6 * 60, 22 * 60 + 1, interval_min):
        hour, minute = divmod(mins, 60)
        times.append(f'{hour:02d}:{minute:02d}:00')
    return times


def map_stops(records: list[dict]):
    by_name: dict[str, set[str]] = defaultdict(set)
    by_identity: dict[str, set[str]] = defaultdict(set)
    by_key = {stop['key']: stop for stop in records}
    for stop in records:
        by_name[''.join(tokens(stop['name']))].add(stop['key'])
        for name in (stop['name'], stop['key']):
            by_identity[identity(name)].add(stop['key'])

    for alias, canonical in NAME_ALIASES.items():
        if canonical in by_key:
            by_identity[identity(alias)].add(canonical)
            by_name[''.join(tokens(alias))].add(canonical)

    metro_keys = {stop['key'] for stop in records if stop.get('metro')}

    def match(name: str) -> str | None:
        if identity(name) == 'cda':
            return None
        alias_key = NAME_ALIASES.get(' '.join(tokens(name)))
        if alias_key and alias_key in by_key:
            return alias_key
        exact = by_name.get(''.join(tokens(name)), set())
        candidates = exact or by_identity.get(identity(name), set())
        if 'metro' in tokens(name):
            candidates = candidates & metro_keys
        return next(iter(candidates)) if len(candidates) == 1 else None

    return match


def parse_trips(text: str, code: str) -> list[list[tuple[str, str]]]:
    metadata = re.search(r'Short Name\s+(\S+)', text)
    count = re.search(r'Total Trips\s*(\d+)', text)
    starts = list(TRIP.finditer(text))
    if not metadata or metadata[1] != code or not count or len(starts) != int(count[1]):
        raise ValueError('route metadata or trip count does not match the index')
    if len({start[1] for start in starts}) != len(starts):
        raise ValueError('duplicate trip ID')
    trips = []
    for i, start in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        rows = [(' '.join(name.split()), arrival, departure)
                for name, arrival, departure in ROW.findall(text[start.end():end])]
        if len(rows) < 2 or any(not name or len(name) > 90 for name, _, _ in rows):
            raise ValueError('unreadable stop sequence')
        last = '00:00:00'
        trip = []
        for name, arrival, departure in rows:
            if not last <= arrival <= departure < '24:00:00':
                raise ValueError('departure clock times are inconsistent')
            trip.append((name, departure))
            last = departure
        trips.append(trip)
    return trips


def terminal_direction(
    code: str,
    label: str,
    url: str,
    spec: dict,
    *,
    reverse: bool,
) -> dict:
    start_key, end_key = spec['start_key'], spec['end_key']
    start_name, end_name = spec['start'], spec['end']
    if reverse:
        keys = [end_key, start_key]
        aliases = {end_key: end_name, start_key: start_name}
        toward = start_name
    else:
        keys = [start_key, end_key]
        aliases = {start_key: start_name, end_key: end_name}
        toward = end_name
    departures = synthesize_headway(spec.get('headway_min'))
    return {
        'route': code,
        'category': route_category(code),
        'toward': toward,
        'source': url,
        'listedDirection': label,
        'verificationStatus': 'index_terminals',
        'terminalsOnly': True,
        'platformSideVerified': False,
        'coordinatesVerified': False,
        'policyNote': spec['note'],
        'stopKeys': keys,
        'stopAliases': aliases,
        'departures': {keys[0]: departures} if departures else {},
    }


def import_direction(entry, cache, match):
    code, label, url = entry
    spec = INDEX_TERMINALS.get(code)
    audit = {
        'route': code,
        'category': route_category(code),
        'listedDirection': label,
        'source': url,
        'verificationStatus': 'pending',
    }
    if spec:
        audit['policyNote'] = spec['note']
        audit['policy'] = spec['policy']

    name = Path(urlparse(url).path).name
    reverse = 'backward' in name.lower()
    trips: list[list[tuple[str, str]]] = []
    pdf_records: list[dict] = []

    if not name.lower().endswith('.pdf'):
        if spec:
            records = [
                terminal_direction(code, label, SOURCE, spec, reverse=False),
                terminal_direction(code, label, SOURCE, spec, reverse=True),
            ]
            return records, audit | {
                'status': 'available_index_terminals',
                'publishedTrips': 0,
                'publishedStops': [spec['start'], spec['end']],
                'mappedStops': 2,
                'verificationStatus': 'index_terminals',
            }
        return [], audit | {'status': 'no published timetable PDF'}

    try:
        file = cache / name
        if not file.exists():
            file.write_bytes(fetch(url))
        extracted = cache / (name + '.txt')
        if not extracted.exists() or extracted.stat().st_mtime < file.stat().st_mtime:
            extracted.write_text('\n'.join(page.extract_text() for page in PdfReader(file).pages),
                                 encoding='utf-8')
        trips = parse_trips(extracted.read_text(encoding='utf-8'), code)
    except (OSError, ValueError, PdfReadError) as error:
        if spec:
            record = terminal_direction(code, label, url, spec, reverse=reverse)
            return [record], audit | {
                'status': 'available_index_terminals',
                'publishedTrips': 0,
                'publishedStops': [spec['start'], spec['end']],
                'mappedStops': 2,
                'verificationStatus': 'index_terminals',
                'parseError': str(error),
            }
        return [], audit | {'status': str(error)}

    patterns = defaultdict(list)
    for trip in trips:
        patterns[tuple(name for name, _ in trip)].append(trip)
    force_index = bool(spec and spec['policy'] == 'index_over_pdf')
    if not force_index:
        for names, runs in patterns.items():
            keys = [match(name) for name in names]
            counts = Counter(keys)
            metro_counts = Counter(key for name, key in zip(names, keys) if 'metro' in tokens(name))
            mapped = [(i, key) for i, key in enumerate(keys) if key is not None and (
                counts[key] == 1 or (metro_counts[key] == 1 and 'metro' in tokens(names[i])))]
            if len(mapped) < 2:
                continue
            record = {
                'route': code,
                'category': route_category(code),
                'toward': names[-1],
                'source': url,
                'listedDirection': label,
                'verificationStatus': 'schedule_mapped',
                'platformSideVerified': False,
                'coordinatesVerified': False,
                'stopKeys': [key for _, key in mapped],
                'stopAliases': {key: names[i] for i, key in mapped},
                'departures': {key: sorted({trip[i][1] for trip in runs}) for i, key in mapped[:-1]},
            }
            if code == 'FR-07':
                record['scanCode'] = 'FR-7'
                if identity(names[-1]) == 'pimshospital':
                    record['scanDirection'] = 'fr_7_toward_pims'
                elif 'G-11 Markaz' in names:
                    record['scanDirection'] = 'fr_7_toward_g11'
                    record['scanExitKeys'] = [key for i, key in mapped if i < names.index('G-11 Markaz')]
            pdf_records.append(record)

    if force_index or (spec and not pdf_records):
        records = [terminal_direction(code, label, url, spec, reverse=reverse)]
        status = 'available_index_terminals'
        verification = 'index_terminals'
    elif pdf_records:
        records = pdf_records
        # Sparse endpoint-only mappings for incomplete corridors still need
        # terminals-only speech (no mid-stop guidance).
        if spec and spec['policy'] == 'terminals_only':
            for record in records:
                record['terminalsOnly'] = True
                record['policyNote'] = spec['note']
                if len(record.get('stopKeys', [])) <= 2:
                    record['verificationStatus'] = 'index_terminals'
            status = 'available_index_terminals'
            verification = 'index_terminals'
        else:
            status = 'available'
            verification = 'schedule_mapped'
    else:
        records = []
        status = 'fewer than two uniquely mapped stops'
        verification = 'incomplete_mapping'

    published = sorted({name for trip in trips for name, _ in trip})
    if spec and verification == 'index_terminals':
        published = sorted(set(published) | {spec['start'], spec['end']})

    return records, audit | {
        'status': status,
        'publishedTrips': len(trips),
        'publishedStops': published,
        'mappedStops': len({key for record in records for key in record['stopKeys']}),
        'verificationStatus': verification,
    }


def additional_stops(osm_path: Path, known: list[dict]) -> list[dict]:
    """Import unambiguous named stop features from an optional Overpass export."""
    existing = {identity(stop['name']) for stop in known} | {identity(stop['key']) for stop in known}
    known_keys = {stop['key'] for stop in known}
    by_name = defaultdict(list)
    for element in json.loads(osm_path.read_text(encoding='utf-8'))['elements']:
        tags = element.get('tags', {})
        name = tags.get('name:en') or tags.get('name', '')
        key = ' '.join(core_tokens(name))
        point = element.get('center', element)
        if not key or key in known_keys or identity(name) in existing or 'lat' not in point or 'lon' not in point:
            continue
        by_name[identity(name)].append({
            'name': name,
            'key': key,
            'lat': round(point['lat'], 6),
            'lon': round(point['lon'], 6),
            'metro': 'metro' in tokens(name),
            'osm': f"{element['type']}/{element['id']}",
        })
    unique_names = [group[0] for group in by_name.values() if len(group) == 1]
    keys = Counter(stop['key'] for stop in unique_names)
    return [stop for stop in unique_names if keys[stop['key']] == 1]


def merge_curated_terminals(stops: list[dict]) -> list[dict]:
    known_keys = {stop['key'] for stop in stops}
    added = []
    for stop in CURATED_TERMINALS:
        if stop['key'] not in known_keys:
            stops.append(dict(stop))
            added.append(stop['key'])
            known_keys.add(stop['key'])
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--osm', type=Path, help='optional Overpass named stop export')
    parser.add_argument(
        '--index-cache',
        type=Path,
        default=ROOT / 'tmp' / 'cda_index.html',
        help='cached CDA transit map HTML for offline rebuilds',
    )
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    stops_path = ASSETS / 'transit_stops.json'
    gazetteer = json.loads(stops_path.read_text(encoding='utf-8-sig'))
    stops = gazetteer['stops']
    curated_added = merge_curated_terminals(stops)
    if len({stop['key'] for stop in stops}) != len(stops):
        raise ValueError('Duplicate gazetteer stop keys')
    additions = additional_stops(args.osm, stops) if args.osm else []
    match = map_stops(stops + additions)
    index = read_index(args.cache, args.index_cache)
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(lambda entry: import_direction(entry, args.cache, match), index))

    # FR-04B (and any index-only route) may appear without a PDF link row.
    covered = {audit['route'] for _, audit in outcomes}
    for code, spec in INDEX_TERMINALS.items():
        if code in covered:
            continue
        records = [
            terminal_direction(code, f"{spec['start']} - {spec['end']}", SOURCE, spec, reverse=False),
            terminal_direction(code, f"{spec['end']} - {spec['start']}", SOURCE, spec, reverse=True),
        ]
        audit = {
            'route': code,
            'category': route_category(code),
            'listedDirection': f"{spec['start']} - {spec['end']}",
            'source': SOURCE,
            'status': 'available_index_terminals',
            'publishedTrips': 0,
            'publishedStops': [spec['start'], spec['end']],
            'mappedStops': 2,
            'verificationStatus': 'index_terminals',
            'policy': spec['policy'],
            'policyNote': spec['note'],
        }
        outcomes.append((records, audit))

    directions = [record for records, _ in outcomes for record in records]
    coverage = [audit for _, audit in outcomes]
    if not directions:
        raise ValueError('No usable route records were imported')
    used = {key for direction in directions for key in direction['stopKeys']}
    retained = [stop for stop in additions if stop['key'] in used]
    if curated_added or retained:
        if retained:
            stops.extend(retained)
        gazetteer['stops'] = stops
        gazetteer['count'] = len(stops)
        bbox = gazetteer['bbox']
        changed = retained + [s for s in stops if s['key'] in curated_added]
        if changed:
            gazetteer['bbox'] = [
                min([bbox[0]] + [s['lat'] for s in changed]),
                min([bbox[1]] + [s['lon'] for s in changed]),
                max([bbox[2]] + [s['lat'] for s in changed]),
                max([bbox[3]] + [s['lon'] for s in changed]),
            ]
        stops_path.write_text(json.dumps(gazetteer, ensure_ascii=False, indent=1) + '\n',
                              encoding='utf-8', newline='\n')
        print(
            'Updated gazetteer pins: '
            + ', '.join(curated_added + [s['key'] for s in retained])
        )
    data = {
        'source': SOURCE,
        'generatedFrom': 'tools/build_direct_bus_routes.py',
        'timingNote': (
            'Departures are CDA published schedule times or index headway estimates, '
            'not live bus ETAs. Index-conflict routes use CDA website endpoints only. '
            'Routes without mid-stop pins use terminals-only boarding/exit navigation. '
            'platformSideVerified and coordinatesVerified are false unless a '
            'separate authoritative source confirms curb/platform geometry.'
        ),
        'coverage': coverage,
        'directions': directions,
    }
    payload = json.dumps(data, indent=2)
    payload = re.sub(r'\[\s*(?:"\d\d:\d\d:\d\d",?\s*)+\]',
                     lambda match: json.dumps(json.loads(match[0])), payload)
    (ASSETS / 'direct_bus_routes.json').write_text(payload + '\n', encoding='utf-8', newline='\n')
    print(f'{len({d["route"] for d in directions})} of {len({e[0] for e in index} | set(INDEX_TERMINALS))} routes, '
          f'{len(directions)} mapped directions')
    for audit in coverage:
        if audit['status'] not in {'available', 'available_index_terminals'}:
            print(f'{audit["route"]} {audit["listedDirection"]}: {audit["status"]}')


if __name__ == '__main__':
    main()
