# -*- coding: utf-8 -*-
"""
calibrate_depth.py  --  VisionNav MiDaS physical distance calibration tool
==========================================================================

USAGE
-----
  Collect samples interactively (webcam + YOLO + MiDaS):
    python calibrate_depth.py collect

  Fit the calibration model from an existing CSV:
    python calibrate_depth.py fit

  Self-test with synthetic data (no camera, no model needed):
    python calibrate_depth.py test

OPTIONS (apply to all sub-commands)
  --csv PATH        CSV file path       (default: data/depth_calibration.csv)
  --model PATH      ONNX model path     (default: model-small.onnx)
  --samples N       Frames per distance (default: 30)
  --conf FLOAT      YOLO confidence     (default: 0.25)

PHYSICAL PROCEDURE (collect)
----------------------------
1. Place a calibration target (a person is fine) at a KNOWN distance.
2. Measure that distance precisely with a tape measure (in metres).
3. Run:  python calibrate_depth.py collect
4. The live camera view opens.  Press SPACE when you are ready to record.
5. In the terminal, type the measured distance (e.g. 1.5) and press Enter.
6. Keep the target still while 30 frames of disparity are sampled.
7. After collection completes, move the target to the NEXT distance.
8. Repeat from step 4.
9. Press Q in the camera window to finish and save the CSV.

FITTING (fit)
-------------
After collecting >=3 distance points:
    python calibrate_depth.py fit

The model fitted is:
    1/Z = a * d + b       =>  Z = 1 / (a*d + b)

Where d = raw MiDaS disparity, Z = physical distance in metres.

Derived convenience parameters:
    s = 1/a               (replaces RELATIVE_DEPTH_SCALE_M in config)
    o = -b/a              (disparity offset)

The fitted values are REPORTED, not written into config.py automatically.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

# ---------------------------------------------------------------------------
#  Ensure the project root is on sys.path so `import pipeline` works.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
#  Defaults
# ---------------------------------------------------------------------------
DEFAULT_CSV = ROOT / "data" / "depth_calibration.csv"
DEFAULT_MODEL = ROOT / "model-small.onnx"
DEFAULT_SAMPLES = 30

CSV_COLS = [
    "distance_m",
    "disparity_median",
    "disparity_std",
    "disparity_min",
    "disparity_max",
    "num_samples",
    "num_rejected",
    "timestamp",
    "notes",
]


# ===========================================================================
#  DEPTH SAMPLING  (mirrors pipeline/distance/calculator._sample_bbox_depth)
# ===========================================================================

def sample_bbox_central_median(
    depth_map: np.ndarray,
    bbox_xyxy: tuple[float, float, float, float],
) -> float | None:
    """
    Median of the CENTRAL 50% of a bounding box in the depth map.
    Logic is byte-for-byte identical to
    pipeline/distance/calculator._sample_bbox_depth.
    """
    h, w = depth_map.shape[:2]
    x1, y1, x2, y2 = bbox_xyxy
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(w, int(x2)), min(h, int(y2))
    if x2 <= x1 or y2 <= y1:
        return None

    bw, bh = x2 - x1, y2 - y1
    cx1 = x1 + int(bw * 0.25)
    cx2 = x2 - int(bw * 0.25)
    cy1 = y1 + int(bh * 0.25)
    cy2 = y2 - int(bh * 0.25)
    roi = depth_map[cy1:cy2, cx1:cx2]
    if roi.size == 0:
        roi = depth_map[y1:y2, x1:x2]

    valid = roi[np.isfinite(roi) & (roi > 0)]
    if valid.size == 0:
        return None
    return float(np.median(valid))


# ===========================================================================
#  MIDAS RAW DISPARITY  (same preprocessing as midas_onnx.py)
# ===========================================================================

_MEAN_255 = np.array([0.485 * 255, 0.456 * 255, 0.406 * 255], dtype=np.float32)
_STD_255  = np.array([0.229 * 255, 0.224 * 255, 0.225 * 255], dtype=np.float32)
_NORM_BUF = np.empty((256, 256, 3), dtype=np.float32)


def midas_raw_disparity(
    frame_bgr: np.ndarray,
    session,
    input_name: str,
) -> np.ndarray:
    """
    Run MiDaS v2.1 Small ONNX and return the RAW disparity map (float32, HxW).
    Preprocessing is identical to MiDaSONNXBackend.estimate() in midas_onnx.py.
    scale / shift are NOT applied -- we need the raw values for calibration.
    """
    h, w = frame_bgr.shape[:2]
    resized = cv2.resize(frame_bgr, (256, 256), interpolation=cv2.INTER_CUBIC)
    rgb = resized[:, :, ::-1]  # BGR->RGB via view
    np.subtract(rgb, _MEAN_255, out=_NORM_BUF, casting="unsafe")
    np.divide(_NORM_BUF, _STD_255, out=_NORM_BUF)
    tensor = np.ascontiguousarray(_NORM_BUF.transpose(2, 0, 1))[np.newaxis, ...]
    prediction = session.run(None, {input_name: tensor})[0][0]
    depth = cv2.resize(prediction, (w, h), interpolation=cv2.INTER_LINEAR)
    return depth.astype(np.float32)


# ===========================================================================
#  YOLO DETECTION
# ===========================================================================

def detect_largest_target(
    frame_bgr: np.ndarray,
    yolo_model,
    target_classes: set[str],
    conf: float,
) -> tuple[tuple[float, float, float, float], str] | None:
    """
    Run YOLO and return (bbox_xyxy, class_name) for the largest detection
    matching any class in target_classes.  Returns None if nothing detected.
    """
    results = yolo_model(frame_bgr, conf=conf, verbose=False)[0]
    if results.boxes is None or len(results.boxes) == 0:
        return None

    best_area = -1.0
    best_box = None
    best_cls = ""
    boxes = results.boxes
    for i in range(len(boxes)):
        cls_name = results.names[int(boxes.cls[i])]
        if target_classes and cls_name not in target_classes:
            continue
        x1, y1, x2, y2 = boxes.xyxy[i].tolist()
        area = (x2 - x1) * (y2 - y1)
        if area > best_area:
            best_area = area
            best_box = (x1, y1, x2, y2)
            best_cls = cls_name
    if best_box is None:
        return None
    return best_box, best_cls


# ===========================================================================
#  CSV HELPERS
# ===========================================================================

def ensure_csv(csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if not csv_path.exists():
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLS)
            writer.writeheader()


def append_row(csv_path: Path, row: dict) -> None:
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLS)
        writer.writerow(row)


def load_csv(csv_path: Path) -> list[dict]:
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


# ===========================================================================
#  COLLECT  (interactive webcam session)
# ===========================================================================

def run_collection(
    csv_path: Path,
    model_path: Path,
    samples_per_dist: int,
    conf: float,
) -> None:
    """Interactive data-collection loop using webcam."""
    import onnxruntime as ort
    from pipeline.config import PipelineConfig

    cfg = PipelineConfig()
    target_classes = cfg.target_classes

    # -- Load MiDaS ONNX (same session options as production) ----------------
    print(f"\nLoading MiDaS ONNX: {model_path}")
    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.intra_op_num_threads = cfg.midas_onnx_intra_op_threads
    opts.inter_op_num_threads = cfg.midas_onnx_inter_op_threads
    opts.enable_mem_pattern = True
    opts.enable_cpu_mem_arena = True
    session = ort.InferenceSession(
        str(model_path),
        sess_options=opts,
        providers=["CPUExecutionProvider"],
    )
    input_name = session.get_inputs()[0].name

    # -- Load YOLO -----------------------------------------------------------
    from ultralytics import YOLO
    print(f"Loading YOLO: {cfg.yolo_model}")
    yolo = YOLO(cfg.yolo_model)

    # -- Open camera ---------------------------------------------------------
    print(f"Opening camera index {cfg.camera_index} ...")
    cap = cv2.VideoCapture(cfg.camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        sys.exit("ERROR: Could not open webcam.")

    ensure_csv(csv_path)
    print(f"\nCSV: {csv_path.resolve()}")
    print(f"Target classes: {sorted(target_classes)}")
    print(f"Samples per distance: {samples_per_dist}\n")
    print("=" * 60)
    print("CONTROLS")
    print("  SPACE  -> start collecting at a new distance")
    print("  Q      -> quit and save")
    print("=" * 60)

    collecting = False
    current_dist_m: float | None = None
    disparity_buf: list[float] = []
    rejected_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            # Run YOLO + MiDaS every frame for live visual feedback
            det = detect_largest_target(frame, yolo, target_classes, conf)
            depth_map = midas_raw_disparity(frame, session, input_name)

            disp_val: float | None = None
            det_class = ""
            bbox = None
            if det is not None:
                bbox, det_class = det
                disp_val = sample_bbox_central_median(depth_map, bbox)

            # -- Overlay -----------------------------------------------------
            vis = frame.copy()
            if bbox is not None:
                x1, y1, x2, y2 = map(int, bbox)
                # Full bbox (blue)
                cv2.rectangle(vis, (x1, y1), (x2, y2), (255, 100, 0), 2)
                # Central 50% region (green)
                bw, bh = x2 - x1, y2 - y1
                cv2.rectangle(
                    vis,
                    (x1 + bw // 4, y1 + bh // 4),
                    (x2 - bw // 4, y2 - bh // 4),
                    (0, 220, 60),
                    2,
                )
                label = f"{det_class}"
                if disp_val is not None:
                    label += f"  disp={disp_val:.1f}"
                cv2.putText(
                    vis, label, (x1, max(y1 - 8, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 60), 2,
                )
            else:
                cv2.putText(
                    vis, "No target detected", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 200), 2,
                )

            # -- Status bar --------------------------------------------------
            if collecting and current_dist_m is not None:
                count = len(disparity_buf)
                if disp_val is not None:
                    status = (
                        f"Recording @ {current_dist_m:.2f} m  "
                        f"[{count}/{samples_per_dist}]  disp={disp_val:.1f}"
                    )
                else:
                    status = (
                        f"Recording @ {current_dist_m:.2f} m  "
                        f"[{count}/{samples_per_dist}]  NO DETECTION"
                    )
                # Accumulate valid samples
                if disp_val is not None:
                    if np.isfinite(disp_val) and disp_val > 0:
                        disparity_buf.append(disp_val)
                    else:
                        rejected_count += 1
            else:
                status = "Press SPACE to record | Q to quit"

            cv2.putText(
                vis, status, (6, vis.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1,
                cv2.LINE_AA,
            )
            cv2.imshow("VisionNav Calibration", vis)

            # -- Save row when enough samples collected ----------------------
            if collecting and len(disparity_buf) >= samples_per_dist:
                arr = np.array(disparity_buf, dtype=np.float64)
                row = {
                    "distance_m":      f"{current_dist_m:.4f}",
                    "disparity_median": f"{float(np.median(arr)):.4f}",
                    "disparity_std":    f"{float(np.std(arr)):.4f}",
                    "disparity_min":    f"{float(arr.min()):.4f}",
                    "disparity_max":    f"{float(arr.max()):.4f}",
                    "num_samples":      len(disparity_buf),
                    "num_rejected":     rejected_count,
                    "timestamp":        datetime.now(timezone.utc).isoformat(
                                            timespec="seconds"),
                    "notes":            "",
                }
                append_row(csv_path, row)
                med = float(np.median(arr))
                std = float(np.std(arr))
                print(
                    f"\n  [OK] Saved: dist={current_dist_m:.2f} m  "
                    f"median_disp={med:.2f}  std={std:.2f}  "
                    f"rejected={rejected_count}"
                )
                print(f"       -> {csv_path}")
                # Reset for next distance
                collecting = False
                current_dist_m = None
                disparity_buf = []
                rejected_count = 0
                print(
                    "\nMove target to next distance.  "
                    "Press SPACE to collect | Q to quit.\n"
                )

            # -- Keyboard ----------------------------------------------------
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q")):
                print("\nCollection finished.")
                break
            elif key == ord(" ") and not collecting:
                # Prompt for distance in terminal
                cv2.destroyAllWindows()
                dist_str = input(
                    "  Enter known distance in metres (e.g. 1.5): "
                ).strip()
                try:
                    dist_m = float(dist_str)
                    if dist_m <= 0:
                        raise ValueError("Distance must be positive.")
                except ValueError as e:
                    print(f"  Invalid input: {e} -- skipping.")
                else:
                    current_dist_m = dist_m
                    collecting = True
                    disparity_buf = []
                    rejected_count = 0
                    print(
                        f"  Recording {samples_per_dist} samples "
                        f"at {dist_m:.2f} m ..."
                    )
    finally:
        cap.release()
        cv2.destroyAllWindows()


# ===========================================================================
#  FIT  (curve fitting + error analysis)
# ===========================================================================

def run_fitting(csv_path: Path) -> None:
    """
    Load calibration CSV, fit  1/Z = a*d + b  via least squares,
    compute error metrics, print full report.
    Does NOT modify config.py.
    """
    if not csv_path.exists():
        sys.exit(f"ERROR: CSV not found: {csv_path}")

    rows = load_csv(csv_path)
    if len(rows) < 2:
        sys.exit(
            f"ERROR: Need at least 2 calibration points; found {len(rows)}."
        )

    Z   = np.array([float(r["distance_m"])       for r in rows], dtype=np.float64)
    d   = np.array([float(r["disparity_median"])  for r in rows], dtype=np.float64)
    std = np.array([float(r["disparity_std"])     for r in rows], dtype=np.float64)
    n   = np.array([int(r["num_samples"])         for r in rows], dtype=int)

    print()
    print("=" * 60)
    print("CALIBRATION FIT  --  1/Z = a*d + b")
    print("=" * 60)

    # -- Sanity checks -------------------------------------------------------
    if np.any(d <= 0):
        print("  WARNING: Some disparity values <= 0 -- those rows are suspect.")
    if np.any(~np.isfinite(d)):
        print("  WARNING: Non-finite disparity values present -- check data.")

    # Monotonicity: closer objects should have HIGHER MiDaS disparity
    order = np.argsort(Z)
    d_sorted = d[order]
    diffs = np.diff(d_sorted)
    if np.all(diffs < 0):
        print("  OK  Monotonicity: disparity decreases with distance (expected).")
    elif np.all(diffs > 0):
        print(
            "  WARNING: disparity INCREASES with distance -- "
            "unexpected for MiDaS."
        )
    else:
        print(
            "  WARNING: disparity is NOT monotonic -- "
            "possible outliers or inconsistent measurements."
        )

    # -- Fit via ordinary least squares: inv_Z = a*d + b ---------------------
    inv_Z = 1.0 / Z
    A_mat = np.column_stack([d, np.ones_like(d)])  # design matrix [d | 1]
    coeffs, residuals, rank, sv = np.linalg.lstsq(A_mat, inv_Z, rcond=None)
    a, b = coeffs

    print()
    print("  Fitted coefficients:")
    print(f"    a = {a:.10f}   (slope)")
    print(f"    b = {b:.10f}   (intercept)")

    # -- Derived parameters ---------------------------------------------------
    if abs(a) < 1e-15:
        print("  WARNING: 'a' is near zero -- degenerate fit.")
        return

    s = 1.0 / a
    o = -b / a

    print()
    print("  Derived calibration parameters:")
    print(f"    s  = 1/a     = {s:.4f}")
    print(f"    o  = -b/a    = {o:.4f}")
    print()
    print(f"    Distance formula:  Z = 1 / (a*d + b)")
    print(f"                       Z = {s:.4f} / (d + {b/a:.4f})")
    print()
    print("    NOTE: Do NOT write these into config.py until you review")
    print("          the error analysis below.")

    # -- Denominator sanity ---------------------------------------------------
    denom = a * d + b
    if np.any(denom <= 0):
        bad = d[denom <= 0]
        print(
            f"\n  WARNING: fitted denominator (a*d+b) <= 0 for disparity "
            f"values {bad.tolist()} -- fit is INVALID there."
        )
    else:
        print(
            "\n  OK  Denominator (a*d+b) positive for all calibration points."
        )

    # -- Predictions and per-point errors -------------------------------------
    Z_pred = np.where(denom > 0, 1.0 / denom, np.nan)
    err = Z_pred - Z
    abs_err = np.abs(err)
    pct_err = 100.0 * abs_err / Z

    mae  = float(np.nanmean(abs_err))
    rmse = float(np.sqrt(np.nanmean(err ** 2)))
    mape = float(np.nanmean(pct_err))

    # R-squared on 1/Z
    inv_Z_pred = a * d + b
    ss_res = np.sum((inv_Z - inv_Z_pred) ** 2)
    ss_tot = np.sum((inv_Z - inv_Z.mean()) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    print()
    print("-" * 70)
    header = (
        f"  {'Dist(m)':>8}  {'Med.Disp':>9}  {'Std':>7}  "
        f"{'Pred Z(m)':>10}  {'Err(m)':>8}  {'Err%':>6}  {'N':>4}"
    )
    print(header)
    print("  " + "-" * 66)
    for i in range(len(rows)):
        p = Z_pred[i]
        e = err[i]
        pe = pct_err[i]
        flag = "  <- outlier?" if abs(pe) > 15 else ""
        print(
            f"  {Z[i]:8.2f}  {d[i]:9.1f}  {std[i]:7.2f}  "
            f"{p:10.3f}  {e:+8.3f}  {pe:5.1f}%  {n[i]:4d}{flag}"
        )
    print("  " + "-" * 66)

    print()
    print(f"  MAE  = {mae:.4f} m")
    print(f"  RMSE = {rmse:.4f} m")
    print(f"  MAPE = {mape:.2f} %")
    r2_verdict = "good" if r2 >= 0.99 else "poor -- collect more points"
    print(f"  R^2  = {r2:.6f}  ({r2_verdict})")

    if r2 < 0.95:
        print()
        print("  WARNING: R^2 < 0.95.  Possible causes:")
        print("    * Too few calibration points (need >= 4-6)")
        print("    * Significant measurement or positioning error")
        print("    * MiDaS output not well approximated by 1/Z = a*d + b")
        print("    -> Collect more points and re-run:  python calibrate_depth.py fit")

    # -- Outlier detection (3-sigma on 1/Z residuals) -------------------------
    residuals_lin = inv_Z - inv_Z_pred
    thresh = 3.0 * np.std(residuals_lin)
    outlier_idx = np.where(np.abs(residuals_lin) > thresh)[0]
    if len(outlier_idx):
        print()
        print("  Potential outliers (residual > 3-sigma):")
        for i in outlier_idx:
            print(f"    Row {i}: dist={Z[i]:.2f} m, disparity={d[i]:.2f}")
    else:
        print("\n  OK  No outliers detected (3-sigma criterion).")

    # -- Next step guidance ---------------------------------------------------
    print()
    print("=" * 60)
    print("NEXT STEP")
    print("-" * 60)
    print(f"  If the fit is satisfactory (R^2 >= 0.99, MAPE < 5%):")
    print(f"    Set in pipeline/config.py:")
    print(f"      RELATIVE_DEPTH_SCALE_M = {s:.4f}    # = 1/a")
    print(f"      MIDAS_ONNX_SHIFT       = {o:.4f}    # = -b/a")
    print(f"  Then re-run the live pipeline to verify distances.")
    print("=" * 60)
    print()


# ===========================================================================
#  TEST  (synthetic self-test, no camera or model needed)
# ===========================================================================

def run_test(csv_path: Path) -> None:
    """
    Create a test CSV with synthetic data and run the fitting step on it.
    Validates that CSV writing and curve-fitting logic work correctly.
    Ground truth:  d = 500/Z  =>  1/Z = (1/500)*d  =>  a=0.002, b=0
    """
    print()
    print("=" * 60)
    print("SELF-TEST -- synthetic data verification")
    print("=" * 60)

    TRUE_SCALE = 500.0  # true: Z = 500/d, so a = 1/500 = 0.002, b = 0
    distances = [1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0]
    rng = np.random.default_rng(42)

    # Use a separate test CSV to avoid polluting real data
    test_csv = csv_path.parent / ("test_" + csv_path.name)
    # Remove old test file if exists
    if test_csv.exists():
        test_csv.unlink()
    ensure_csv(test_csv)
    print(f"  Writing synthetic rows to: {test_csv.resolve()}")

    for Z in distances:
        true_d = TRUE_SCALE / Z
        samples = true_d + rng.normal(0, 5.0, size=30)
        samples = samples[samples > 0]  # keep positive
        med = float(np.median(samples))
        std_val = float(np.std(samples))
        row = {
            "distance_m":      f"{Z:.4f}",
            "disparity_median": f"{med:.4f}",
            "disparity_std":    f"{std_val:.4f}",
            "disparity_min":    f"{float(samples.min()):.4f}",
            "disparity_max":    f"{float(samples.max()):.4f}",
            "num_samples":      len(samples),
            "num_rejected":     0,
            "timestamp":        datetime.now(timezone.utc).isoformat(
                                    timespec="seconds"),
            "notes":            "synthetic_test",
        }
        append_row(test_csv, row)
        print(
            f"    dist={Z:5.1f} m  true_d={true_d:6.1f}  "
            f"sampled_median={med:6.1f}  std={std_val:.1f}"
        )

    print(f"\n  CSV written. Running fitting step ...\n")
    run_fitting(test_csv)
    print("  Self-test complete.\n")


# ===========================================================================
#  ARGUMENT PARSING + ENTRY POINT
# ===========================================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="VisionNav MiDaS physical distance calibration tool",
    )
    sub = p.add_subparsers(dest="command", help="Sub-command to run")

    # -- collect --
    c = sub.add_parser("collect", help="Interactive webcam collection session")
    c.add_argument(
        "--csv", default=str(DEFAULT_CSV), help="CSV output path"
    )
    c.add_argument(
        "--model", default=str(DEFAULT_MODEL), help="ONNX model path"
    )
    c.add_argument(
        "--samples", type=int, default=DEFAULT_SAMPLES,
        help="Frames per distance point",
    )
    c.add_argument(
        "--conf", type=float, default=0.25, help="YOLO confidence threshold"
    )

    # -- fit --
    f = sub.add_parser("fit", help="Fit calibration model from CSV")
    f.add_argument(
        "--csv", default=str(DEFAULT_CSV), help="CSV input path"
    )

    # -- test --
    t = sub.add_parser("test", help="Self-test with synthetic data")
    t.add_argument(
        "--csv", default=str(DEFAULT_CSV),
        help="Base CSV path (test_ prefix added automatically)",
    )

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        print(
            "\nRun one of: collect, fit, test\n"
            "Example:  python calibrate_depth.py collect\n"
        )
        sys.exit(0)

    csv_path = Path(args.csv)

    if args.command == "test":
        run_test(csv_path)
    elif args.command == "collect":
        model_path = Path(args.model)
        if not model_path.exists():
            sys.exit(
                f"ERROR: MiDaS ONNX model not found: {model_path.resolve()}\n"
                "Download from: https://github.com/isl-org/MiDaS/releases/"
                "download/v2_1/model-small.onnx"
            )
        run_collection(csv_path, model_path, args.samples, args.conf)
    elif args.command == "fit":
        run_fitting(csv_path)


if __name__ == "__main__":
    main()
