from app.models.cv_detector import CVDetectorProtocol
from app.models.media_extractor import MediaExtractorProtocol
from app.models.miscue import MiscueReporterProtocol
from app.models.passage import PassageRepositoryProtocol
from app.models.prosody_detector import ProsodyDetectorProtocol
from app.models.proper_noun import ProperNounExtractorProtocol
from app.models.scoring import ScoringEngineProtocol
from app.models.session import SessionRepositoryProtocol
from app.models.storage import RecordingStorageProtocol
from app.models.transcription import TranscriberProtocol
from app.services.analysis_orchestrator import AnalysisOrchestrator
from app.services.db.passage_repository import PassageRepository
from app.services.db.recording_storage import SupabaseRecordingStorage
from app.services.db.session_repository import SessionRepository
from app.services.db.supabase_client import get_supabase_client
from app.services.go2.miscue_classifier import MiscueClassifier
from app.services.go2.miscue_reporter import MiscueReporter
from app.services.go2.pipeline import GO2Pipeline
from app.services.go2.proper_noun_extractor import CapitalizationProperNounExtractor
from app.services.go2.scoring_engine import ScoringEngine
from app.services.go2.transcriber import get_transcriber_instance
from app.services.go3.cv_detector import get_detector_instance
from app.services.go3.pipeline import GO3Pipeline
from app.services.go3.prosody_detector import ProsodyAmplitudeDetector
from app.services.media_extractor import MediaExtractor


def get_transcriber() -> TranscriberProtocol:
    """FastAPI dependency — returns the singleton WhisperX transcriber."""
    return get_transcriber_instance()


def get_scoring_engine() -> ScoringEngineProtocol:
    """FastAPI dependency — fresh ScoringEngine per call (stateless)."""
    return ScoringEngine()


def get_cv_detector() -> CVDetectorProtocol:
    """FastAPI dependency — returns the singleton MediaPipe CV detector."""
    return get_detector_instance()


def get_prosody_detector() -> ProsodyDetectorProtocol:
    """FastAPI dependency — fresh ProsodyAmplitudeDetector per call (stateless)."""
    return ProsodyAmplitudeDetector()


def get_passage_repository() -> PassageRepositoryProtocol:
    """FastAPI dependency — PassageRepository backed by the Supabase service client."""
    client = get_supabase_client()
    if client is None:
        raise RuntimeError("Supabase client not initialised — check SUPABASE_URL and SUPABASE_SERVICE_KEY")
    return PassageRepository(client)


def get_session_repository() -> SessionRepositoryProtocol:
    """FastAPI dependency — SessionRepository backed by the Supabase service client."""
    client = get_supabase_client()
    if client is None:
        raise RuntimeError("Supabase client not initialised — check SUPABASE_URL and SUPABASE_SERVICE_KEY")
    return SessionRepository(client)


def get_recording_storage() -> RecordingStorageProtocol | None:
    """FastAPI dependency — SupabaseRecordingStorage backed by the Supabase service client.
    None if Supabase isn't configured — audio upload is a non-fatal, best-effort extra, unlike
    the passage/session repositories which /analyze cannot function without."""
    client = get_supabase_client()
    if client is None:
        return None
    return SupabaseRecordingStorage(client, get_passage_repository())


def get_media_extractor() -> MediaExtractorProtocol:
    """FastAPI dependency — stateless MediaExtractor (subprocess ffmpeg)."""
    return MediaExtractor()


def get_miscue_reporter() -> MiscueReporterProtocol:
    """FastAPI dependency — stateless MiscueReporter (prints miscues to console)."""
    return MiscueReporter()


def get_proper_noun_extractor() -> ProperNounExtractorProtocol:
    """FastAPI dependency — stateless capitalization-based proper-noun extractor."""
    return CapitalizationProperNounExtractor()


def get_go2_pipeline() -> GO2Pipeline:
    """FastAPI dependency — fully wired GO2Pipeline."""
    return GO2Pipeline(
        transcriber=get_transcriber(),
        classifier=MiscueClassifier(),
        scorer=get_scoring_engine(),
        passage_repo=get_passage_repository(),
        reporter=get_miscue_reporter(),
        proper_noun_extractor=get_proper_noun_extractor(),
    )


def get_go3_pipeline() -> GO3Pipeline:
    """FastAPI dependency — fully wired GO3Pipeline."""
    return GO3Pipeline(
        cv_detector=get_cv_detector(),
        prosody_detector=get_prosody_detector(),
    )


def get_analysis_orchestrator() -> AnalysisOrchestrator:
    """FastAPI dependency — fully wired AnalysisOrchestrator."""
    return AnalysisOrchestrator(
        extractor=get_media_extractor(),
        go2_pipeline=get_go2_pipeline(),
        go3_pipeline=get_go3_pipeline(),
        session_repo=get_session_repository(),
    )
