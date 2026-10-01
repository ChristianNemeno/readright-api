from app.models.passage import PassageRecord
from app.services.db.recording_storage import SupabaseRecordingStorage


class FakePassageRepo:
    """Returns a fixed passage text, or raises if told to simulate a fetch failure."""

    def __init__(self, text: str = "", fail: bool = False) -> None:
        self._text = text
        self._fail = fail

    def fetch(self, passage_id: str) -> PassageRecord:
        if self._fail:
            raise ValueError(f"Passage not found: {passage_id}")
        return PassageRecord(text=self._text, word_count=len(self._text.split()))


class FakeStorageBucket:
    """Captures the path/bytes/options passed to .upload() for assertions."""

    def __init__(self) -> None:
        self.last_path: str | None = None

    def from_(self, bucket: str) -> "FakeStorageBucket":
        return self

    def upload(self, path: str, file_bytes: bytes, options: dict[str, str]) -> None:
        self.last_path = path


class FakeClient:
    def __init__(self) -> None:
        self.storage = FakeStorageBucket()


def test_upload_prefixes_filename_with_first_10_alnum_chars_of_passage() -> None:
    client = FakeClient()
    storage = SupabaseRecordingStorage(client, FakePassageRepo(text="The Cat, Sat!! on the mat."))  # type: ignore[arg-type]

    storage.upload(b"bytes", "audio.wav", "learner1", "passage1", "audio/wav")

    assert client.storage.last_path is not None
    filename = client.storage.last_path.split("/")[-1]
    assert filename.startswith("thecatsat")  # first 10 alnum chars, lowercased
    assert filename.endswith(".wav")


def test_upload_falls_back_to_no_prefix_when_passage_fetch_fails() -> None:
    client = FakeClient()
    storage = SupabaseRecordingStorage(client, FakePassageRepo(fail=True))  # type: ignore[arg-type]

    storage.upload(b"bytes", "audio.wav", "learner1", "missing-passage", "audio/wav")

    assert client.storage.last_path is not None
    filename = client.storage.last_path.split("/")[-1]
    assert len(filename) == len(".wav") + 32  # just the uuid4 hex + ext, no prefix
