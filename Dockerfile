FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    libgles2 \
    libegl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Model choice is a build arg so the baked cache matches what runs at startup.
# int8 (CTranslate2) keeps large-v3 accuracy while ~halving RAM and speeding CPU inference.
ARG WHISPERX_MODEL=large-v3
ARG WHISPERX_COMPUTE_TYPE=int8

# Pre-download + int8-quantize the model into the default HuggingFace cache
# (~/.cache/huggingface). whisperx.load_model() finds it there at startup.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPERX_MODEL}', device='cpu', compute_type='${WHISPERX_COMPUTE_TYPE}')"

COPY app/ ./app/

# Pre-bake the MediaPipe .task bundles so the first request never hits the network
# (and a locked-down box works offline). Mirrors _ensure_model() in cv_detector.py.
RUN python -c "import urllib.request, pathlib; d = pathlib.Path('app/services/go3/models'); d.mkdir(parents=True, exist_ok=True); urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task', d / 'hand_landmarker.task'); urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task', d / 'face_landmarker.task')"

ENV WHISPERX_MODEL=${WHISPERX_MODEL}
ENV WHISPERX_COMPUTE_TYPE=${WHISPERX_COMPUTE_TYPE}
ENV WHISPERX_DEVICE=cpu
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
