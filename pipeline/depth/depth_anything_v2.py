"""Depth Anything V2 backend (relative or metric HuggingFace variants)."""

from __future__ import annotations

import cv2
import numpy as np
import torch
from PIL import Image

from pipeline.depth.base import BaseDepthBackend
from pipeline.models import DepthMap


class DepthAnythingV2Backend(BaseDepthBackend):
    name = "depth_anything_v2"

    def __init__(self, model_id: str, input_size: int = 518, num_threads: int = 0):
        """
        Args:
            model_id: HuggingFace model id.
            input_size: Network input resolution (shorter side, multiple of 14).
                518 is the model default; 266-392 is 2-4x faster on CPU with a
                modest accuracy cost. Runtime scales ~ with input_size².
            num_threads: torch CPU threads (0 = leave torch default).
        """
        self.model_id = model_id
        self.input_size = max(14, (int(input_size) // 14) * 14)
        self.num_threads = int(num_threads)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._processor = None
        self._model = None
        self._is_metric = "metric" in model_id.lower()

    @property
    def provides_metric_depth(self) -> bool:
        return self._is_metric

    def _load(self):
        if self._model is not None:
            return
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation

        if self.num_threads > 0 and self.device.type == "cpu":
            torch.set_num_threads(self.num_threads)
        self._processor = AutoImageProcessor.from_pretrained(
            self.model_id,
            size={"height": self.input_size, "width": self.input_size},
            keep_aspect_ratio=True,
            ensure_multiple_of=14,
        )
        self._model = AutoModelForDepthEstimation.from_pretrained(self.model_id)
        self._model.to(self.device).eval()

    def estimate(self, frame_bgr: np.ndarray) -> DepthMap:
        self._load()
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)

        inputs = self._processor(images=pil_image, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model(**inputs)
            prediction = outputs.predicted_depth

        depth = torch.nn.functional.interpolate(
            prediction.unsqueeze(1),
            size=(frame_bgr.shape[0], frame_bgr.shape[1]),
            mode="bicubic",
            align_corners=False,
        ).squeeze().cpu().numpy()

        depth = depth.astype(np.float32)
        if self._is_metric:
            # Metric HF models output depth in meters (estimated, not ground-truth validated).
            scale_note = (
                "Depth Anything V2 Metric variant — values treated as estimated metric depth (m). "
                "Validate with MAE/RMSE against measured distances before claiming accuracy."
            )
            unit = "m"
        else:
            scale_note = (
                "Depth Anything V2 relative depth — NOT metric. "
                "Apply RELATIVE_DEPTH_SCALE_M or camera calibration before reporting meters."
            )
            unit = "relative"

        return DepthMap(
            values=depth,
            is_metric=self._is_metric,
            unit=unit,
            backend_name=self.name,
            scale_note=scale_note,
        )
