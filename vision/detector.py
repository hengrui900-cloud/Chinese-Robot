"""
High-level detector wrapper around the ONNX core detector.
"""

import logging
import threading
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class ChessboardDetector:
    """
    Detect board corners and classify the full 10x9 xiangqi board.

    The ONNX sessions must be loaded once and reused. Recreating them for every
    dynamic recognition poll is extremely expensive, especially on CUDA.
    """

    def __init__(self, pose_model_path: str, classifier_model_path: str):
        self.pose_model_path = pose_model_path
        self.classifier_model_path = classifier_model_path
        self._core_detector = None
        self._pose_model = None
        self._classifier_model = None
        self._runtime_lock = threading.RLock()

        logger.info("ChessboardDetector init")
        logger.info("  pose model: %s", pose_model_path)
        logger.info("  classifier model: %s", classifier_model_path)

    def _load_models(self):
        if self._core_detector is not None:
            return

        with self._runtime_lock:
            if self._core_detector is not None:
                return

            try:
                from core.chessboard_detector import ChessboardDetector as CoreDetector

                self._core_detector = CoreDetector(
                    pose_model_path=self.pose_model_path,
                    full_classifier_model_path=self.classifier_model_path,
                )
                self._pose_model = self._core_detector.pose
                self._classifier_model = self._core_detector.full_classifier
                logger.info("ONNX models loaded")
            except Exception as exc:
                logger.error("Load ONNX models failed: %s", exc, exc_info=True)
                raise RuntimeError(f"Cannot load ONNX models: {exc}")

    def reset_board_cache(self):
        if self._core_detector is not None and hasattr(self._core_detector, "reset_board_cache"):
            self._core_detector.reset_board_cache()

    def detect_and_classify(self, image_rgb: np.ndarray, draw_debug: bool = False) -> Tuple[
        Optional[np.ndarray],
        Optional[np.ndarray],
        Optional[str],
        Optional[list],
        str,
    ]:
        self._load_models()

        if image_rgb is None:
            return None, None, None, None, ""

        with self._runtime_lock:
            try:
                return self._core_detector.pred_detect_board_and_classifier(
                    image_rgb,
                    draw_debug=draw_debug,
                )
            except Exception as exc:
                logger.error("Detect/classify failed: %s", exc, exc_info=True)
                return None, None, None, None, f"error: {exc}"

    def parse_layout_string(self, layout_str: str) -> dict:
        if not layout_str:
            return {}

        board_state = {}
        rows = layout_str.strip().split("\n")
        for row_idx, row_str in enumerate(rows):
            if len(row_str) != 9:
                continue
            for col_idx, char in enumerate(row_str):
                if char in (".", "x"):
                    continue
                board_state[(col_idx, row_idx)] = char
        return board_state
