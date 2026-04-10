"""Deepgram Aura-2 TTS via SageMaker using deepgram-python-sdk-transport-sagemaker.

Wraps the Deepgram Python SDK's speak.v1 WebSocket API with a SageMaker
transport factory as a pipecat TTSService. Each synthesis call creates a
fresh client (with restore_transport) since only one transport factory can
be active at a time.

Uses deepgram-sagemaker >= 0.2.2 (NOT pipecat's built-in SageMaker client).
"""

import asyncio
import re

from loguru import logger

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.speak.v1.types import SpeakV1Close, SpeakV1Flush, SpeakV1Flushed, SpeakV1Text
from deepgram.transport import restore_transport
from deepgram_sagemaker import SageMakerTransportFactory

from pipecat.frames.frames import (
    Frame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService

from typing import AsyncGenerator


def _clean_for_tts(text: str) -> str:
    """Remove characters that cause TTS mispronunciation."""
    text = text.replace("—", ", ").replace("–", ", ").replace("…", "...")
    text = re.sub(r"\s+", " ", text).strip()
    return text


class SageMakerTTSService(TTSService):
    """Deepgram Aura-2 TTS on SageMaker via deepgram-python-sdk-transport-sagemaker.

    Each call to run_tts creates a fresh AsyncDeepgramClient with a SageMaker
    transport factory, synthesizes the text, yields audio frames, then cleans up.
    """

    def __init__(
        self,
        *,
        endpoint_name: str,
        region: str = "us-west-2",
        model: str = "aura-2-thalia-en",
        sample_rate: int = 24000,
        **kwargs,
    ):
        super().__init__(
            sample_rate=sample_rate,
            settings=TTSSettings(model=model, voice=model, language=None),
            **kwargs,
        )
        self._endpoint_name = endpoint_name
        self._region = region
        self._model = model
        self._output_sample_rate = sample_rate

    def _fresh_client(self) -> AsyncDeepgramClient:
        try:
            restore_transport()
        except Exception:
            pass
        factory = SageMakerTransportFactory(
            endpoint_name=self._endpoint_name,
            region=self._region,
        )
        return AsyncDeepgramClient(api_key="unused", transport_factory=factory)

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        text = _clean_for_tts(text)
        if not text:
            return

        logger.info(f"TTS: '{text[:60]}' ({len(text)} chars)")

        audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        total_bytes = 0

        client = self._fresh_client()

        try:
            async with client.speak.v1.connect(
                model=self._model,
                encoding="linear16",
                sample_rate=str(self._output_sample_rate),
            ) as conn:

                def on_msg(d):
                    if isinstance(d, (bytes, bytearray)):
                        loop.call_soon_threadsafe(audio_queue.put_nowait, bytes(d))
                    elif isinstance(d, SpeakV1Flushed):
                        loop.call_soon_threadsafe(audio_queue.put_nowait, None)

                def on_err(e):
                    if "STREAM_BROKEN" not in repr(e):
                        logger.error(f"TTS error: {e}")

                conn.on(EventType.MESSAGE, on_msg)
                conn.on(EventType.ERROR, on_err)
                task = asyncio.create_task(conn.start_listening())
                await asyncio.sleep(0.1)

                await conn.send_text(SpeakV1Text(type="Speak", text=text))
                await conn.send_flush(SpeakV1Flush(type="Flush"))

                yield TTSStartedFrame()

                while True:
                    try:
                        chunk = await asyncio.wait_for(audio_queue.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        logger.warning("TTS: stream timeout")
                        break
                    if chunk is None:
                        break
                    total_bytes += len(chunk)
                    yield TTSAudioRawFrame(
                        audio=chunk,
                        sample_rate=self._output_sample_rate,
                        num_channels=1,
                    )

                yield TTSStoppedFrame()

                await conn.send_close(SpeakV1Close(type="Close"))
                await asyncio.sleep(0.3)
                task.cancel()

        finally:
            try:
                restore_transport()
            except Exception:
                pass

        logger.info(f"TTS: streamed {total_bytes} bytes")
