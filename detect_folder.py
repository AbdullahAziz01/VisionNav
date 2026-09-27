"""
VisionNav - Batch detection on all images in a folder
Usage: python detect_folder.py data/raw
"""
import sys
from pathlib import Path

from ultralytics import YOLO

MODEL = "yolov8n.pt"
CONF = 0.4
TARGET_CLASSES = {"person", "bicycle", "car", "motorcycle", "bus", "truck"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def main():
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw")
    if not folder.exists():
        print(f"Folder not found: {folder}")
        print("Create it and add photos: data/raw/")
        sys.exit(1)

    images = [f for f in folder.iterdir() if f.suffix.lower() in IMAGE_EXT]
    if not images:
        print(f"No images in {folder}")
        sys.exit(1)

    model = YOLO(MODEL)
    print(f"Processing {len(images)} images...\n")

    summary = {c: 0 for c in TARGET_CLASSES}
    for img in images:
        results = model.predict(str(img), conf=CONF, save=True, verbose=False)[0]
        found = []
        for box in results.boxes:
            name = results.names[int(box.cls)]
            if name in TARGET_CLASSES:
                summary[name] += 1
                found.append(name)
        status = ", ".join(found) if found else "nothing relevant"
        print(f"  {img.name}: {status}")

    print("\n--- Summary (VisionNav classes) ---")
    for cls, count in summary.items():
        print(f"  {cls}: {count} detections across all images")


if __name__ == "__main__":
    main()
