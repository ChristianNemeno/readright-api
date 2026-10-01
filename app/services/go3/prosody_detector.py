# app/services/go3/prosody_detector.py
import logging
from typing import Any, cast

import librosa  # type: ignore[import-untyped]
import numpy as np
import numpy.typing as npt
import parselmouth  # type: ignore[import-untyped]

from app.models.prosody_detector import ProsodyFlags

_INAUDIBLE_RMS_THRESHOLD = 0.01
_MONOTONE_F0_STD_THRESHOLD_ST = 2.5     # semitones — std of voiced F0 expressed as 12*log2(f0/median_f0). Speaker-normalized: removes pitch-register bias (a child at ~280Hz mean and an adult at ~110Hz are compared on the same scale). Literature places monotone perception at ~2-3 ST; 2.5 sits mid-range.
_MIN_DURATION_SECONDS = 5.0
_MIN_VOICED_FRAMES = 10
_SAMPLE_RATE = 16000
_SILENCE_RMS_THRESHOLD: float = 0.015      # frames below this = silence; above noise floor (~0.005), below soft speech (~0.03)
_SILENCE_MIN_FRAMES: int = 6               # min consecutive silent frames to count as inter-word gap (~192ms at hop=512, sr=16000)
_MEDIUM_GAP_MAX: float = 0.5               # upper bound on "within-sentence" word gap (s); longer = sentence break / breath
_WORD_BY_WORD_RATE_THRESHOLD: float = 0.2  # medium gaps / total audio duration > 0.2/s = word-by-word; calibrated on fluent (0.11/s) vs WBW (0.30/s) fixtures
_MIN_GAP_EVENTS: int = 2                   # need ≥2 interior gaps to compute a meaningful rate

_LOG = logging.getLogger(__name__)


def _default_flags() -> ProsodyFlags:
    """Safe all-False result — used when audio is too short to analyze."""
    return {"inaudible_reading": False, "monotone_reading": False, "word_by_word_reading": False}


class ProsodyAmplitudeDetector:
    """Extracts three prosody-based behavioral flags from a WAV file using librosa and parselmouth."""

    def detect(self, wav_path: str) -> ProsodyFlags:
        """Loads WAV once and runs all three prosody checks. Returns all-False for audio < 5s."""
        # librosa is untyped (import-level type: ignore above), so its return is Any —
        # cast to what librosa.load actually returns rather than let Any/Unknown leak
        # into every downstream use of y/sr.
        y, sr = cast(
            tuple[npt.NDArray[np.float64], int | float],
            librosa.load(wav_path, sr=_SAMPLE_RATE),  # type: ignore[no-untyped-call]
        )
        if len(y) / sr < _MIN_DURATION_SECONDS:
            return _default_flags()
        return {
            "inaudible_reading": self._detect_inaudible(y),
            "monotone_reading": self._detect_monotone(wav_path),
            "word_by_word_reading": self._detect_word_by_word(y, sr),
        }

    def _detect_inaudible(self, y: npt.NDArray[np.float64]) -> bool:
        """True if mean RMS energy falls below threshold — indicates voice too soft to score."""
        # librosa.feature.rms is typed but returns a bare (unsubscripted) np.ndarray —
        # cast rather than let that third-party imprecision leak into our own types.
        rms = cast(
            npt.NDArray[np.float64],
            librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0],  # type: ignore[no-untyped-call]
        )
        return float(np.mean(rms)) < _INAUDIBLE_RMS_THRESHOLD

    def _detect_monotone(self, wav_path: str) -> bool:
        """True if semitone-std of voiced F0 is below threshold — indicates flat/unexpressive reading."""
        snd: Any = parselmouth.Sound(wav_path)  # type: ignore[no-untyped-call]
        pitch: Any = snd.to_pitch()  # type: ignore[no-untyped-call]
        f0_values: npt.NDArray[np.float64] = np.array(pitch.selected_array["frequency"])  # type: ignore[no-untyped-call]
        voiced: npt.NDArray[np.float64] = f0_values[f0_values > 0]
        if len(voiced) < _MIN_VOICED_FRAMES:
            return False
        # Speaker-normalize: express F0 variation in semitones around the speaker's median.
        # Median (vs mean) shrugs off occasional Praat octave-jump errors.
        median_f0: float = float(np.median(voiced))
        semitones: npt.NDArray[np.float64] = 12.0 * np.log2(voiced / median_f0)
        st_std: float = float(np.std(semitones))
        decision: bool = st_std < _MONOTONE_F0_STD_THRESHOLD_ST
        _LOG.info(
            "monotone diagnostics: voiced_frames=%d median_f0=%.1fHz st_std=%.3f threshold=%.3fST -> decision=%s",
            len(voiced), median_f0, st_std, _MONOTONE_F0_STD_THRESHOLD_ST, decision,
        )
        return decision

    def _detect_word_by_word(self, y: npt.NDArray[np.float64], sr: int | float) -> bool:
        """True if mean inter-word silence gap exceeds threshold — indicates halting, word-by-word pacing."""
        hop_length: int = 512
        rms = cast(
            npt.NDArray[np.float64],
            librosa.feature.rms(  # type: ignore[no-untyped-call]
                y=y, frame_length=2048, hop_length=hop_length
            )[0],
        )
        n_frames: int = len(rms)
        silent_mask: npt.NDArray[np.bool_] = rms < _SILENCE_RMS_THRESHOLD

        transitions: npt.NDArray[np.int8] = np.diff(silent_mask.astype(np.int8))
        gap_starts: npt.NDArray[np.intp] = np.where(transitions == 1)[0] + 1
        gap_ends: npt.NDArray[np.intp] = np.where(transitions == -1)[0] + 1

        if silent_mask[0]:
            gap_starts = np.concatenate([[0], gap_starts])
        if silent_mask[-1]:
            gap_ends = np.concatenate([gap_ends, [n_frames]])

        n_gaps: int = min(len(gap_starts), len(gap_ends))
        gap_starts = gap_starts[:n_gaps]
        gap_ends = gap_ends[:n_gaps]

        # Keep only interior gaps — exclude leading/trailing recording silence
        interior: npt.NDArray[np.bool_] = (gap_starts > 0) & (gap_ends < n_frames)
        gap_lengths: npt.NDArray[np.intp] = (gap_ends - gap_starts)[interior]
        real_gaps: npt.NDArray[np.intp] = gap_lengths[gap_lengths >= _SILENCE_MIN_FRAMES]

        if len(real_gaps) < _MIN_GAP_EVENTS:
            _LOG.info(
                "word_by_word diagnostics: raw_runs=%d interior_gaps=%d (need >=%d) -> decision=False (insufficient gaps)",
                n_gaps, len(real_gaps), _MIN_GAP_EVENTS,
            )
            return False

        frame_duration: float = hop_length / float(sr)
        gap_durations: npt.NDArray[np.floating[Any]] = real_gaps * frame_duration
        total_duration: float = n_frames * frame_duration
        medium_count: int = int(np.sum(gap_durations <= _MEDIUM_GAP_MAX))
        medium_rate: float = medium_count / total_duration if total_duration > 0 else 0.0
        decision: bool = medium_rate > _WORD_BY_WORD_RATE_THRESHOLD
        _LOG.info(
            "word_by_word diagnostics: raw_runs=%d interior_gaps=%d medium_gaps=%d "
            "total_duration=%.2fs medium_rate=%.3f/s durations=%s "
            "min=%.3f median=%.3f mean=%.3f max=%.3f threshold=%.3f/s -> decision=%s",
            n_gaps,
            len(real_gaps),
            medium_count,
            total_duration,
            medium_rate,
            [round(float(g), 3) for g in gap_durations],
            float(np.min(gap_durations)),
            float(np.median(gap_durations)),
            float(np.mean(gap_durations)),
            float(np.max(gap_durations)),
            _WORD_BY_WORD_RATE_THRESHOLD,
            decision,
        )
        return decision
