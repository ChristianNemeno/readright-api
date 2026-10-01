# tests/test_rr030.py
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import cv2
import numpy as np
import pytest

from app.services.go3 import cv_detector
from app.services.go3.cv_detector import CVDetector

_POINTING_FIXTURE = Path("tests/fixtures/finger_pointing.mp4")
_NORMAL_FIXTURE = Path("tests/fixtures/normal_reading.mp4")


@pytest.fixture(scope="module")
def detector() -> Iterator[CVDetector]:
    """One loaded CVDetector reused across the module — load() is expensive.
    Must close() after use: the MediaPipe landmarkers' background threads otherwise
    keep pytest's process alive indefinitely after all tests have already passed."""
    d = CVDetector()
    d.load()
    yield d
    d.close()


def _write_video(path: Path, frames: int, *, color: int = 0) -> None:
    """Writes a tiny solid-color .avi with `frames` frames for the edge-case tests."""
    fourcc = cast(int, cv2.VideoWriter_fourcc(*"MJPG"))  # type: ignore[reportAttributeAccessIssue]
    writer = cv2.VideoWriter(str(path), fourcc, 10.0, (320, 240))
    frame = np.full((240, 320, 3), color, dtype=np.uint8)
    for _ in range(frames):
        writer.write(frame)
    writer.release()


@pytest.mark.skipif(
    not _POINTING_FIXTURE.exists(), reason="pointing.mp4 fixture not provided yet"
)
def test_finger_pointing_detected(detector: CVDetector) -> None:
    """Real clip with index finger over the text region → finger_pointing True."""
    flags = detector.detect(str(_POINTING_FIXTURE))
    assert flags["finger_pointing"] is True


@pytest.mark.skipif(
    not _NORMAL_FIXTURE.exists(), reason="normal_reading.mp4 fixture not provided yet"
)
def test_normal_reading_no_pointing(detector: CVDetector) -> None:
    """Real clip of normal reading, no pointing → finger_pointing False."""
    flags = detector.detect(str(_NORMAL_FIXTURE))
    assert flags["finger_pointing"] is False


def test_no_person_returns_false(detector: CVDetector, tmp_path: Path) -> None:
    """Black video, no hands/face → both flags False, no crash."""
    video = tmp_path / "black.avi"
    _write_video(video, frames=30, color=0)
    flags = detector.detect(str(video))
    assert flags["finger_pointing"] is False
    assert flags["loss_of_place"] is False


def test_empty_or_zero_frame_video(detector: CVDetector, tmp_path: Path) -> None:
    """Single-frame video → valid dict with both keys, no crash."""
    video = tmp_path / "tiny.avi"
    _write_video(video, frames=1, color=0)
    flags = detector.detect(str(video))
    assert flags["finger_pointing"] is False
    assert flags["loss_of_place"] is False


def test_timeout_returns_defaults(
    detector: CVDetector, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Timeout tripped immediately → early-exit default dict (both False)."""
    monkeypatch.setattr(cv_detector, "_TIMEOUT_SECONDS", 0.0)
    video = tmp_path / "multi.avi"
    _write_video(video, frames=30, color=0)
    flags = detector.detect(str(video))
    assert flags["finger_pointing"] is False
    assert flags["loss_of_place"] is False
