"""
Run the full VisionNav pipeline on webcam, image, or video.

Usage:
  python run_pipeline.py                  # webcam
  python run_pipeline.py test.jpg         # single image (tracking IDs may be ephemeral)
  python run_pipeline.py --eval-csv gt.csv  # TODO: MAE/RMSE evaluation hook
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2

from pipeline import PipelineConfig, VisionNavPipeline
from pipeline.config import DEBUG_SNAPSHOT_DIR


def run_webcam(pipeline: VisionNavPipeline):
    from pipeline.camera import open_camera

    cap = open_camera(pipeline.config.camera_index)
    if not cap.isOpened():
        print("Could not open webcam.")
        return 1

    print(f"Mode: {pipeline.active_mode}")
    print(f"Depth backend: {pipeline.mono_depth.name if pipeline.active_mode == 'monocular' else pipeline.stereo_depth.name}")
    print(f"Tracker: {pipeline.tracker.name}")
    print("Press Q to quit.\n")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            stereo_pair = pipeline._read_stereo_frames() if pipeline.stereo_status.available else None
            result = pipeline.process_frame(frame, stereo_pair=stereo_pair)

            for line in result.format_lines():
                print(line)
            print()

            display = frame.copy()
            for obj in result.objects:
                x1, y1, x2, y2 = map(int, obj.bbox_xyxy)
                cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"ID {obj.track_id} {obj.distance_label}"
                cv2.putText(display, label, (x1, max(y1 - 8, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

            cv2.imshow("VisionNav Pipeline", display)
            if cv2.waitKey(1) & 0xFF in (ord("q"), "Q"):
                break
    finally:
        cap.release()
        pipeline.release()
        cv2.destroyAllWindows()
    return 0


def run_image(pipeline: VisionNavPipeline, image_path: Path):
    frame = cv2.imread(str(image_path))
    if frame is None:
        print(f"Could not read image: {image_path}")
        return 1

    result = pipeline.process_frame(frame)
    for line in result.format_lines():
        print(line)
    print("\nDebug:", result.debug)
    return 0


def main():
    pipeline = VisionNavPipeline(PipelineConfig())

    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        return run_image(pipeline, Path(sys.argv[1]))

    DEBUG_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    return run_webcam(pipeline)


if __name__ == "__main__":
    raise SystemExit(main())
