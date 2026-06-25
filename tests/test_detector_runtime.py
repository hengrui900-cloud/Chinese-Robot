import os
import threading
import time
import unittest
from unittest.mock import patch

from core.runonnx import base_onnx
from vision.detector import ChessboardDetector


class DetectorRuntimeTests(unittest.TestCase):
    def test_default_onnx_provider_prefers_cuda_when_available(self):
        with (
            patch.dict(os.environ, {}, clear=False),
            patch.object(
                base_onnx.onnxruntime,
                "get_available_providers",
                return_value=["CUDAExecutionProvider", "CPUExecutionProvider"],
            ),
            patch.object(base_onnx, "_cuda_dependencies_available", return_value=True),
        ):
            os.environ.pop("CHRO_ONNX_PROVIDERS", None)
            providers = base_onnx._preferred_providers()

        self.assertEqual(providers, ["CUDAExecutionProvider", "CPUExecutionProvider"])

    def test_default_onnx_session_limits_cpu_threads(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CHRO_ONNX_INTRA_THREADS", None)
            os.environ.pop("CHRO_ONNX_INTER_THREADS", None)
            options = base_onnx._build_session_options()

        self.assertEqual(options.intra_op_num_threads, 2)
        self.assertEqual(options.inter_op_num_threads, 1)

    def test_detector_serializes_concurrent_inference(self):
        detector = ChessboardDetector("pose.onnx", "classifier.onnx")
        active = 0
        max_active = 0
        state_lock = threading.Lock()

        class FakeCoreDetector:
            def pred_detect_board_and_classifier(self, image, draw_debug=False):
                nonlocal active, max_active
                with state_lock:
                    active += 1
                    max_active = max(max_active, active)
                time.sleep(0.05)
                with state_lock:
                    active -= 1
                return None, None, "layout", [], "ok"

        detector._core_detector = FakeCoreDetector()
        threads = [
            threading.Thread(
                target=detector.detect_and_classify,
                args=(object(),),
            )
            for _ in range(3)
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=1.0)

        self.assertEqual(max_active, 1)


if __name__ == "__main__":
    unittest.main()
