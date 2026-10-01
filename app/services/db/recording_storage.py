import logging
import os
import uuid

from supabase import Client

logger = logging.getLogger(__name__)

RECORDINGS_BUCKET = "recordings"


class SupabaseRecordingStorage:
    """Uploads raw recording files to the Supabase Storage 'recordings' bucket."""

    def __init__(self, client: Client) -> None:
        """Store the Supabase client."""
        self._client = client

    def upload(
        self,
        file_bytes: bytes,
        source_filename: str,
        learner_id: str,
        passage_id: str,
        content_type: str,
    ) -> None:
        """Upload the recording. Never raises — logs and swallows storage errors."""
        ext = os.path.splitext(source_filename)[-1] or ".webm"
        path = f"{learner_id or 'anonymous'}/{passage_id}/{uuid.uuid4().hex}{ext}"
        try:
            self._client.storage.from_(RECORDINGS_BUCKET).upload(
                path, file_bytes, {"content-type": content_type}
            )
        except Exception:
            logger.exception(
                "Recording upload failed learner=%s passage=%s path=%s",
                learner_id,
                passage_id,
                path,
            )
