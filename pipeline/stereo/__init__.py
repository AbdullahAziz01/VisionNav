from pipeline.stereo.base import BaseStereoDepthBackend
from pipeline.stereo.detector import StereoPairStatus, detect_stereo_pair
from pipeline.stereo.raft_stereo import RaftStereoBackend
from pipeline.stereo.stereo_sgbm import StereoSGBMBackend

__all__ = [
    "BaseStereoDepthBackend",
    "StereoSGBMBackend",
    "RaftStereoBackend",
    "detect_stereo_pair",
    "StereoPairStatus",
    "create_stereo_depth_backend",
]


def create_stereo_depth_backend(backend: str) -> BaseStereoDepthBackend:
    if backend == "stereo_sgbm":
        return StereoSGBMBackend()
    if backend == "raft_stereo":
        return RaftStereoBackend()
    raise ValueError(f"Unknown stereo depth backend: {backend}")
