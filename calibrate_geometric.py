# -*- coding: utf-8 -*-
"""
calibrate_geometric.py -- Calibrate GEOMETRIC_FOCAL_RATIO for VisionNav.

The geometric distance model is:
    Z = H_real * K / (bbox_height_px / image_height_px)
so, from one known sample:
    K = Z_true * (bbox_height_px / image_height_px) / H_real

USAGE
  python calibrate_geometric.py collect      # webcam + YOLO, interactive
  python calibrate_geometric.py test         # synthetic self-test, no camera

PROCEDURE (collect)
  1. Stand a person of KNOWN height, FULL BODY visible head-to-toe in frame.
  2. Measure the true distance (camera to person) with a tape measure.
  3. Press SPACE, type the distance (m) and the person height (m, default 1.70).
  4. 30 frames of bbox-height fraction are averaged into one K estimate.
  5. Repeat at 2-3 distances. Press Q to finish and see the recommended K.

Set the reported value in pipeline/config.py -> GEOMETRIC_FOCAL_RATIO.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

DEFAULT_HEIGHT_M = 1.70
SAMPLES_PER_POINT = 30


def _largest_target(frame_bgr, yolo, target_classes, conf):
    results = yolo(frame_bgr, conf=conf, verbose=False)[0]
    if results.boxes is None or len(results.boxes) == 0:
        return None
    best_area, best = -1.0, None
    for i in range(len(results.boxes)):
        cls_name = results.names[int(results.boxes.cls[i])]
        if target_classes and cls_name not in target_classes:
            continue
        x1, y1, x2, y2 = results.boxes.xyxy[i].tolist()
        area = (x2 - x1) * (y2 - y1)
        if area > best_area:
            best_area, best = area, ((x1, y1, x2, y2), cls_name)
    return best


def run_collection(conf: float = 0.25):
    from ultralytics import YOLO
    from pipeline.config import PipelineConfig

    cfg = PipelineConfig()
    yolo = YOLO(cfg.yolo_model)
    cap = cv2.VideoCapture(cfg.camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        sys.exit("ERROR: Could not open webcam.")

    print("\nControls: SPACE = record a distance point | Q = finish\n")
    k_estimates: list[float] = []
    collecting = False
    dist_m = None
    height_m = DEFAULT_HEIGHT_M
    fracs: list[float] = []

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            img_h = frame.shape[0]
            det = _largest_target(frame, yolo, cfg.target_classes, conf)

            vis = frame.copy()
            frac = None
            if det is not None:
                (x1, y1, x2, y2), cls_name = det
                frac = (y2 - y1) / img_h
                cv2.rectangle(vis, (int(x1), int(y1)), (int(x2), int(y2)), (0, 220, 60), 2)
                cv2.putText(vis, f"{cls_name} h_frac={frac:.3f}", (int(x1), max(int(y1) - 8, 14)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 60), 2)
                warn = "OK" if (y1 > 2 and y2 < img_h - 2) else "BODY CUT OFF - move back!"
                cv2.putText(vis, warn, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                            (0, 200, 0) if warn == "OK" else (0, 0, 220), 2)
            else:
                cv2.putText(vis, "No target", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 200), 2)

            if collecting and dist_m is not None:
                if frac is not None and frac > 0:
                    fracs.append(frac)
                cv2.putText(vis, f"Recording @ {dist_m:.2f}m [{len(fracs)}/{SAMPLES_PER_POINT}]",
                            (6, vis.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

            cv2.imshow("Geometric Calibration", vis)

            if collecting and len(fracs) >= SAMPLES_PER_POINT:
                med_frac = float(np.median(fracs))
                k = dist_m * med_frac / height_m
                k_estimates.append(k)
                print(f"  [OK] dist={dist_m:.2f}m height={height_m:.2f}m "
                      f"med_frac={med_frac:.4f}  ->  K={k:.4f}")
                collecting = False
                dist_m = None
                fracs = []
                print("  Move to next distance. SPACE to record | Q to finish.\n")

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q")):
                break
            elif key == ord(" ") and not collecting:
                cv2.destroyAllWindows()
                try:
                    dist_m = float(input("  Measured distance (m): ").strip())
                    h_in = input(f"  Person/object height (m) [{DEFAULT_HEIGHT_M}]: ").strip()
                    height_m = float(h_in) if h_in else DEFAULT_HEIGHT_M
                    if dist_m <= 0 or height_m <= 0:
                        raise ValueError
                    collecting = True
                    fracs = []
                    print(f"  Recording {SAMPLES_PER_POINT} samples...")
                except ValueError:
                    print("  Invalid input, skipping.")
                    dist_m = None
    finally:
        cap.release()
        cv2.destroyAllWindows()

    if k_estimates:
        k_arr = np.array(k_estimates)
        print("\n" + "=" * 50)
        print(f"  Points collected : {len(k_arr)}")
        print(f"  K per point      : {[round(x, 4) for x in k_estimates]}")
        print(f"  Recommended K    : {k_arr.mean():.4f}  (std {k_arr.std():.4f})")
        print("=" * 50)
        print("  Set in pipeline/config.py:")
        print(f"      GEOMETRIC_FOCAL_RATIO = {k_arr.mean():.4f}")
        print("=" * 50 + "\n")
    else:
        print("\nNo calibration points collected.\n")


def run_test():
    # Synthetic: true K=1.20, H=1.7. Build fractions for several distances.
    true_k, H = 1.20, 1.70
    print("\nSELF-TEST  (true K = 1.20)")
    ks = []
    for z in [1.0, 2.0, 3.0, 5.0]:
        frac = H * true_k / z            # invert the model
        k = z * frac / H                 # recover K
        ks.append(k)
        print(f"  Z={z:.1f}m  frac={frac:.4f}  recovered K={k:.4f}")
    print(f"  Mean recovered K = {np.mean(ks):.4f} (expected 1.20)\n")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "collect":
        run_collection()
    elif cmd == "test":
        run_test()
    else:
        print(__doc__)
        print("Run: python calibrate_geometric.py collect | test")


if __name__ == "__main__":
    main()
