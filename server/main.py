"""Patient Connect voice agent server.

Uses websockets + asyncio.run() with deepgram-sagemaker >= 0.2.2.

HTTP endpoints: /api/health, /api/records
WebSocket:      /ws/call?record_id=...
Debug:          /mic-test
"""

from __future__ import annotations

import asyncio
import http
import json
import logging
import os
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import boto3
import websockets
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.speak.v1.types import SpeakV1Close, SpeakV1Flush, SpeakV1Flushed, SpeakV1Text
from deepgram.transport import restore_transport
from deepgram_sagemaker import SageMakerTransportFactory

import config
from call_prompts import bedrock_system_prompt, opening_greeting
from dataset import get_eligible_record, load_eligible_records

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("server")

PORT = 8000
MIC_SAMPLE_RATE = 16000
TTS_SAMPLE_RATE = config.DEEPGRAM_TTS_SAMPLE_RATE
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _fresh_client(endpoint: str, region: str) -> AsyncDeepgramClient:
    """Create a fresh AsyncDeepgramClient with restore_transport() first."""
    try:
        restore_transport()
    except Exception:
        pass
    factory = SageMakerTransportFactory(endpoint_name=endpoint, region=region)
    return AsyncDeepgramClient(api_key="unused", transport_factory=factory)


# ---------------------------------------------------------------------------
# TTS: one factory swap per response, stream audio as it arrives
# ---------------------------------------------------------------------------

async def _speak(ws, text: str) -> None:
    """Synthesize all sentences with a single factory swap. Streams audio."""
    await ws.send(json.dumps({"type": "agent_transcript", "text": text}))

    tts_client = _fresh_client(config.SAGEMAKER_ENDPOINT_TTS, config.SAGEMAKER_TTS_REGION)

    try:
        for sentence in _SENTENCE_SPLIT.split(text):
            sentence = sentence.strip()
            if not sentence:
                continue
            try:
                await _synthesize_and_stream(ws, tts_client, sentence)
            except Exception:
                logger.exception("TTS failed: %s", sentence[:60])
    finally:
        try:
            restore_transport()
        except Exception:
            pass


def _clean_for_tts(text: str) -> str:
    """Clean text for TTS — remove characters that cause mispronunciation."""
    text = text.replace("—", ", ").replace("–", ", ").replace("…", "...")
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def _synthesize_and_stream(ws, client: AsyncDeepgramClient, text: str) -> None:
    """Synthesize one sentence and stream audio to browser as chunks arrive."""
    text = _clean_for_tts(text)
    logger.info("TTS: '%s' (%d chars)", text[:60], len(text))
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    flushed = asyncio.Event()
    loop = asyncio.get_running_loop()
    total_bytes = 0

    async with client.speak.v1.connect(
        model=config.DEEPGRAM_TTS_MODEL,
        encoding="linear16",
        sample_rate=str(TTS_SAMPLE_RATE),
    ) as conn:

        def on_msg(d):
            if isinstance(d, (bytes, bytearray)):
                loop.call_soon_threadsafe(audio_queue.put_nowait, bytes(d))
            elif isinstance(d, SpeakV1Flushed):
                flushed.set()
                loop.call_soon_threadsafe(audio_queue.put_nowait, None)

        def on_err(e):
            if "STREAM_BROKEN" not in repr(e):
                logger.error("TTS error: %s", e)

        conn.on(EventType.MESSAGE, on_msg)
        conn.on(EventType.ERROR, on_err)
        task = asyncio.create_task(conn.start_listening())
        await asyncio.sleep(0.1)

        await conn.send_text(SpeakV1Text(type="Speak", text=text))
        await conn.send_flush(SpeakV1Flush(type="Flush"))

        # Stream audio to browser as it arrives from TTS
        while True:
            try:
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                logger.warning("TTS: stream timeout")
                break
            if chunk is None:
                break
            await ws.send(chunk)
            total_bytes += len(chunk)

        await conn.send_close(SpeakV1Close(type="Close"))
        await asyncio.sleep(0.5)
        task.cancel()

    logger.info("TTS: streamed %d bytes", total_bytes)


# ---------------------------------------------------------------------------
# Streaming Bedrock: TTS starts on first sentence while LLM still generates
# ---------------------------------------------------------------------------

_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")

async def _stream_bedrock_and_speak(ws, bedrock, messages, system, interrupted: asyncio.Event | None = None) -> None:
    """Stream Bedrock response sentence-by-sentence, TTS each immediately."""

    sentence_buf = ""
    full_reply = ""

    def _stream_sync():
        """Run in thread — yields text chunks from Bedrock converse_stream."""
        resp = bedrock.converse_stream(
            modelId=config.BEDROCK_MODEL_ID,
            messages=messages,
            system=[{"text": system}],
            inferenceConfig={"maxTokens": 120, "temperature": 0.6},
        )
        for event in resp.get("stream", []):
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"].get("delta", {})
                text = delta.get("text", "")
                if text:
                    yield text

    # Collect chunks from streaming LLM in a thread
    chunk_queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def _producer():
        def _run():
            for chunk in _stream_sync():
                chunk_queue.put_nowait(chunk)
            chunk_queue.put_nowait(None)
        await asyncio.to_thread(_run)

    producer_task = asyncio.create_task(_producer())

    # Swap to TTS factory once for the entire response
    tts_client = _fresh_client(config.SAGEMAKER_ENDPOINT_TTS, config.SAGEMAKER_TTS_REGION)
    transcript_sent = False

    try:
        while True:
            if interrupted and interrupted.is_set():
                logger.info("Agent: interrupted by user")
                break

            chunk = await chunk_queue.get()
            if chunk is None:
                break

            sentence_buf += chunk
            full_reply += chunk

            # Split at sentence boundaries (may produce multiple sentences per chunk)
            while True:
                match = _SENTENCE_END.search(sentence_buf)
                if not match:
                    break

                split_pos = match.end()
                sentence = sentence_buf[:split_pos].strip()
                sentence_buf = sentence_buf[split_pos:]

                if sentence:
                    if interrupted and interrupted.is_set():
                        logger.info("Agent: interrupted before TTS")
                        break
                    logger.info("Agent (streaming): %s", sentence[:60])
                    await ws.send(json.dumps({"type": "agent_transcript", "text": full_reply.strip()}))
                    await _synthesize_and_stream(ws, tts_client, sentence)

        if sentence_buf.strip() and not (interrupted and interrupted.is_set()):
            sentence = sentence_buf.strip()
            logger.info("Agent (streaming): %s", sentence[:60])
            await ws.send(json.dumps({"type": "agent_transcript", "text": full_reply.strip()}))
            await _synthesize_and_stream(ws, tts_client, sentence)

    finally:
        try:
            restore_transport()
        except Exception:
            pass
        await producer_task

    messages.append({"role": "assistant", "content": [{"text": full_reply}]})
    logger.info("Agent full reply: %s", full_reply[:100])


# ---------------------------------------------------------------------------
# Voice agent session
# ---------------------------------------------------------------------------

async def voice_agent(ws, record: dict[str, Any]) -> None:
    system = bedrock_system_prompt(record)
    greeting = opening_greeting(record)
    messages: list[dict] = []
    transcript_queue: asyncio.Queue[str] = asyncio.Queue()

    bedrock = boto3.client(
        "bedrock-runtime",
        region_name=config.AWS_REGION,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

    # -- Send greeting (TTS only, no LLM) --
    logger.info("Greeting: %s", greeting[:60])
    await _speak(ws, greeting)
    messages.append({"role": "assistant", "content": [{"text": greeting}]})

    # -- Open STT --
    stt_client = _fresh_client(config.SAGEMAKER_ENDPOINT_STT, config.SAGEMAKER_STT_REGION)

    async with stt_client.listen.v2.connect(
        model=config.DEEPGRAM_STT_MODEL,
        encoding="linear16",
        sample_rate=str(MIC_SAMPLE_RATE),
    ) as stt_conn:

        stt_connected_logged = False

        def on_stt_msg(m):
            nonlocal stt_connected_logged
            transcript = getattr(m, "transcript", None)
            event = getattr(m, "event", None)
            if getattr(m, "request_id", None) and not transcript:
                if not stt_connected_logged:
                    logger.info("STT: connected")
                    stt_connected_logged = True
                return
            if transcript:
                tag = str(event) if event else ""
                is_final = "end" in tag.lower()
                if is_final:
                    logger.info("STT >>> %s", transcript)
                    asyncio.get_event_loop().create_task(transcript_queue.put(transcript))

        def on_stt_err(e):
            if "streaming the inference" not in str(e).lower():
                logger.error("STT error: %s", e)

        stt_conn.on(EventType.MESSAGE, on_stt_msg)
        stt_conn.on(EventType.ERROR, on_stt_err)
        listen_task = asyncio.create_task(stt_conn.start_listening())
        await asyncio.sleep(0.5)
        logger.info("STT: ready")

        running = True
        interrupted = asyncio.Event()
        agent_speaking = False

        async def audio_receiver():
            nonlocal running
            try:
                async for msg in ws:
                    if isinstance(msg, bytes) and len(msg) > 0:
                        await stt_conn.send_media(msg)
            except websockets.ConnectionClosed:
                pass
            running = False

        async def conversation_loop():
            nonlocal agent_speaking
            while running:
                try:
                    text = await asyncio.wait_for(transcript_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                # Barge-in: if agent is speaking, interrupt it
                if agent_speaking:
                    interrupted.set()
                    logger.info("BARGE-IN: user interrupted agent")
                    await ws.send(json.dumps({"type": "agent_interrupted"}))

                await ws.send(json.dumps({"type": "user_transcript", "text": text}))
                logger.info("User: %s", text)

                messages.append({"role": "user", "content": [{"text": text}]})
                try:
                    interrupted.clear()
                    agent_speaking = True
                    await _stream_bedrock_and_speak(ws, bedrock, messages, system, interrupted)
                    agent_speaking = False
                except Exception:
                    agent_speaking = False
                    logger.exception("Conversation turn failed")

        recv_task = asyncio.create_task(audio_receiver())
        conv_task = asyncio.create_task(conversation_loop())
        await asyncio.gather(recv_task, conv_task, return_exceptions=True)

        await stt_conn.send_close_stream()
        await asyncio.sleep(1)
        listen_task.cancel()

    logger.info("Voice agent session ended")


# ---------------------------------------------------------------------------
# WebSocket + HTTP routing
# ---------------------------------------------------------------------------

async def handle_ws(ws):
    path = urlparse(ws.request.path).path
    qs = parse_qs(urlparse(ws.request.path).query)

    if path == "/ws/call":
        record_id = (qs.get("record_id") or [""])[0]
        if not record_id:
            await ws.close(4000, "record_id required")
            return
        record = get_eligible_record(record_id)
        if not record:
            await ws.close(4004, "Unknown record_id")
            return
        logger.info("Call started: %s", record_id)
        try:
            await voice_agent(ws, record)
        except websockets.ConnectionClosed:
            logger.info("Call ended (client disconnected)")
        except Exception:
            logger.exception("Call error")

    elif path == "/ws/mic-test":
        await mic_test_session(ws)
    else:
        await ws.close(4000, "Unknown path")


async def mic_test_session(ws):
    logger.info("Mic test started")
    client = _fresh_client(config.SAGEMAKER_ENDPOINT_STT, config.SAGEMAKER_STT_REGION)

    async with client.listen.v2.connect(
        model=config.DEEPGRAM_STT_MODEL,
        encoding="linear16",
        sample_rate=str(MIC_SAMPLE_RATE),
    ) as conn:
        mic_logged = False

        def on_msg(m):
            nonlocal mic_logged
            transcript = getattr(m, "transcript", None)
            event = getattr(m, "event", None)
            if getattr(m, "request_id", None) and not transcript:
                if not mic_logged:
                    logger.info("Mic test: STT connected")
                    mic_logged = True
                return
            if transcript:
                is_final = "end" in str(event or "").lower()
                asyncio.get_event_loop().create_task(
                    ws.send(json.dumps({"type": "final" if is_final else "interim", "text": transcript})))

        conn.on(EventType.MESSAGE, on_msg)
        conn.on(EventType.ERROR, lambda e: None)
        task = asyncio.create_task(conn.start_listening())
        await asyncio.sleep(0.5)

        try:
            async for msg in ws:
                if isinstance(msg, bytes) and len(msg) > 0:
                    await conn.send_media(msg)
        except websockets.ConnectionClosed:
            pass
        await conn.send_close_stream()
        await asyncio.sleep(1)
        task.cancel()
    logger.info("Mic test ended")


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

MIC_TEST_HTML = """<!DOCTYPE html><html><head><title>Mic Test</title>
<style>body{font-family:monospace;background:#111;color:#0f0;padding:20px;max-width:800px;margin:0 auto}
h2{color:#0ff}button{font-size:18px;padding:10px 24px;margin:5px;cursor:pointer;background:#222;color:#0f0;border:1px solid #0f0}
button:hover{background:#0f0;color:#111}#status{color:#ff0;margin:10px 0}
#log{white-space:pre-wrap;margin-top:10px;padding:10px;background:#0a0a0a;border:1px solid #333;max-height:70vh;overflow-y:auto;line-height:1.6}
.final{color:#0f0;font-weight:bold}.interim{color:#888}.system{color:#0ff}</style></head><body>
<h2>Mic Test — Flux STT</h2>
<button onclick="startMic()">Start Mic</button> <button onclick="stopMic()">Stop</button>
<div id="status">Ready</div><div id="log"></div>
<script>
let ws,ctx,proc,strm;const log=document.getElementById('log'),stat=document.getElementById('status');
function addLog(m,c){const s=document.createElement('span');s.className=c||'system';s.textContent=m+'\\n';log.appendChild(s);log.scrollTop=log.scrollHeight}
async function startMic(){log.innerHTML='';stat.textContent='Connecting...';
ws=new WebSocket('ws://'+location.host+'/ws/mic-test');ws.binaryType='arraybuffer';
ws.onopen=async()=>{stat.textContent='Getting mic...';try{
strm=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});
ctx=new AudioContext();const src=ctx.createMediaStreamSource(strm);
proc=ctx.createScriptProcessor(4096,1,1);const nr=ctx.sampleRate;addLog('[mic] '+nr+'Hz -> 16000Hz');
proc.onaudioprocess=(e)=>{if(!ws||ws.readyState!==1)return;const r=e.inputBuffer.getChannelData(0),ratio=nr/16000,nl=Math.round(r.length/ratio),i16=new Int16Array(nl);
for(let i=0;i<nl;i++){const si=i*ratio,lo=Math.floor(si),hi=Math.min(lo+1,r.length-1);i16[i]=Math.max(-32768,Math.min(32767,Math.round((r[lo]*(1-(si-lo))+r[hi]*(si-lo))*32767)))}
ws.send(i16.buffer)};src.connect(proc);proc.connect(ctx.destination);stat.textContent='LIVE — speak now!';addLog('[streaming]');
}catch(e){addLog('[ERROR] '+e.message);stat.textContent='Mic error'}};
ws.onmessage=(e)=>{try{const m=JSON.parse(e.data);if(m.type==='final')addLog('>>> '+m.text,'final');
else if(m.type==='interim')addLog('... '+m.text,'interim');else addLog('['+m.type+'] '+(m.text||''),'system')}catch(x){addLog(e.data)}};
ws.onclose=()=>{stat.textContent='Disconnected';addLog('[closed]')};ws.onerror=()=>{stat.textContent='Error';addLog('[error]')};}
function stopMic(){if(proc)proc.disconnect();if(strm)strm.getTracks().forEach(t=>t.stop());if(ctx)ctx.close();if(ws)ws.close();stat.textContent='Stopped';addLog('[stopped]');}
</script></body></html>"""


async def process_request(connection, request):
    path = urlparse(request.path).path
    if path.startswith("/ws/"):
        return None
    if path == "/api/health":
        return connection.respond(http.HTTPStatus.OK, json.dumps({"status": "ok"}))
    if path == "/api/records":
        try:
            rows = load_eligible_records()
            return connection.respond(http.HTTPStatus.OK, json.dumps(rows))
        except FileNotFoundError as e:
            return connection.respond(http.HTTPStatus.INTERNAL_SERVER_ERROR, json.dumps({"detail": str(e)}))
    if path == "/api/start":
        return connection.respond(http.HTTPStatus.OK, json.dumps({"status": "ok"}))
    if path == "/mic-test":
        resp = connection.respond(http.HTTPStatus.OK, MIC_TEST_HTML)
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        return resp
    return connection.respond(http.HTTPStatus.NOT_FOUND, "Not found")


async def main():
    logger.info("Patient Connect server on port %d", PORT)
    logger.info("STT: %s (%s)", config.SAGEMAKER_ENDPOINT_STT, config.SAGEMAKER_STT_REGION)
    logger.info("TTS: %s (%s)", config.SAGEMAKER_ENDPOINT_TTS, config.SAGEMAKER_TTS_REGION)
    logger.info("LLM: %s", config.BEDROCK_MODEL_ID)
    logger.info("Mic test: http://localhost:%d/mic-test", PORT)
    logger.info("Client:   http://localhost:5173")

    async with websockets.serve(handle_ws, "0.0.0.0", PORT, process_request=process_request, max_size=2**20):
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped")
