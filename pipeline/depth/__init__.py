from pipeline.depth.base import BaseDepthBackend
from pipeline.depth.depth_anything_v2 import DepthAnythingV2Backend
from pipeline.depth.metric3d import Metric3DBackend
from pipeline.depth.midas_onnx import MiDaSONNXBackend

__all__ = [
    "BaseDepthBackend",
    "DepthAnythingV2Backend",
    "Metric3DBackend",
    "MiDaSONNXBackend",
    "create_mono_depth_backend",
]


def create_mono_depth_backend(
    backend: str,
    depth_anything_model: str,
    metric3d_checkpoint: str,
    midas_onnx_model_path: str = "model-small.onnx",
    midas_onnx_scale: float = 1.0,
    midas_onnx_shift: float = 0.0,
    midas_onnx_intra_op_threads: int = 4,
    midas_onnx_inter_op_threads: int = 1,
    depth_anything_input_size: int = 518,
    depth_anything_threads: int = 0,
) -> BaseDepthBackend:
    if backend == "depth_anything_v2":
        return DepthAnythingV2Backend(
            depth_anything_model,
            input_size=depth_anything_input_size,
            num_threads=depth_anything_threads,
        )
    if backend == "metric3d":
        return Metric3DBackend(metric3d_checkpoint)
    if backend == "midas_onnx":
        return MiDaSONNXBackend(
            midas_onnx_model_path,
            scale=midas_onnx_scale,
            shift=midas_onnx_shift,
            intra_op_threads=midas_onnx_intra_op_threads,
            inter_op_threads=midas_onnx_inter_op_threads,
        )
    raise ValueError(f"Unknown monocular depth backend: {backend}")
