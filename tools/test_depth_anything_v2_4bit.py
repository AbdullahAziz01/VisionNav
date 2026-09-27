"""Standalone test for the local 4-bit Depth Anything V2 Metric Outdoor Small model.

Does NOT import or modify the VisionNav pipeline / existing depth backend.

Usage (from repo root):
    python tools/test_depth_anything_v2_4bit.py
    python tools/test_depth_anything_v2_4bit.py path/to/image.jpg
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models" / "depth_anything_v2_metric_outdoor_small_4bit"
OUT_VIS = ROOT / "runs" / "debug" / "depth_anything_v2_4bit_vis.png"

WARMUP_RUNS = 2
TIMED_RUNS = 10


def _find_image(argv: list[str]) -> Path:
    candidates: list[Path] = []
    if len(argv) > 1:
        candidates.append(Path(argv[1]))
    candidates.extend(
        [
            ROOT / "test.jpg",
            ROOT / "runs" / "debug" / "test_depth_bgr.jpg",
            ROOT / "runs" / "debug" / "test_depth_rgb.jpg",
        ]
    )
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "No test image found. Pass a path: python tools/test_depth_anything_v2_4bit.py image.jpg"
    )


def _device_of(model: torch.nn.Module) -> torch.device:
    try:
        return next(model.parameters()).device
    except StopIteration:
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def main() -> int:
    print("=== Depth Anything V2 4-bit standalone test ===")
    print(f"python     : {sys.executable}")
    print(f"torch      : {torch.__version__}")
    print(f"cuda       : {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"gpu        : {torch.cuda.get_device_name(0)}")
    print(f"model dir  : {MODEL_DIR}")

    if not MODEL_DIR.is_dir():
        print(f"ERROR: model folder not found: {MODEL_DIR}")
        return 1

    try:
        import bitsandbytes as bnb  # noqa: F401
        import transformers
        from transformers import (
            AutoImageProcessor,
            AutoModelForDepthEstimation,
            BitsAndBytesConfig,
        )

        print(f"transformers: {transformers.__version__}")
        print(f"bitsandbytes: {bnb.__version__}")
    except ImportError as exc:
        print(f"ERROR: missing dependency: {exc}")
        print("Install with: pip install bitsandbytes accelerate")
        return 1

    image_path = _find_image(sys.argv)
    print(f"image      : {image_path}")
    pil_image = Image.open(image_path).convert("RGB")
    print(f"image size : {pil_image.size[0]}x{pil_image.size[1]} (WxH)")

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=False,
    )

    print("Loading processor + 4-bit model...", flush=True)
    t_load = time.perf_counter()
    processor = AutoImageProcessor.from_pretrained(str(MODEL_DIR))
    # device_map="auto" can hang on CPU-only Windows; the saved 4-bit
    # checkpoint already carries quantization_config and loads on CPU.
    model = AutoModelForDepthEstimation.from_pretrained(
        str(MODEL_DIR),
        quantization_config=quant_config,
    )
    model.eval()
    print(f"load time  : {time.perf_counter() - t_load:.2f}s", flush=True)
    device = _device_of(model)
    print(f"model device: {device}", flush=True)

    inputs = processor(images=pil_image, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}

    def run_once() -> tuple[torch.Tensor, float]:
        if device.type == "cuda":
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        with torch.no_grad():
            outputs = model(**inputs)
        if device.type == "cuda":
            torch.cuda.synchronize()
        elapsed = time.perf_counter() - t0
        return outputs.predicted_depth, elapsed

    print(f"Warmup ({WARMUP_RUNS})...")
    depth = None
    for _ in range(WARMUP_RUNS):
        depth, _ = run_once()

    times: list[float] = []
    print(f"Timed runs ({TIMED_RUNS})...")
    for _ in range(TIMED_RUNS):
        depth, elapsed = run_once()
        times.append(elapsed)

    assert depth is not None
    depth_np = depth.detach().float().cpu().numpy()
    valid = depth_np[np.isfinite(depth_np)]
    avg = float(np.mean(times))
    fps = (1.0 / avg) if avg > 0 else 0.0

    print("--- result ---")
    print(f"depth tensor shape : {tuple(depth_np.shape)}")
    print(f"min                : {float(valid.min()):.4f}")
    print(f"max                : {float(valid.max()):.4f}")
    print(f"mean               : {float(valid.mean()):.4f}")
    print(f"median             : {float(np.median(valid)):.4f}")
    print(f"runs               : {TIMED_RUNS}")
    print(f"latencies_s        : {[round(t, 4) for t in times]}")
    print(f"avg latency        : {avg * 1000:.2f} ms")
    print(f"FPS                : {fps:.2f}")

    # Upsample to original image size for a readable visualization.
    vis_src = torch.from_numpy(depth_np)
    if vis_src.ndim == 2:
        vis_src = vis_src.unsqueeze(0).unsqueeze(0)
    elif vis_src.ndim == 3:
        vis_src = vis_src.unsqueeze(1) if vis_src.shape[0] == 1 else vis_src.unsqueeze(0)
    vis = (
        torch.nn.functional.interpolate(
            vis_src.float(),
            size=(pil_image.size[1], pil_image.size[0]),
            mode="bicubic",
            align_corners=False,
        )
        .squeeze()
        .numpy()
    )
    vis = vis.astype(np.float32)
    # Cap vis resolution so a huge source photo (e.g. 6000px) does not dominate I/O.
    max_side = 1280
    h, w = vis.shape[:2]
    if max(h, w) > max_side:
        scale = max_side / float(max(h, w))
        vis = cv2.resize(
            vis,
            (int(w * scale), int(h * scale)),
            interpolation=cv2.INTER_AREA,
        )
    vmin, vmax = float(np.nanmin(vis)), float(np.nanmax(vis))
    norm = np.zeros_like(vis, dtype=np.uint8) if vmax <= vmin else (
        (vis - vmin) / (vmax - vmin) * 255.0
    ).clip(0, 255).astype(np.uint8)
    color = cv2.applyColorMap(norm, cv2.COLORMAP_INFERNO)
    OUT_VIS.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT_VIS), color)
    print(f"saved vis          : {OUT_VIS}")
    print("=== done ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
