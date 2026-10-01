from typing import Protocol


class RecordingStorageProtocol(Protocol):
    """Interface for persisting a learner's raw recording upload to object storage."""

    def upload(
        self,
        file_bytes: bytes,
        source_filename: str,
        learner_id: str,
        passage_id: str,
        content_type: str,
    ) -> None:
        """Store the recording. Never raises — logs and swallows storage errors."""
        ...
