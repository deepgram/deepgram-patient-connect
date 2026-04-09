"""Load settings from project-root `.env` (all config lives in env)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
_SERVER_DIR = Path(__file__).resolve().parent

for _env in (
    _ROOT / "test-endpoints" / ".env",
    _ROOT / ".env",
    _SERVER_DIR / ".env",
):
    if _env.is_file():
        load_dotenv(_env, override=True)


def _get(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name, default)
    return v if v not in ("", None) else default


AWS_REGION = _get("AWS_REGION", "us-west-2")

# STT — Deepgram Flux on SageMaker (via deepgram-sagemaker transport)
SAGEMAKER_ENDPOINT_STT = _get("SAGEMAKER_ENDPOINT_NAME", "patient-connect-endpoint-stt-flux")
SAGEMAKER_STT_REGION = _get("AWS_REGION", "us-west-2")
DEEPGRAM_STT_MODEL = _get("DEEPGRAM_STT_MODEL", "flux-general-en")

# TTS — Deepgram Aura-2 on SageMaker (via deepgram-sagemaker transport)
SAGEMAKER_ENDPOINT_TTS = _get("SAGEMAKER_ENDPOINT_NAME_TTS", "patient-connect-endpoint-tts")
SAGEMAKER_TTS_REGION = _get("AWS_REGION", "us-west-2")
DEEPGRAM_TTS_MODEL = _get("DEEPGRAM_TTS_MODEL", "aura-2-thalia-en")
DEEPGRAM_TTS_SAMPLE_RATE = int(_get("DEEPGRAM_TTS_SAMPLE_RATE", "24000") or "24000")

# Deepgram Cloud API key (kept for future use / fallback)
DEEPGRAM_API_KEY = _get("DEEPGRAM_API_KEY", "")

# Amazon Bedrock LLM
BEDROCK_MODEL_ID = _get("BEDROCK_MODEL_ID", "us.amazon.nova-micro-v1:0")

DATASET_PATH = _get(
    "DATASET_PATH",
    str(_ROOT / "patient_promotions_dataset.jsonl"),
)

CORS_ORIGINS = [
    o.strip()
    for o in (_get("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173") or "").split(
        ","
    )
    if o.strip()
]
