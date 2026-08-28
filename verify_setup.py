"""Verify VisionNav Phase 1 environment setup."""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).parent
REQUIRED_PACKAGES = [
    ("ultralytics", "YOLOv8"),
    ("cv2", "OpenCV"),
    ("fastapi", "FastAPI"),
    ("uvicorn", "Uvicorn"),
    ("torch", "PyTorch"),
    ("timm", "MiDaS dependency"),
]
REQUIRED_FILES = [
    "yolov8n.pt",
    "main.py",
    "detect_image.py",
    "detect_folder.py",
    "depth_test.py",
    "camera_detect.py",
    "requirements.txt",
]
REQUIRED_DIRS = [
    "data/raw",
    "data/annotated",
    "runs",
]


def check_package(module_name: str, label: str) -> tuple[bool, str]:
    try:
        mod = importlib.import_module(module_name)
        version = getattr(mod, "__version__", "installed")
        return True, f"{label} ({version})"
    except ImportError as exc:
        return False, f"{label} missing: {exc}"


def main():
    print("VisionNav - Phase 1 Environment Check\n")
    ok = True

    print("Python packages:")
    for module_name, label in REQUIRED_PACKAGES:
        passed, message = check_package(module_name, label)
        print(f"  [{'OK' if passed else 'FAIL'}] {message}")
        ok = ok and passed

    print("\nProject files:")
    for rel_path in REQUIRED_FILES:
        exists = (ROOT / rel_path).exists()
        print(f"  [{'OK' if exists else 'FAIL'}] {rel_path}")
        ok = ok and exists

    print("\nProject folders:")
    for rel_path in REQUIRED_DIRS:
        exists = (ROOT / rel_path).exists()
        print(f"  [{'OK' if exists else 'FAIL'}] {rel_path}")
        ok = ok and exists

    print("\nCamera:")
    try:
        import cv2

        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                h, w = frame.shape[:2]
                print(f"  [OK] Webcam accessible ({w}x{h})")
            else:
                print("  [FAIL] Webcam opened but could not read a frame")
                ok = False
        else:
            print("  [FAIL] No webcam detected")
            ok = False
        cap.release()
    except Exception as exc:
        print(f"  [FAIL] Camera check error: {exc}")
        ok = False

    print()
    if ok:
        print("Phase 1 COMPLETE: environment + camera integration ready.")
        return 0

    print("Phase 1 INCOMPLETE: fix the failed checks above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
