"""ByteTrack tracker via Ultralytics YOLO tracking."""

from __future__ import annotations

import numpy as np
from ultralytics import YOLO

from pipeline.models import TrackedObject
from pipeline.tracking.base import BaseTracker


class ByteTrackTracker(BaseTracker):
    name = "bytetrack"

    def __init__(self, model_path: str, conf: float = 0.25, target_classes: set[str] | None = None):
        self.model = YOLO(model_path)
        self.conf = conf
        self.target_classes = target_classes or set()

    def track(self, frame: np.ndarray) -> list[TrackedObject]:
        results = self.model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            conf=self.conf,
            verbose=False,
        )[0]

        tracked: list[TrackedObject] = []
        if results.boxes is None or len(results.boxes) == 0:
            return tracked

        boxes = results.boxes
        has_ids = boxes.id is not None

        for i in range(len(boxes)):
            class_name = results.names[int(boxes.cls[i])]
            if self.target_classes and class_name not in self.target_classes:
                continue

            track_id = int(boxes.id[i]) if has_ids else -(i + 1)
            x1, y1, x2, y2 = boxes.xyxy[i].tolist()
            tracked.append(
                TrackedObject(
                    track_id=track_id,
                    class_name=class_name,
                    confidence=float(boxes.conf[i]),
                    bbox_xyxy=(x1, y1, x2, y2),
                )
            )
        return tracked

    def reset(self) -> None:
        # Ultralytics persist=True keeps state on the model instance.
        if hasattr(self.model, "predictor") and self.model.predictor is not None:
            self.model.predictor = None
