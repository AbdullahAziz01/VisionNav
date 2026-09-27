"""Build the app's offline transit gazetteer from OpenStreetMap.

Pulls named public-transport stops (bus stops, bus stations, Metro Bus
stations) from the Overpass API and writes
visionnav_app/assets/transit_stops.json.

The app matches spoken destinations against this file first, because OSM's
free-text search misses local phrasing: a user saying "PIMS bus stand" gets no
result, since OSM names it "PIMS Metro Bus Station".

Run from the repo root:
    python tools/build_transit_gazetteer.py

To cover another city, change BBOX (south, west, north, east).
Data: (c) OpenStreetMap contributors, ODbL.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "visionnav_app" / "assets" / "transit_stops.json"

# Islamabad / Rawalpindi
BBOX = (33.40, 72.80, 33.80, 73.30)
AREA_NAME = "Islamabad / Rawalpindi"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "VisionNav-FYP/1.0 (student accessibility project)"

# Words describing the KIND of place, not which place it is. Stripping them is
# what lets "PIMS bus stand" match "PIMS Metro Bus Station".
# Keep in sync with TransitGazetteer._noise in the Dart code.
NOISE = {
    "metro", "bus", "station", "stop", "terminal", "stand", "adda",
    "north", "south", "east", "west", "no", "islamabad", "rawalpindi",
}


def build_query(bbox: tuple[float, float, float, float]) -> str:
    b = ",".join(str(v) for v in bbox)
    return f"""
[out:json][timeout:90];
(
  node["highway"="bus_stop"]["name"]({b});
  node["amenity"="bus_station"]["name"]({b});
  way["amenity"="bus_station"]["name"]({b});
  node["public_transport"~"station|stop_position"]["name"]({b});
  way["public_transport"="station"]["name"]({b});
);
out center tags;
"""


def normalize(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def core_tokens(name: str) -> list[str]:
    return [t for t in normalize(name).split() if t not in NOISE]


def fetch(query: str) -> dict:
    req = urllib.request.Request(
        OVERPASS_URL,
        data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def main() -> int:
    data = fetch(build_query(BBOX))

    stops: dict[str, dict] = {}
    for element in data["elements"]:
        tags = element.get("tags", {})
        name = (tags.get("name") or "").strip()
        if not name:
            continue
        lat = element.get("lat") or element.get("center", {}).get("lat")
        lon = element.get("lon") or element.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue

        core = core_tokens(name)
        if not core:
            continue
        key = " ".join(core)
        is_metro = "metro" in normalize(name)

        existing = stops.get(key)
        # Prefer the main Metro entry over duplicated North/South platforms.
        better = (
            existing is None
            or (is_metro and not existing["metro"])
            or (is_metro == existing["metro"] and len(name) < len(existing["name"]))
        )
        if better:
            stops[key] = {
                "name": name,
                "key": key,
                "lat": round(float(lat), 6),
                "lon": round(float(lon), 6),
                "metro": is_metro,
            }

    records = sorted(stops.values(), key=lambda r: (not r["metro"], r["key"]))
    payload = {
        "source": "OpenStreetMap via Overpass API (ODbL)",
        "area": AREA_NAME,
        "bbox": list(BBOX),
        "count": len(records),
        "stops": records,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    metro = sum(r["metro"] for r in records)
    print(f"wrote {OUT.relative_to(ROOT)}  stops={len(records)}  metro={metro}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
