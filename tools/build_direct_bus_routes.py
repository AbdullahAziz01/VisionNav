"""Build direct bus planning data from CDA timetables and mapped stops.

Install pypdf and beautifulsoup4, then run:
    python tools/build_direct_bus_routes.py --cache PATH_TO_PDF_CACHE

The cache holds downloaded PDFs, never checked into Git. Unmatched or ambiguous
stop names are omitted, and directions with fewer than two mapped stops are
recorded in the coverage audit. The resulting coordinates are mapped station
locations, not verified direction-specific boarding points.
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


def fetch(url: str) -> bytes:
    request = Request(url, headers={'User-Agent': 'VisionNav-FYP/1.0'})
    with urlopen(request, timeout=25) as response:
        return response.read()


def read_index() -> list[tuple[str, str, str]]:
    page = BeautifulSoup(fetch(SOURCE), 'html.parser')
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
    if not directions:
        raise ValueError('CDA route table is empty')
    return directions


def tokens(name: str) -> list[str]:
    return [str(int(word)) if word.isdigit() else word
            for word in re.findall(r'[a-z0-9]+', name.lower())]


def identity(name: str) -> str:
    return ''.join(word for word in tokens(name) if word not in GENERIC)


def map_stops(records: list[dict]):
    by_name: dict[str, set[str]] = defaultdict(set)
    by_identity: dict[str, set[str]] = defaultdict(set)
    for stop in records:
        by_name[''.join(tokens(stop['name']))].add(stop['key'])
        for name in (stop['name'], stop['key']):
            by_identity[identity(name)].add(stop['key'])

    def match(name: str) -> str | None:
        # Bare CDA can refer to unrelated stops. Without a qualified name, skip it.
        if identity(name) == 'cda':
            return None
        exact = by_name.get(''.join(tokens(name)), set())
        candidates = exact or by_identity.get(identity(name), set())
        if 'metro' in tokens(name):
            candidates = candidates & metro_keys
        return next(iter(candidates)) if len(candidates) == 1 else None

    # Explicit spelling equivalences from CDA and OSM stop labels.
    for cda_name, map_name in {'hassan abdal': 'hasaan abdal'}.items():
        by_identity[identity(cda_name)].update(by_identity.get(identity(map_name), set()))
    metro_keys = {stop['key'] for stop in records if stop.get('metro')}
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


def import_direction(entry, cache, match):
    code, label, url = entry
    audit = {'route': code, 'listedDirection': label, 'source': url}
    name = Path(urlparse(url).path).name
    if not name.lower().endswith('.pdf'):
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
        return [], audit | {'status': str(error)}

    patterns = defaultdict(list)
    for trip in trips:
        patterns[tuple(name for name, _ in trip)].append(trip)
    records = []
    for names, runs in patterns.items():
        keys = [match(name) for name in names]
        counts = Counter(keys)
        # Where a terminal name and its distinct metro stop both occur,
        # retain the explicitly named metro stop and omit the ambiguous label.
        metro_counts = Counter(key for name, key in zip(names, keys) if 'metro' in tokens(name))
        mapped = [(i, key) for i, key in enumerate(keys) if key is not None and (
            counts[key] == 1 or (metro_counts[key] == 1 and 'metro' in tokens(names[i])))]
        if len(mapped) < 2:
            continue
        record = {
            'route': code,
            'toward': names[-1],
            'source': url,
            'stopKeys': [key for _, key in mapped],
            'stopAliases': {key: names[i] for i, key in mapped},
            'departures': {key: sorted({trip[i][1] for trip in runs}) for i, key in mapped[:-1]},
        }
        # Keep the existing FR-07 scanner compatible with the sign vocabulary
        # in the backend. Other imported routes require driver confirmation.
        if code == 'FR-07':
            record['scanCode'] = 'FR-7'
            if identity(names[-1]) == 'pimshospital':
                record['scanDirection'] = 'fr_7_toward_pims'
            elif 'G-11 Markaz' in names:
                record['scanDirection'] = 'fr_7_toward_g11'
                record['scanExitKeys'] = [key for i, key in mapped if i < names.index('G-11 Markaz')]
        records.append(record)
    status = 'available' if records else 'fewer than two uniquely mapped stops'
    return records, audit | {'status': status, 'publishedTrips': len(trips),
                              'publishedStops': sorted({name for trip in trips for name, _ in trip}),
                              'mappedStops': len({key for record in records for key in record['stopKeys']})}


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--osm', type=Path, help='optional Overpass named stop export')
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    stops_path = ASSETS / 'transit_stops.json'
    gazetteer = json.loads(stops_path.read_text(encoding='utf-8-sig'))
    stops = gazetteer['stops']
    if len({stop['key'] for stop in stops}) != len(stops):
        raise ValueError('Duplicate gazetteer stop keys')
    additions = additional_stops(args.osm, stops) if args.osm else []
    match = map_stops(stops + additions)
    index = read_index()
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(lambda entry: import_direction(entry, args.cache, match), index))
    directions = [record for records, _ in outcomes for record in records]
    coverage = [audit for _, audit in outcomes]
    if not directions:
        raise ValueError('No usable route records were imported')
    used = {key for direction in directions for key in direction['stopKeys']}
    retained = [stop for stop in additions if stop['key'] in used]
    if retained:
        stops.extend(retained)
        gazetteer['count'] = len(stops)
        bbox = gazetteer['bbox']
        gazetteer['bbox'] = [min([bbox[0]] + [s['lat'] for s in retained]),
                              min([bbox[1]] + [s['lon'] for s in retained]),
                              max([bbox[2]] + [s['lat'] for s in retained]),
                              max([bbox[3]] + [s['lon'] for s in retained])]
        stops_path.write_text(json.dumps(gazetteer, ensure_ascii=False, indent=1) + '\n',
                              encoding='utf-8', newline='\n')
        print(f'Added {len(retained)} mapped stops: ' + ', '.join(s['key'] for s in retained))
    data = {'source': SOURCE, 'coverage': coverage, 'directions': directions}
    payload = json.dumps(data, indent=2)
    payload = re.sub(r'\[\s*(?:"\d\d:\d\d:\d\d",?\s*)+\]',
                     lambda match: json.dumps(json.loads(match[0])), payload)
    (ASSETS / 'direct_bus_routes.json').write_text(payload + '\n', encoding='utf-8', newline='\n')
    print(f'{len({d["route"] for d in directions})} of {len({e[0] for e in index})} routes, '
          f'{len(directions)} mapped directions')
    for audit in coverage:
        if audit['status'] != 'available':
            print(f'{audit["route"]} {audit["listedDirection"]}: {audit["status"]}')


if __name__ == '__main__':
    main()
