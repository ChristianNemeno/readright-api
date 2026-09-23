from typing import Any

import whisperx  # type: ignore[import-untyped]

from app.config import get_settings
from app.models.transcription import WordSegment


class WhisperXTranscriber:
    """Holds pre-loaded WhisperX model refs and runs forced-alignment transcription."""

    def __init__(self) -> None:
        self._model: Any = None
        self._align_model: Any = None
        self._metadata: Any = None

    def load(self) -> None:
        """Loads the WhisperX model and alignment model into memory. Called once at startup."""
        settings = get_settings()
        self._model = whisperx.load_model(  # type: ignore[no-untyped-call]
            settings.WHISPERX_MODEL,
            device=settings.WHISPERX_DEVICE,
            compute_type=settings.WHISPERX_COMPUTE_TYPE,
            language="en",
        )
        self._align_model, self._metadata = whisperx.load_align_model(  # type: ignore[no-untyped-call]
            language_code="en",
            device=settings.WHISPERX_DEVICE,
        )

    def transcribe(self, wav_path: str, passage_text: str) -> list[WordSegment]:
        """Runs ASR + forced alignment on a WAV file. Returns [] if no speech found."""
        result = self._model.transcribe(wav_path, batch_size=4)  # type: ignore[no-untyped-call]
        aligned = whisperx.align(  # type: ignore[no-untyped-call]
            result["segments"],
            self._align_model,
            self._metadata,
            wav_path,
            device=get_settings().WHISPERX_DEVICE,
        )
        words: list[WordSegment] = []
        for seg in aligned.get("word_segments", []):
            words.append(
                WordSegment(
                    word=seg["word"].lower().strip(),
                    start=seg["start"],
                    end=seg["end"],
                    score=seg.get("score", 1.0),
                )
            )
        return words


_transcriber: WhisperXTranscriber | None = None


def load_models() -> None:
    """Creates and loads the WhisperXTranscriber singleton. Called once in FastAPI lifespan."""
    global _transcriber
    _transcriber = WhisperXTranscriber()
    _transcriber.load()


def get_transcriber_instance() -> WhisperXTranscriber:
    """Returns the singleton transcriber. Raises RuntimeError if not loaded yet."""
    if _transcriber is None:
        raise RuntimeError("Transcriber not loaded — call load_models() at startup")
    return _transcriber
