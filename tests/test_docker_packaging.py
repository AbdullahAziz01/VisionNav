"""Inspectable Docker packaging checks that do not require Docker."""

from __future__ import annotations

import unittest
from pathlib import Path

from tools.seed_runtime_weights import seed_directory, seed_file, seed_runtime_caches

ROOT = Path(__file__).resolve().parents[1]


class TestDockerfileDoesNotNeedHostWeights(unittest.TestCase):
    def test_dockerfile_does_not_copy_pt_or_onnx(self):
        text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("COPY "):
                self.assertNotIn(".pt", stripped)
                self.assertNotIn(".onnx", stripped)
                self.assertNotIn(".pth", stripped)
                self.assertNotIn("model-small", stripped)
        self.assertIn("prepare_weights.py", text)
        self.assertIn("seed_runtime_weights.py", text)
        self.assertIn("--workers", text)
        self.assertIn("1", text)
        self.assertNotIn("model-small.onnx", text)

    def test_compose_keeps_one_worker_and_production_auth(self):
        text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("VISIONNAV_ENV=production", text)
        self.assertIn("VISIONNAV_API_KEY", text)
        self.assertIn("visionnav_cache:/app/cache", text)
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertRegex(dockerfile, r'--workers["\s,]+1')

    def test_dockerignore_excludes_secrets_git_phone_and_media(self):
        text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        for token in (".git", ".env", "visionnav_app/", "runs/", "*.pt", "*.onnx", "*.jpg"):
            self.assertIn(token, text)


class TestSeedRuntimeWeights(unittest.TestCase):
    def test_missing_files_are_seeded_without_overwriting_existing_files(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "src"
            dest = tmp_path / "dest"
            src.mkdir()
            (src / "model.bin").write_text("weights", encoding="utf-8")
            (src / "additional.bin").write_text("additional", encoding="utf-8")
            self.assertTrue(seed_directory(src, dest))
            self.assertEqual((dest / "model.bin").read_text(encoding="utf-8"), "weights")

            (src / "model.bin").write_text("newer", encoding="utf-8")
            self.assertFalse(seed_directory(src, dest))
            self.assertEqual((dest / "model.bin").read_text(encoding="utf-8"), "weights")

            # A partial volume can be completed on a later container start.
            (src / "new-model.bin").write_text("new", encoding="utf-8")
            self.assertTrue(seed_directory(src, dest))
            self.assertEqual((dest / "model.bin").read_text(encoding="utf-8"), "weights")
            self.assertEqual((dest / "new-model.bin").read_text(encoding="utf-8"), "new")

    def test_seed_file_skips_existing(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "yolov8n.pt"
            dest = tmp_path / "app" / "yolov8n.pt"
            src.write_bytes(b"abc")
            self.assertTrue(seed_file(src, dest))
            dest.write_bytes(b"keep")
            src.write_bytes(b"xyz")
            self.assertFalse(seed_file(src, dest))
            self.assertEqual(dest.read_bytes(), b"keep")

    def test_seed_runtime_caches_from_weights_root(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "opt"
            (root / "huggingface" / "hub").mkdir(parents=True)
            (root / "huggingface" / "hub" / "config.json").write_text("hf", encoding="utf-8")
            (root / "torch").mkdir()
            (root / "torch" / "hub.pth").write_text("t", encoding="utf-8")
            (root / "easyocr" / "model").mkdir(parents=True)
            (root / "easyocr" / "model" / "craft.pth").write_text("ocr", encoding="utf-8")
            (root / "yolo").mkdir()
            (root / "yolo" / "yolov8n.pt").write_bytes(b"yolo")
            (root / "config").mkdir()
            (root / "config" / "depth_scale_calibration.json").write_text("{}", encoding="utf-8")

            cache = tmp_path / "cache"
            app = tmp_path / "app"
            result = seed_runtime_caches(
                weights_root=root,
                hf_home=cache / "huggingface",
                torch_home=cache / "torch",
                easyocr_home=cache / "easyocr",
                yolo_dest=app / "yolov8n.pt",
                config_dest=app / "config",
            )
            self.assertTrue(all(result.values()))
            self.assertTrue((cache / "huggingface" / "hub" / "config.json").is_file())
            self.assertTrue((app / "yolov8n.pt").is_file())

            (root / "yolo" / "yolov8n.pt").write_bytes(b"new")
            result2 = seed_runtime_caches(
                weights_root=root,
                hf_home=cache / "huggingface",
                torch_home=cache / "torch",
                easyocr_home=cache / "easyocr",
                yolo_dest=app / "yolov8n.pt",
                config_dest=app / "config",
            )
            self.assertFalse(any(result2.values()))
            self.assertEqual((app / "yolov8n.pt").read_bytes(), b"yolo")


class TestPrepareWeightsScope(unittest.TestCase):
    def test_prepare_weights_does_not_reference_midas(self):
        text = (ROOT / "tools" / "prepare_weights.py").read_text(encoding="utf-8")
        # The module docstring explains that MiDaS is intentionally excluded;
        # inspect executable source for accidental loading/download code.
        lower = text.split('"""', 2)[-1].lower()
        self.assertNotIn("midas", lower)
        self.assertNotIn("model-small.onnx", lower)
        self.assertIn("yolov8n", lower)
        self.assertIn("easyocr", lower)
        self.assertIn("depth anything", lower)


if __name__ == "__main__":
    unittest.main()
