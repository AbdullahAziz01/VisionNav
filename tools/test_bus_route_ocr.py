"""Standalone single-image OCR check for VisionNav bus-route text.

Usage (from the repo root):
    python tools/test_bus_route_ocr.py --image path/to/image.jpg
    python tools/test_bus_route_ocr.py --image path/to/image.jpg --crop x,y,width,height

The first run may download EasyOCR English model weights.
This tool reads one image only and does not use RouteStabilityTracker.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.bus_route.ocr_reader import BusOcrReader
from pipeline.bus_route.route_matcher import RouteMatch, match_route_text

_FINAL_LABELS = {
    "toward_barakahu": "Green Line toward Barakahu",
    "toward_pims": "Green Line toward PIMS",
    "toward_n5": "Orange Line toward N-5",
    "toward_faiz_ahmad_faiz": "Orange Line toward Faiz Ahmad Faiz",
}


def parse_crop(value: str) -> tuple[int, int, int, int]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("Invalid crop. Use --crop x,y,width,height")
    try:
        x, y, width, height = (int(part) for part in parts)
    except ValueError as exc:
        raise ValueError(
            "Invalid crop. x, y, width, and height must be integers"
        ) from exc
    if width <= 0 or height <= 0:
        raise ValueError("Invalid crop. Width and height must be positive")
    return x, y, width, height


def clamp_crop(
    image,
    x: int,
    y: int,
    width: int,
    height: int,
) -> tuple[object, tuple[int, int, int, int]]:
    frame_height, frame_width = image.shape[:2]
    left = max(0, x)
    top = max(0, y)
    right = min(frame_width, x + width)
    bottom = min(frame_height, y + height)
    if right <= left or bottom <= top:
        raise ValueError(
            "Invalid crop. The rectangle is outside the image "
            f"({frame_width}x{frame_height})"
        )
    clamped = (left, top, right - left, bottom - top)
    return image[top:bottom, left:right], clamped


def collect_matches(texts: list[str]) -> list[RouteMatch]:
    matches: list[RouteMatch] = []
    seen: set[tuple[str, str]] = set()
    for text in texts:
        match = match_route_text(text)
        if match is None:
            continue
        key = (match.raw_text, match.direction_id)
        if key in seen:
            continue
        seen.add(key)
        matches.append(match)
    return matches


def final_label(matches: list[RouteMatch]) -> str:
    if not matches:
        return "No supported route match"
    best_confidence = max(match.confidence for match in matches)
    best = [match for match in matches if match.confidence == best_confidence]
    directions = {match.direction_id for match in best}
    if len(directions) != 1:
        return "No supported route match"
    return _FINAL_LABELS.get(best[0].direction_id, "No supported route match")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OCR one image and match it to a supported Metrobus route."
    )
    parser.add_argument("--image", required=True, help="Path to a local image")
    parser.add_argument(
        "--crop",
        default=None,
        help="Optional crop as x,y,width,height. Coordinates are clamped to the image.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    image_path = Path(args.image)
    if not image_path.is_file():
        print(f"Image not found: {image_path}", file=sys.stderr)
        return 1

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        print(f"Could not read image: {image_path}", file=sys.stderr)
        return 1

    if args.crop is not None:
        try:
            x, y, width, height = parse_crop(args.crop)
            image, clamped = clamp_crop(image, x, y, width, height)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        left, top, crop_width, crop_height = clamped
        print(
            f"Crop: x={left}, y={top}, width={crop_width}, height={crop_height}"
        )

    print(
        "Loading EasyOCR. The first run may download English model weights.",
        flush=True,
    )
    try:
        items, combined = BusOcrReader().text_candidates(image)
    except Exception as exc:
        print(f"OCR failed: {exc}", file=sys.stderr)
        return 1

    print()
    print("OCR results:")
    if not items:
        print("  (none)")
    for item in items:
        print(f"  {item.text}  confidence={item.confidence:.2f}")

    print("Combined OCR text:")
    print(f"  {combined if combined else '(none)'}")

    texts = [item.text for item in items]
    if combined and combined not in texts:
        texts.append(combined)
    matches = collect_matches(texts)

    print("Route matches:")
    if not matches:
        print("  (none)")
    for match in matches:
        label = _FINAL_LABELS.get(match.direction_id, match.direction_id)
        print(
            f"  {label}  direction={match.direction_id}  "
            f"confidence={match.confidence:.2f}  text={match.raw_text!r}"
        )

    print("Final result:")
    print(f"  {final_label(matches)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
