# app/services/go3/cv_detector.py
import math
import time
import urllib.request
from pathlib import Path
from typing import Any

import cv2  # type: ignore[import-untyped]
import mediapipe as mp  # type: ignore[import-untyped]
from mediapipe.tasks import python as mp_python  # type: ignore[import-untyped]
from mediapipe.tasks.python import vision  # type: ignore[import-untyped]

from app.models.cv_detector import CVFlags

_FRAME_SAMPLE_RATE = 5
_INDEX_TIP_LANDMARK = 8
_LEFT_IRIS_LANDMARK = 468
_RIGHT_IRIS_LANDMARK = 473
_TEXT_REGION_MIN_Y = 0.33
_TEXT_REGION_MIN_X = 0.25
_TEXT_REGION_MAX_X = 0.75
_FINGER_POINTING_FRAME_RATIO = 0.20
_MIN_HAND_VISIBLE_FRAMES = 10
_GAZE_SHIFT_DELTA = 0.10
_GAZE_SHIFT_COUNT_THRESHOLD = 2
_NO_FACE_THRESHOLD = 3
_MIN_DETECTION_CONFIDENCE = 0.5
_TIMEOUT_SECONDS = 120.0

_MODEL_DIR = Path(__file__).parent / "models"
_HAND_MODEL_PATH = _MODEL_DIR / "hand_landmarker.task"
_FACE_MODEL_PATH = _MODEL_DIR / "face_landmarker.task"
_HAND_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
_FACE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"


def _ensure_model(path: Path, url: str) -> None:
    """Downloads a MediaPipe .task bundle to `path` if not already cached locally."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, path)


def _default_flags() -> CVFlags:
    """Safe all-False result — used for empty/missing/timed-out video."""
    return {"finger_pointing": False, "loss_of_place": False}


class CVDetector:
    """Reads a reading video and returns GO3 flags (finger_pointing, loss_of_place) via MediaPipe Tasks."""

    def __init__(self) -> None:
        self._hands: Any = None
        self._face_mesh: Any = None

    def close(self) -> None:
        """Releases the HandLandmarker/FaceLandmarker native resources and their background
        threads. The production singleton (load_models()) never calls this — the API process
        is killed, not cleanly shut down — but tests that construct their own CVDetector must,
        or the landmarkers' threads keep pytest's process alive indefinitely after all tests pass."""
        if self._hands is not None:
            self._hands.close()
        if self._face_mesh is not None:
            self._face_mesh.close()

    def load(self) -> None:
        """Downloads (if needed) and loads MediaPipe HandLandmarker + FaceLandmarker once at startup."""
        _ensure_model(_HAND_MODEL_PATH, _HAND_MODEL_URL)
        _ensure_model(_FACE_MODEL_PATH, _FACE_MODEL_URL)
        hand_base: Any = mp_python.BaseOptions(model_asset_path=str(_HAND_MODEL_PATH))  # type: ignore[no-untyped-call]
        hand_opts: Any = vision.HandLandmarkerOptions(base_options=hand_base, num_hands=1, min_hand_detection_confidence=_MIN_DETECTION_CONFIDENCE)  # type: ignore[no-untyped-call]
        self._hands = vision.HandLandmarker.create_from_options(hand_opts)  # type: ignore[no-untyped-call]
        face_base: Any = mp_python.BaseOptions(model_asset_path=str(_FACE_MODEL_PATH))  # type: ignore[no-untyped-call]
        face_opts: Any = vision.FaceLandmarkerOptions(base_options=face_base, num_faces=1, min_face_detection_confidence=_MIN_DETECTION_CONFIDENCE)  # type: ignore[no-untyped-call]
        self._face_mesh = vision.FaceLandmarker.create_from_options(face_opts)  # type: ignore[no-untyped-call]

    def detect(self, video_path: str) -> CVFlags:
        """Samples every 5th frame, aggregates finger-pointing frames + gaze shifts. Always returns a valid dict."""
        if self._hands is None or self._face_mesh is None:
            raise RuntimeError("CV detector not loaded — call load_models() at startup")

        capture = cv2.VideoCapture(video_path)  # type: ignore[no-untyped-call]
        start = time.monotonic()
        sampled = 0
        hand_visible_frames = 0
        pointing_frames = 0
        gaze_shifts = 0
        no_face_frames = 0
        face_ever_seen = False
        prev_xy: tuple[float, float] | None = None
        frame_index = 0
        try:
            while True:
                ok, frame = capture.read()  # type: ignore[no-untyped-call]
                if not ok:
                    break
                if frame_index % _FRAME_SAMPLE_RATE != 0:
                    frame_index += 1
                    continue
                if time.monotonic() - start > _TIMEOUT_SECONDS:
                    return _default_flags()
                sampled += 1
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # type: ignore[no-untyped-call]
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)  # type: ignore[no-untyped-call]
                in_region, hand_present = self._finger_in_text_region(image)
                if hand_present:
                    hand_visible_frames += 1
                if in_region:
                    pointing_frames += 1
                xy = self._iris_xy(image)
                if xy is not None:
                    face_ever_seen = True
                    if (
                        prev_xy is not None
                        and math.hypot(xy[0] - prev_xy[0], xy[1] - prev_xy[1]) > _GAZE_SHIFT_DELTA
                    ):
                        gaze_shifts += 1
                    prev_xy = xy
                elif face_ever_seen:
                    # Only count a vanished face as losing place once a face was actually
                    # established — a face that's never visible from frame 1 is a camera/
                    # setup problem, not a reader who looked away mid-passage.
                    no_face_frames += 1
                frame_index += 1
        finally:
            capture.release()  # type: ignore[no-untyped-call]

        if sampled == 0:
            return _default_flags()
        return {
            "finger_pointing": (
                hand_visible_frames >= _MIN_HAND_VISIBLE_FRAMES
                and pointing_frames / hand_visible_frames >= _FINGER_POINTING_FRAME_RATIO
            ),
            "loss_of_place": (
                no_face_frames >= _NO_FACE_THRESHOLD
                or gaze_shifts >= _GAZE_SHIFT_COUNT_THRESHOLD
            ),
        }

    def _finger_in_text_region(self, image: Any) -> tuple[bool, bool]:
        """Returns (in_text_region, hand_present) for the index-finger tip this frame."""
        result = self._hands.detect(image)
        hands = result.hand_landmarks
        if not hands:
            return False, False
        tip = hands[0][_INDEX_TIP_LANDMARK]
        in_region = tip.y > _TEXT_REGION_MIN_Y and _TEXT_REGION_MIN_X < tip.x < _TEXT_REGION_MAX_X
        return in_region, True

    def _iris_xy(self, image: Any) -> tuple[float, float] | None:
        """Returns the combined (x, y) gaze position for this frame, or None if no face is detected.

        Averages the left iris center (landmark 468) and the right iris center (landmark 473)
        in normalized image coordinates. Averaging both irises is more robust than tracking a
        single eye: it smooths out per-eye detection noise, squint/blink artifacts, and
        asymmetric head pose, and yields a single point that can be compared frame-to-frame
        with a 2D Euclidean distance for loss-of-place gaze-shift detection.
        """
        result = self._face_mesh.detect(image)
        faces = result.face_landmarks
        if not faces:
            return None
        left = faces[0][_LEFT_IRIS_LANDMARK]
        right = faces[0][_RIGHT_IRIS_LANDMARK]
        return (float(left.x + right.x) / 2.0, float(left.y + right.y) / 2.0)


_detector: CVDetector | None = None


def load_models() -> None:
    """Creates and loads the CVDetector singleton. Called once in FastAPI lifespan."""
    global _detector
    _detector = CVDetector()
    _detector.load()


def get_detector_instance() -> CVDetector:
    """Returns the singleton CV detector. Raises RuntimeError if not loaded yet."""
    if _detector is None:
        raise RuntimeError("CV detector not loaded — call load_models() at startup")
    return _detector
