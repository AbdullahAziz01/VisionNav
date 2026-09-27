"""
VisionNav - Single image detection
Usage: python detect_image.py path/to/image.jpg
"""
import sys
from pathlib import Path

from ultralytics import YOLO

MODEL = "yolov8n.pt"
CONF = 0.4
# Classes relevant to VisionNav (COCO names)
TARGET_CLASSES = {"person", "bicycle", "car", "motorcycle", "bus", "truck"}


def main():
    if len(sys.argv) < 2:
        print("Usage: python detect_image.py <image_path>")
        sys.exit(1)

    image_path = Path(sys.argv[1])
    if not image_path.exists():
        print(f"File not found: {image_path}")
        sys.exit(1)

    model = YOLO(MODEL)
    results = model.predict(str(image_path), conf=CONF, save=True, verbose=False)[0]

    print(f"\nImage: {image_path.name}")
    print(f"Total detections: {len(results.boxes)}")

    for box in results.boxes:
        name = results.names[int(box.cls)]
        conf = float(box.conf)
        marker = " [VisionNav]" if name in TARGET_CLASSES else ""
        print(f"  - {name}: {conf:.0%}{marker}")

    print(f"\nSaved to: runs/detect/predict/")


if __name__ == "__main__":
    main()
