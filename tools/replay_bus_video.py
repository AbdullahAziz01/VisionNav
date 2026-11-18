"""Replay a recorded video through VisionNav's existing frame API.

This is a development/evaluation helper. It does not alter the live scanner.
Frames are uploaded sequentially with one session ID so the backend can keep
tracking and bus-route OCR evidence across the clip.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import cv2
except ImportError as exc:  # pragma: no cover - depends on local environment
    raise SystemExit("OpenCV is required. Install the project's Python requirements first.") from exc


def make_multipart(field_name: str, filename: str, payload: bytes) -> tuple[bytes, str]:
    boundary = "----VisionNavReplay" + uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        "Content-Type: image/jpeg\r\n\r\n"
    ).encode("utf-8") + payload + f"\r\n--{boundary}--\r\n".encode("ascii")
    return body, boundary


def request_frame(url: str, session_id: str, filename: str, jpeg: bytes,
                  api_key: str | None, timeout: float) -> tuple[int, dict[str, Any]]:
    body, boundary = make_multipart("file", filename, jpeg)
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "X-Session-ID": session_id,
        "Accept": "application/json",
    }
    if api_key:
        headers["X-API-Key"] = api_key
    req = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = response.status
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    except URLError as exc:
        raise RuntimeError(f"Could not reach backend: {exc.reason}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"response_text": raw}
    if not isinstance(data, dict):
        data = {"response": data}
    return status, data


def first_value(data: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        value = data.get(name)
        if value not in (None, "", [], {}):
            return value
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send sampled frames from a bus video through VisionNav's /pipeline/frame API."
    )
    parser.add_argument("video", type=Path, help="Path to a recorded video (MP4, MOV, AVI, etc.)")
    parser.add_argument("--api", default="http://127.0.0.1:8000",
                        help="Backend base URL (default: http://127.0.0.1:8000)")
    parser.add_argument("--api-key", default=os.getenv("VISIONNAV_API_KEY"),
                        help="Backend API key; can also be set as VISIONNAV_API_KEY")
    parser.add_argument("--session-id", default=None,
                        help="Session ID to reuse; otherwise a fresh replay session is generated")
    parser.add_argument("--sample-every", type=int, default=6,
                        help="Upload one frame every N source frames (default: 6)")
    parser.add_argument("--max-fps", type=float, default=2.0,
                        help="Maximum upload rate to avoid overwhelming the backend (default: 2)")
    parser.add_argument("--timeout", type=float, default=120.0,
                        help="Per-frame HTTP timeout in seconds (default: 120)")
    parser.add_argument("--output", type=Path, default=Path("runs/bus_video_tests"),
                        help="Folder for replay_results.csv and replay_results.jsonl")
    args = parser.parse_args()

    if not args.video.is_file():
        parser.error(f"video file does not exist: {args.video}")
    if args.sample_every < 1 or args.max_fps <= 0 or args.timeout <= 0:
        parser.error("sample-every, max-fps, and timeout must be positive")

    endpoint = args.api.rstrip("/") + "/pipeline/frame"
    session_id = args.session_id or f"video-replay-{uuid.uuid4().hex}"
    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        raise SystemExit(f"Could not open video: {args.video}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    args.output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = args.video.stem
    csv_path = args.output / f"{stem}_{stamp}_results.csv"
    jsonl_path = args.output / f"{stem}_{stamp}_results.jsonl"
    fields = ["frame", "video_time_seconds", "http_status", "bus_detected",
              "route", "direction", "message", "error"]
    sent = 0
    failed = 0
    frame_index = 0
    previous_send = 0.0
    delay = 1.0 / args.max_fps

    print(f"Video: {args.video}")
    print(f"Backend: {endpoint}")
    print(f"Session: {session_id}")
    print(f"Source: {fps:.2f} fps, {total} frames; sampling every {args.sample_every} frames")
    print("Starting replay; frames are uploaded sequentially to preserve backend tracking state.")

    try:
        with csv_path.open("w", newline="", encoding="utf-8-sig") as csv_file, \
                jsonl_path.open("w", encoding="utf-8") as jsonl_file:
            writer = csv.DictWriter(csv_file, fieldnames=fields)
            writer.writeheader()
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                current = frame_index
                frame_index += 1
                if current % args.sample_every:
                    continue
                wait = delay - (time.monotonic() - previous_send)
                if previous_send and wait > 0:
                    time.sleep(wait)
                previous_send = time.monotonic()
                ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                row: dict[str, Any] = {
                    "frame": current,
                    "video_time_seconds": round(current / fps, 3) if fps > 0 else "",
                    "http_status": "",
                    "bus_detected": "",
                    "route": "",
                    "direction": "",
                    "message": "",
                    "error": "",
                }
                result: dict[str, Any]
                if not ok:
                    failed += 1
                    row["error"] = "JPEG encoding failed"
                    result = {"error": row["error"]}
                else:
                    try:
                        status, result = request_frame(
                            endpoint, session_id, f"frame_{current:08d}.jpg",
                            encoded.tobytes(), args.api_key, args.timeout
                        )
                        row["http_status"] = status
                        objects = result.get("objects", [])
                        if isinstance(objects, list):
                            buses = [obj for obj in objects if isinstance(obj, dict)
                                     and str(obj.get("label", obj.get("class_name", ""))).lower() == "bus"]
                            row["bus_detected"] = bool(buses)
                            if buses:
                                bus = buses[0]
                                row["route"] = first_value(bus, ("route", "route_number", "bus_route", "route_code"))
                                row["direction"] = first_value(bus, ("direction", "destination", "route_direction"))
                        row["message"] = first_value(result, ("message", "speech", "speech_text", "alert"))
                        if status >= 400:
                            failed += 1
                            row["error"] = json.dumps(result, ensure_ascii=False)
                    except Exception as exc:  # preserve per-frame failures in the report
                        failed += 1
                        result = {"error": str(exc)}
                        row["error"] = str(exc)
                writer.writerow(row)
                csv_file.flush()
                jsonl_file.write(json.dumps({"row": row, "response": result}, ensure_ascii=False) + "\n")
                jsonl_file.flush()
                sent += 1
                if row["error"]:
                    print(f"Frame {current}: error: {row['error']}")
                else:
                    print(f"Frame {current}: HTTP {row['http_status']}; bus={row['bus_detected']}; "
                          f"route={row['route'] or '—'}; direction={row['direction'] or '—'}")
    except KeyboardInterrupt:
        print("Replay stopped by user; results saved for frames already processed.")
    finally:
        capture.release()

    print(f"\nReplay complete: sent {sent} sampled frames, {failed} failed.")
    print(f"CSV summary: {csv_path.resolve()}")
    print(f"Full responses: {jsonl_path.resolve()}")
    return 0 if sent and not failed else 1


if __name__ == "__main__":
    sys.exit(main())
