"""Export the backend's supported route directions for the Flutter trip picker."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "pipeline" / "bus_route" / "routes.json"
OUTPUT = ROOT / "visionnav_app" / "assets" / "bus_trip_options.json"


if __name__ == "__main__":
    routes = json.loads(ROUTES.read_text(encoding="utf-8"))["routes"]
    options = [
        {
            "line": route["display_name"],
            "code": route["route_code"],
            "direction": direction["id"],
            "destination": direction["destination"],
        }
        for route in routes
        for direction in route["directions"]
    ]
    OUTPUT.write_text(json.dumps(options, indent=2) + "\n", encoding="utf-8")
