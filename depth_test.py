"""LEGACY: MiDaS depth test — NOT used by the active VisionNav pipeline.

The active pipeline uses Depth Anything V2 / Metric3D / stereo backends instead.
Run: python run_pipeline.py
"""import sys
from pathlib import Path

import cv2
import numpy as np
import torch

MODEL_TYPE = "MiDaS_small"


def load_midas():
    model = torch.hub.load("intel-isl/MiDaS", MODEL_TYPE, trust_repo=True)
    transforms = torch.hub.load("intel-isl/MiDaS", "transforms", trust_repo=True)
    transform = transforms.small_transform

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()
    return model, transform, device


def estimate_depth(model, transform, device, image_path: Path):
    frame = cv2.imread(str(image_path))
    if frame is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    input_batch = transform(rgb).to(device)

    with torch.no_grad():
        prediction = model(input_batch)
        prediction = torch.nn.functional.interpolate(
            prediction.unsqueeze(1),
            size=frame.shape[:2],
            mode="bicubic",
            align_corners=False,
        ).squeeze()

    depth = prediction.cpu().numpy()
    depth_min, depth_max = depth.min(), depth.max()
    if depth_max - depth_min > 0:
        depth_vis = ((depth - depth_min) / (depth_max - depth_min) * 255).astype(np.uint8)
    else:
        depth_vis = np.zeros_like(depth, dtype=np.uint8)

    out_path = Path("runs/depth") / f"{image_path.stem}_depth.jpg"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), depth_vis)
    return out_path


def main():
    image_path = Path(sys.argv[1] if len(sys.argv) > 1 else "test.jpg")
    if not image_path.exists():
        print(f"Image not found: {image_path}")
        sys.exit(1)

    print(f"Loading {MODEL_TYPE}...")
    model, transform, device = load_midas()
    print(f"Device: {device}")

    out_path = estimate_depth(model, transform, device, image_path)
    print(f"Depth map saved to: {out_path}")


if __name__ == "__main__":
    main()
