import cv2
import numpy as np
import csv
import sys
import os
import onnxruntime as ort
from datetime import datetime, timezone
from pathlib import Path
from ultralytics import YOLO

from pipeline.config import PipelineConfig

# ---------------------------------------------------------------------------
#  Defaults
# ---------------------------------------------------------------------------
CSV_COLS = [
    "timestamp",
    "frame_number",
    "track_id",
    "class",
    "distance_m",
    "midas_disparity_50_pct",
    "median_50_pct",
    "median_30_pct",
    "median_20_pct",
    "median_full",
    "bbox_xyxy"
]

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

# ===========================================================================
#  DEPTH SAMPLING
# ===========================================================================
def sample_bbox_region(depth_map: np.ndarray, bbox_xyxy: tuple, percent: float):
    h, w = depth_map.shape[:2]
    x1, y1, x2, y2 = bbox_xyxy
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(w, int(x2)), min(h, int(y2))
    
    if x2 <= x1 or y2 <= y1:
        return None
        
    bw, bh = x2 - x1, y2 - y1
    
    if percent >= 1.0:
        roi = depth_map[y1:y2, x1:x2]
    else:
        margin_x = int(bw * (1.0 - percent) / 2)
        margin_y = int(bh * (1.0 - percent) / 2)
        roi = depth_map[y1+margin_y:y2-margin_y, x1+margin_x:x2-margin_x]
        
    if roi.size == 0:
        return None
        
    valid = roi[np.isfinite(roi) & (roi > 0)]
    if valid.size == 0:
        return None
    return float(np.median(valid))

# ===========================================================================
#  MIDAS RAW DISPARITY 
# ===========================================================================
_MEAN_255 = np.array([0.485 * 255, 0.456 * 255, 0.406 * 255], dtype=np.float32)
_STD_255  = np.array([0.229 * 255, 0.224 * 255, 0.225 * 255], dtype=np.float32)
_NORM_BUF = np.empty((256, 256, 3), dtype=np.float32)

def midas_raw_disparity(frame_bgr: np.ndarray, session, input_name: str) -> np.ndarray:
    h, w = frame_bgr.shape[:2]
    resized = cv2.resize(frame_bgr, (256, 256), interpolation=cv2.INTER_CUBIC)
    rgb = resized[:, :, ::-1]  # BGR->RGB
    np.subtract(rgb, _MEAN_255, out=_NORM_BUF, casting="unsafe")
    np.divide(_NORM_BUF, _STD_255, out=_NORM_BUF)
    tensor = np.ascontiguousarray(_NORM_BUF.transpose(2, 0, 1))[np.newaxis, ...]
    prediction = session.run(None, {input_name: tensor})[0][0]
    depth = cv2.resize(prediction, (w, h), interpolation=cv2.INTER_LINEAR)
    return depth.astype(np.float32)

def print_summary(distances_data: dict):
    print("\n" + "="*80)
    print("DATA COLLECTION SUMMARY")
    print("="*80)
    
    for dist, samples in distances_data.items():
        print(f"\nDistance: {dist} m | Valid Samples: {len(samples)}")
        metrics = ["median_full", "median_50_pct", "median_30_pct", "median_20_pct"]
        
        for m in metrics:
            vals = [s[m] for s in samples if s[m] is not None]
            if not vals:
                continue
            arr = np.array(vals)
            mean_val = arr.mean()
            std_val = arr.std()
            cv = (std_val / mean_val * 100) if mean_val > 0 else 0
            
            print(f"  {m:>15} -> Mean: {mean_val:6.1f} | Median: {np.median(arr):6.1f} | "
                  f"Std: {std_val:5.1f} | CV: {cv:5.1f}% | Min: {arr.min():6.1f} | Max: {arr.max():6.1f}")
    print("="*80 + "\n")


def main():
    cfg = PipelineConfig()
    
    # Files
    base_csv = Path("physical_calibration_raw.csv")
    if base_csv.exists():
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = Path(f"physical_calibration_raw_{timestamp_str}.csv")
        print(f"Dataset 'physical_calibration_raw.csv' already exists.")
        print(f"Creating a new dataset: {csv_path}")
    else:
        csv_path = base_csv
    model_path = Path(cfg.midas_onnx_model_path)
    
    if not model_path.exists():
        sys.exit(f"ERROR: Model not found at {model_path}")
        
    print("\n--- INSTRUCTIONS ---")
    print("1. Measure the distance with a measuring tape. Do not estimate.")
    print("2. Keep the same person and approximately the same body orientation.")
    print("3. Keep the camera fixed.")
    print("4. Measure from camera lens to torso center.")
    print("5. Test distances if possible: 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0 m")
    print("--------------------\n")

    # Load Model
    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(str(model_path), sess_options=opts, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    
    # Load YOLO
    yolo = YOLO(cfg.yolo_model)
    
    cap = cv2.VideoCapture(cfg.camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        sys.exit("ERROR: Could not open webcam.")
        
    ensure_csv(csv_path)
    
    print("Camera active. Controls:")
    print("  SPACE -> Enter a new distance and record 30 samples")
    print("  Q     -> Quit and generate summary\n")

    distances_data = {}
    collecting = False
    current_dist_m = None
    target_track_id = None
    samples_collected = []
    
    frame_number = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            frame_number += 1
                
            # Run YOLO Tracking
            results = yolo.track(frame, persist=True, conf=cfg.detection_conf, verbose=False)[0]
            
            best_det = None
            if results.boxes is not None and len(results.boxes) > 0:
                best_area = -1
                for i in range(len(results.boxes)):
                    cls_name = results.names[int(results.boxes.cls[i])]
                    if cls_name not in cfg.target_classes:
                        continue
                    if results.boxes.id is None:
                        continue
                        
                    tid = int(results.boxes.id[i])
                    x1, y1, x2, y2 = results.boxes.xyxy[i].tolist()
                    area = (x2-x1)*(y2-y1)
                    
                    # If we are collecting and have locked onto a track_id, only accept that ID.
                    if collecting and target_track_id is not None:
                        if tid == target_track_id:
                            best_det = (tid, cls_name, (x1, y1, x2, y2))
                            break
                    else:
                        if area > best_area:
                            best_area = area
                            best_det = (tid, cls_name, (x1, y1, x2, y2))
                            
            depth_map = midas_raw_disparity(frame, session, input_name)
            
            vis = frame.copy()
            
            if best_det is not None:
                tid, cls_name, bbox = best_det
                x1, y1, x2, y2 = map(int, bbox)
                cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(vis, f"ID:{tid} {cls_name}", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                
                if collecting and current_dist_m is not None:
                    # Lock onto this track ID if not locked
                    if target_track_id is None:
                        target_track_id = tid
                        print(f"Locked onto Track ID {target_track_id}")
                        
                    # Sample values
                    val_full = sample_bbox_region(depth_map, bbox, 1.0)
                    val_50 = sample_bbox_region(depth_map, bbox, 0.5)
                    val_30 = sample_bbox_region(depth_map, bbox, 0.3)
                    val_20 = sample_bbox_region(depth_map, bbox, 0.2)
                    
                    # Reject invalid
                    if (val_50 is not None and not np.isnan(val_50) and not np.isinf(val_50) and val_50 > 0):
                        row = {
                            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                            "frame_number": frame_number,
                            "track_id": tid,
                            "class": cls_name,
                            "distance_m": current_dist_m,
                            "midas_disparity_50_pct": val_50,
                            "median_50_pct": val_50,
                            "median_30_pct": val_30,
                            "median_20_pct": val_20,
                            "median_full": val_full,
                            "bbox_xyxy": f"[{x1},{y1},{x2},{y2}]"
                        }
                        samples_collected.append(row)
                        
                        cv2.putText(vis, f"Collected: {len(samples_collected)}/30", (x1, y2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                    else:
                        if collecting:
                            print("\nTARGET INVALID (DEPTH) - COLLECTION ABORTED")
                            cv2.putText(vis, "TARGET INVALID - ABORTED", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
                            collecting = False
                            current_dist_m = None
                            target_track_id = None
                            samples_collected = []
                            print("Press SPACE to restart distance collection or Q to finish.")
            else:
                if collecting:
                    print("\nTARGET LOST - COLLECTION ABORTED")
                    cv2.putText(vis, "TARGET LOST - COLLECTION ABORTED", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
                    collecting = False
                    current_dist_m = None
                    target_track_id = None
                    samples_collected = []
                    print("Press SPACE to restart distance collection or Q to finish.")

            # Check completion
            if collecting and len(samples_collected) >= 30:
                print(f"\nSuccessfully collected 30 consecutive samples for {current_dist_m}m.")
                
                # Write the 30 consecutive samples to CSV only upon success
                for row in samples_collected:
                    append_row(csv_path, row)
                
                if current_dist_m not in distances_data:
                    distances_data[current_dist_m] = []
                distances_data[current_dist_m].extend(samples_collected)
                
                collecting = False
                current_dist_m = None
                target_track_id = None
                samples_collected = []
                print("Move to next distance. Press SPACE to continue or Q to finish.")
                
            status = f"Ready (Q to quit)" if not collecting else f"Recording {current_dist_m}m: {len(samples_collected)}/30"
            cv2.putText(vis, status, (10, vis.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.imshow("Real-World Calibration Collector", vis)
            
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), ord('Q')):
                break
            elif key == ord(' ') and not collecting:
                cv2.destroyAllWindows()
                dist_str = input("Enter measured physical distance in meters (e.g. 1.5): ").strip()
                try:
                    current_dist_m = float(dist_str)
                    if current_dist_m <= 0:
                        raise ValueError
                    collecting = True
                    target_track_id = None
                    samples_collected = []
                    print(f"Collecting 30 samples for {current_dist_m}m. Please ensure target is steady.")
                except:
                    print("Invalid distance.")
                    
    finally:
        cap.release()
        cv2.destroyAllWindows()
        if distances_data:
            print_summary(distances_data)

if __name__ == '__main__':
    main()
