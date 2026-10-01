import logging
import os
import uuid

from supabase import Client

from app.models.passage import PassageRepositoryProtocol

logger = logging.getLogger(__name__)

RECORDINGS_BUCKET = "recordings"


class SupabaseRecordingStorage:
    """Uploads raw recording files to the Supabase Storage 'recordings' bucket."""

    def __init__(self, client: Client, passage_repo: PassageRepositoryProtocol) -> None:
        """Store the Supabase client and passage repo (used to name the file after the passage)."""
        self._client = client
        self._passage_repo = passage_repo

    def upload(
        self,
        file_bytes: bytes,
        source_filename: str,
        learner_id: str,
        passage_id: str,
        content_type: str,
    ) -> None:
        """Upload the recording as '<first 10 alnum chars of passage><random id><ext>'. Never raises — logs and swallows storage errors."""
        ext = os.path.splitext(source_filename)[-1] or ".webm"
        prefix = self._passage_prefix(passage_id)
        path = f"{learner_id or 'anonymous'}/{passage_id}/{prefix}{uuid.uuid4().hex}{ext}"
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

    def _passage_prefix(self, passage_id: str) -> str:
        """First 10 alphanumeric chars of the passage text, lowercased. Empty string if the fetch fails."""
        try:
            text = self._passage_repo.fetch(passage_id)["text"]
        except Exception:
            logger.exception("Passage fetch for filename prefix failed passage=%s", passage_id)
            return ""
        return "".join(ch for ch in text if ch.isalnum())[:10].lower()
