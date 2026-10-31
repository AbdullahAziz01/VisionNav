"""Merge baked model weights into runtime cache dirs without overwriting.

Used as the container entrypoint helper so Docker volumes (which hide
image-layer files under /app/cache) start with YOLO, Depth Anything V2, and
EasyOCR weights prepared at image build time. Missing files are added at
startup, while existing files are never overwritten.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

DEFAULT_WEIGHTS_ROOT = Path("/opt/visionnav-weights")


def seed_directory(src: Path, dest: Path) -> bool:
    """Copy missing files from *src* into *dest* without overwriting files."""
    if not src.exists() or not src.is_dir():
        return False

    dest.mkdir(parents=True, exist_ok=True)
    copied_any = False
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            copied_any = seed_directory(item, target) or copied_any
        elif item.is_file():
            copied_any = seed_file(item, target) or copied_any
    return copied_any


def seed_file(src: Path, dest: Path) -> bool:
    """Copy a single file if the destination does not already exist."""
    if not src.is_file() or dest.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return True


def seed_runtime_caches(
    weights_root: Path | None = None,
    hf_home: Path | None = None,
    torch_home: Path | None = None,
    easyocr_home: Path | None = None,
    yolo_dest: Path | None = None,
    config_dest: Path | None = None,
) -> dict[str, bool]:
    root = Path(weights_root or os.environ.get("WEIGHTS_ROOT", DEFAULT_WEIGHTS_ROOT))
    hf = Path(hf_home or os.environ.get("HF_HOME", "/app/cache/huggingface"))
    torch = Path(torch_home or os.environ.get("TORCH_HOME", "/app/cache/torch"))
    easyocr = Path(
        easyocr_home or os.environ.get("EASYOCR_MODULE_PATH", "/app/cache/easyocr")
    )
    yolo = Path(yolo_dest or os.environ.get("YOLO_WEIGHTS_PATH", "/app/yolov8n.pt"))
    config = Path(config_dest or os.environ.get("VISIONNAV_CONFIG_DIR", "/app/config"))

    seeded = {
        "huggingface": seed_directory(root / "huggingface", hf),
        "torch": seed_directory(root / "torch", torch),
        "easyocr": seed_directory(root / "easyocr", easyocr),
        "yolo": seed_file(root / "yolo" / "yolov8n.pt", yolo),
        "config": False,
    }

    baked_config = root / "config"
    if baked_config.is_dir():
        config.mkdir(parents=True, exist_ok=True)
        copied_any = False
        for item in baked_config.iterdir():
            if item.is_file() and seed_file(item, config / item.name):
                copied_any = True
        seeded["config"] = copied_any
    return seeded


def main() -> None:
    result = seed_runtime_caches()
    copied = [name for name, did in result.items() if did]
    if copied:
        print("Seeded empty runtime caches from baked weights:", ", ".join(copied))
    else:
        print("Runtime caches already populated; leaving existing files in place.")


if __name__ == "__main__":
    main()
