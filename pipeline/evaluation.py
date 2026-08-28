"""Optional evaluation helpers for MAE/RMSE against ground-truth distances.

TODO:
  - Collect a small validation set with measured distances (tape measure / LiDAR).
  - Fill CSV columns: frame_id, track_id, class_name, gt_distance_m, pred_distance_m
  - Run: python -m pipeline.evaluation metrics.csv
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class DistanceMetrics:
    mae: float
    rmse: float
    count: int


def load_pairs(csv_path: Path) -> tuple[np.ndarray, np.ndarray]:
    gt, pred = [], []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            gt.append(float(row["gt_distance_m"]))
            pred.append(float(row["pred_distance_m"]))
    return np.array(gt, dtype=np.float32), np.array(pred, dtype=np.float32)


def compute_mae_rmse(gt: np.ndarray, pred: np.ndarray) -> DistanceMetrics:
    err = pred - gt
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    return DistanceMetrics(mae=mae, rmse=rmse, count=len(gt))


def evaluate_csv(csv_path: Path) -> DistanceMetrics:
    gt, pred = load_pairs(csv_path)
    return compute_mae_rmse(gt, pred)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.evaluation <csv_path>")
        sys.exit(1)
    
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Error: File not found: {path}")
        sys.exit(1)
        
    try:
        metrics = evaluate_csv(path)
        print(f"Evaluation Results for '{path.name}':")
        print(f"  Total Sample Pairs: {metrics.count}")
        print(f"  Mean Absolute Error (MAE): {metrics.mae:.3f} m")
        print(f"  Root Mean Squared Error (RMSE): {metrics.rmse:.3f} m")
    except Exception as e:
        print(f"Error during evaluation: {e}")
        sys.exit(1)

