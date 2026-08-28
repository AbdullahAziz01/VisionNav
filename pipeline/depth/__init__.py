from pipeline.depth.base import BaseDepthBackend
from pipeline.depth.depth_anything_v2 import DepthAnythingV2Backend
from pipeline.depth.metric3d import Metric3DBackend

__all__ = ["BaseDepthBackend", "DepthAnythingV2Backend", "Metric3DBackend", "create_mono_depth_backend"]


def create_mono_depth_backend(backend: str, depth_anything_model: str, metric3d_checkpoint: str) -> BaseDepthBackend:
    if backend == "depth_anything_v2":
        return DepthAnythingV2Backend(depth_anything_model)
    if backend == "metric3d":
        return Metric3DBackend(metric3d_checkpoint)
    raise ValueError(f"Unknown monocular depth backend: {backend}")
