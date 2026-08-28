from pipeline.tracking.base import BaseTracker
from pipeline.tracking.byte_track import ByteTrackTracker
from pipeline.tracking.deep_sort import DeepSortTracker

__all__ = ["BaseTracker", "ByteTrackTracker", "DeepSortTracker", "create_tracker"]


def create_tracker(backend: str, model_path: str, conf: float, target_classes: set[str]) -> BaseTracker:
    if backend == "bytetrack":
        return ByteTrackTracker(model_path, conf=conf, target_classes=target_classes)
    if backend == "deepsort":
        return DeepSortTracker(model_path, conf=conf, target_classes=target_classes)
    raise ValueError(f"Unknown tracker backend: {backend}")
