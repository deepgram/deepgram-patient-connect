"""Deepgram Flux STT via SageMaker using deepgram-python-sdk-transport-sagemaker.

Wraps the Deepgram Python SDK's v2 listen API with a SageMaker transport
factory as a pipecat STTService. Audio is streamed to a SageMaker-hosted
Deepgram Flux model via HTTP/2.

Key constraints (from deepgram-sagemaker 0.2.2):
  - Only one transport factory per process; use restore_transport() to swap.
  - SageMaker closes idle HTTP/2 connections — open STT right before audio flows.
  - The TTS calls restore_transport() per utterance, so the STT connection must
    be created AFTER the greeting TTS finishes (lazy connect on first audio).
"""

import asyncio
from typing import AsyncGenerator, Optional

from loguru import logger

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.transport import restore_transport
from deepgram_sagemaker import SageMakerTransportFactory

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    StartFrame,
    TranscriptionFrame,
)
from pipecat.services.stt_service import STTService
from pipecat.utils.time import time_now_iso8601

MIC_SAMPLE_RATE = 16000


class SageMakerFluxSTTService(STTService):
    """Deepgram Flux STT on SageMaker via deepgram-python-sdk-transport-sagemaker.

    Connects lazily on first audio to avoid SageMaker idle-close and to let
    the greeting TTS finish its restore_transport() cycle first.
    """

    def __init__(
        self,
        *,
        endpoint_name: str,
        region: str = "us-west-2",
        model: str = "flux-general-en",
        **kwargs,
    ):
        super().__init__(sample_rate=MIC_SAMPLE_RATE, **kwargs)
        self._endpoint_name = endpoint_name
        self._region = region
        self._model = model

        self._client: Optional[AsyncDeepgramClient] = None
        self._conn = None
        self._listen_task: Optional[asyncio.Task] = None
        self._connected = False
        self._audio_count = 0

    async def start(self, frame: StartFrame):
        await super().start(frame)
        logger.info(
            f"STT ready (lazy connect): {self._endpoint_name} ({self._region}), "
            f"model={self._model}, sample_rate={MIC_SAMPLE_RATE}"
        )

    async def stop(self, frame: EndFrame):
        await super().stop(frame)
        await self._disconnect_stt()

    async def cancel(self, frame: CancelFrame):
        await super().cancel(frame)
        await self._disconnect_stt()

    async def _connect_stt(self):
        """Open Deepgram v2 listen via SageMaker — called on first audio."""
        logger.info(f"STT connecting now (first audio arrived)...")

        try:
            restore_transport()
        except Exception:
            pass

        factory = SageMakerTransportFactory(
            endpoint_name=self._endpoint_name,
            region=self._region,
        )
        self._client = AsyncDeepgramClient(
            api_key="unused", transport_factory=factory
        )

        self._conn = await self._client.listen.v2.connect(
            model=self._model,
            encoding="linear16",
            sample_rate=str(MIC_SAMPLE_RATE),
        ).__aenter__()

        self._conn.on(EventType.MESSAGE, self._on_stt_message)
        self._conn.on(EventType.ERROR, self._on_stt_error)

        self._listen_task = asyncio.create_task(self._conn.start_listening())
        await asyncio.sleep(0.5)
        self._connected = True
        logger.info("STT connected and listening")

    async def _disconnect_stt(self):
        """Close the STT connection and clean up."""
        self._connected = False

        if self._conn:
            try:
                await self._conn.send_close_stream()
            except Exception:
                pass
            await asyncio.sleep(0.5)

        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except (asyncio.CancelledError, Exception):
                pass
            self._listen_task = None

        self._conn = None
        self._client = None

        try:
            restore_transport()
        except Exception:
            pass

        logger.info(f"STT disconnected (processed {self._audio_count} audio chunks)")

    def _on_stt_message(self, m):
        """Callback from Deepgram SDK — fires on the asyncio event loop."""
        transcript = getattr(m, "transcript", None)
        event = getattr(m, "event", None)

        if getattr(m, "request_id", None) and not transcript:
            return

        if transcript:
            tag = str(event) if event else ""
            is_final = "end" in tag.lower()
            if is_final and transcript.strip():
                logger.info(f"STT >>> {transcript}")
                asyncio.get_event_loop().create_task(
                    self.push_frame(
                        TranscriptionFrame(
                            transcript,
                            "",
                            time_now_iso8601(),
                        )
                    )
                )

    def _on_stt_error(self, e):
        if "streaming the inference" not in str(e).lower():
            logger.error(f"STT error: {e}")

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """Forward audio to SageMaker-hosted Deepgram Flux model.

        Lazily connects on first call to avoid idle-close and
        restore_transport conflicts with the greeting TTS.
        """
        if not self._connected:
            await self._connect_stt()

        if self._conn and self._connected:
            try:
                await self._conn.send_media(audio)
                self._audio_count += 1
            except Exception as e:
                logger.error(f"STT send_media error: {e}")
                yield ErrorFrame(error=f"STT send error: {e}")
        yield None
