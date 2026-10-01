import asyncio
import logging

from fastapi import APIRouter, Depends, Form, Header, HTTPException, UploadFile

from app.config import get_settings
from app.dependencies import get_analysis_orchestrator
from app.models.assessment import AssessmentResult
from app.services.analysis_orchestrator import AnalysisOrchestrator

logger = logging.getLogger(__name__)


class AnalyzeController:
    """Handles HTTP for POST /analyze only. Delegates all pipeline logic to AnalysisOrchestrator."""

    def __init__(self) -> None:
        """Register the /analyze route and build the concurrency gate from settings."""
        settings = get_settings()
        # Serialize heavy pipeline runs so a small box never loads two WhisperX
        # inferences at once (OOM guard). Pilot default is 1 — extra callers get 503.
        self._semaphore = asyncio.Semaphore(max(1, settings.MAX_CONCURRENCY))
        self._max_upload_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
        self.router = APIRouter(tags=["analyze"])
        self.router.add_api_route(
            "/analyze",
            self.analyze,
            methods=["POST"],
            response_model=AssessmentResult,
        )

    async def analyze(
        self,
        file: UploadFile,
        passage_id: str = Form(...),
        learner_id: str = Form(""),
        x_api_key: str = Header(..., alias="X-API-Key"),
        orchestrator: AnalysisOrchestrator = Depends(get_analysis_orchestrator),
    ) -> AssessmentResult:
        """Accept a video upload and run the full assessment pipeline."""
        self._check_api_key(x_api_key)
        self._check_upload_size(file.size)

        if self._semaphore.locked():
            logger.warning("/analyze rejected — service busy (max_concurrency reached)")
            raise HTTPException(
                status_code=503,
                detail={"error": "The service is busy. Please wait a moment and try again.", "code": "BUSY"},
            )

        async with self._semaphore:
            upload_bytes = await file.read()
            self._check_upload_size(len(upload_bytes))
            filename = file.filename or "upload.webm"

            logger.info(
                "/analyze inbound filename=%s bytes=%d content_type=%s passage_id=%s learner_id_present=%s",
                filename,
                len(upload_bytes),
                file.content_type,
                passage_id,
                bool(learner_id.strip()),
            )

            result = await orchestrator.run(upload_bytes, filename, passage_id, learner_id)

        logger.info("/analyze outbound body=%s", result.model_dump())
        return result

    def _check_api_key(self, key: str) -> None:
        """Raises 401 if X-API-Key doesn't match settings."""
        if key != get_settings().API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")

    def _check_upload_size(self, size: int | None) -> None:
        """Raises 413 if the upload exceeds MAX_UPLOAD_MB. Skips when size is unknown (None)."""
        if size is not None and size > self._max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail={
                    "error": "That recording is too large. Please record a shorter reading and try again.",
                    "code": "FILE_TOO_LARGE",
                },
            )
