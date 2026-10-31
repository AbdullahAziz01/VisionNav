"""Pre-download and warm-up the models VisionNav actually uses in production.

Downloads and caches:
1. YOLOv8n object detection weights (Ultralytics)
2. Depth Anything V2 Metric (Hugging Face id from pipeline.config)
3. EasyOCR English detector + recognizer

Does not download unused MiDaS ONNX weights. Host checkout files such as
yolov8n.pt or model-small.onnx are not required.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _weights_root() -> Path | None:
    raw = os.environ.get("WEIGHTS_ROOT", "").strip()
    return Path(raw) if raw else None


def prepare_yolo() -> Path:
    print("[1/3] Preparing YOLOv8n model...")
    from ultralytics import YOLO

    # Ultralytics downloads the published yolov8n checkpoint when the file is
    # absent. Do not require a gitignored local copy.
    model = YOLO("yolov8n.pt")
    downloaded = Path("yolov8n.pt").resolve()
    if not downloaded.is_file():
        downloaded = PROJECT_ROOT / "yolov8n.pt"
    if not downloaded.is_file():
        raise FileNotFoundError("YOLO did not produce yolov8n.pt after load")

    root = _weights_root()
    if root is not None:
        dest = root / "yolo" / "yolov8n.pt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if downloaded.resolve() != dest.resolve():
            shutil.copy2(downloaded, dest)
        print(f"      YOLOv8n ready ({dest}).")
        return dest
    print(f"      YOLOv8n ready ({downloaded}).")
    return downloaded


def prepare_depth_anything() -> None:
    print("[2/3] Preparing Depth Anything V2 Metric model...")
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation
    from pipeline.config import DEPTH_ANYTHING_MODEL

    model_id = os.environ.get("DEPTH_ANYTHING_MODEL", DEPTH_ANYTHING_MODEL)
    print(f"      Downloading/caching from Hugging Face: {model_id}...")
    AutoImageProcessor.from_pretrained(model_id)
    AutoModelForDepthEstimation.from_pretrained(model_id)
    print("      Depth Anything V2 weights cached.")


def prepare_easyocr() -> None:
    print("[3/3] Preparing EasyOCR models (detector + recognizer)...")
    import easyocr

    cache_dir = os.environ.get("EASYOCR_MODULE_PATH")
    kwargs: dict = {"gpu": False}
    if cache_dir:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        model_dir = Path(cache_dir) / "model"
        model_dir.mkdir(parents=True, exist_ok=True)
        kwargs["model_storage_directory"] = str(model_dir)
        kwargs["user_network_directory"] = str(model_dir)

    easyocr.Reader(["en"], **kwargs)
    print("      EasyOCR models cached.")


def main() -> None:
    print("==================================================")
    print(" VisionNav Deployment: Weight Preparation Utility")
    print("==================================================")
    print(f"Project Root:  {PROJECT_ROOT}")
    print(f"Weights Root:  {os.environ.get('WEIGHTS_ROOT', '(runtime defaults)')}")
    print(f"HF Cache:      {os.environ.get('HF_HOME', 'Default (~/.cache/huggingface)')}")
    print(f"Torch Cache:   {os.environ.get('TORCH_HOME', 'Default (~/.cache/torch)')}")
    print(f"EasyOCR Cache: {os.environ.get('EASYOCR_MODULE_PATH', 'Default (~/.EasyOCR)')}")
    print("--------------------------------------------------")

    try:
        prepare_yolo()
        prepare_depth_anything()
        prepare_easyocr()
        print("--------------------------------------------------")
        print("All models downloaded and verified successfully!")
        print("Backend is ready for immediate, offline container startup.")
    except Exception as e:
        print(f"ERROR preparing weights: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
