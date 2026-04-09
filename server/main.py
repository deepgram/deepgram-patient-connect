"""Patient Connect voice agent server.

Uses websockets + asyncio.run() directly (NOT uvicorn/FastAPI) because
deepgram-sagemaker 0.2.1 v2/listen only works with asyncio.run().

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
import struct
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


# ---------------------------------------------------------------------------
# WAV header for STT (endpoint auto-detects format from header)
# ---------------------------------------------------------------------------

def _wav_header(sr=16000):
    br, ba = sr * 2, 2
    return struct.pack("<4sI4s4sIHHIIHH4sI",
        b"RIFF", 0x7FFFFFFF + 36, b"WAVE",
        b"fmt ", 16, 1, 1, sr, br, ba, 16, b"data", 0x7FFFFFFF)


# ---------------------------------------------------------------------------
# TTS: open fresh connection per sentence (SageMaker closes idle streams)
# ---------------------------------------------------------------------------

async def _synthesize(text: str) -> list[bytes]:
    """Synthesize text via Aura-2 TTS on SageMaker. Returns PCM16 chunks."""
    logger.info("TTS: '%s' (%d chars)", text[:60], len(text))
    audio: list[bytes] = []
    flushed = asyncio.Event()

    restore_transport()
    tts_factory = SageMakerTransportFactory(
        endpoint_name=config.SAGEMAKER_ENDPOINT_TTS, region=config.SAGEMAKER_TTS_REGION)
    tts_client = AsyncDeepgramClient(api_key="unused", transport_factory=tts_factory)

    try:
        async with tts_client.speak.v1.connect(
            model=config.DEEPGRAM_TTS_MODEL,
            encoding="linear16",
            sample_rate=str(TTS_SAMPLE_RATE),
        ) as conn:
            def on_msg(d):
                if isinstance(d, (bytes, bytearray)):
                    audio.append(bytes(d))
                elif isinstance(d, SpeakV1Flushed):
                    flushed.set()

            def on_err(e):
                if "STREAM_BROKEN" not in repr(e):
                    logger.error("TTS error: %s", e)

            conn.on(EventType.MESSAGE, on_msg)
            conn.on(EventType.ERROR, on_err)
            task = asyncio.create_task(conn.start_listening())
            await asyncio.sleep(0.5)
            await conn.send_text(SpeakV1Text(type="Speak", text=text))
            await conn.send_flush(SpeakV1Flush(type="Flush"))
            try:
                await asyncio.wait_for(flushed.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                logger.warning("TTS: flushed timeout")
            await asyncio.sleep(0.3)
            await conn.send_close(SpeakV1Close(type="Close"))
            await asyncio.sleep(0.5)
            task.cancel()
    finally:
        restore_transport()

    logger.info("TTS: %d chunks (%d bytes)", len(audio), sum(len(c) for c in audio))
    return audio


async def _speak(ws, text: str) -> None:
    """Synthesize text and send audio + transcript to browser."""
    await ws.send(json.dumps({"type": "agent_transcript", "text": text}))
    for sentence in _SENTENCE_SPLIT.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        try:
            chunks = await _synthesize(sentence)
            for chunk in chunks:
                await ws.send(chunk)
        except Exception:
            logger.exception("TTS failed: %s", sentence[:60])


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

    # -- Send greeting (TTS only, no LLM) ----------------------------------
    logger.info("Greeting: %s", greeting[:60])
    await _speak(ws, greeting)
    messages.append({"role": "assistant", "content": [{"text": greeting}]})

    # -- Open STT (AFTER greeting so TTS factory doesn't conflict) ----------
    restore_transport()
    stt_factory = SageMakerTransportFactory(
        endpoint_name=config.SAGEMAKER_ENDPOINT_STT, region=config.SAGEMAKER_STT_REGION)
    stt_client = AsyncDeepgramClient(api_key="unused", transport_factory=stt_factory)

    async with stt_client.listen.v2.connect(model=config.DEEPGRAM_STT_MODEL) as stt_conn:

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
        logger.info("STT: ready for audio")

        # -- Audio receiver: browser → STT ----------------------------------
        running = True
        wav_sent = False

        async def audio_receiver():
            nonlocal running, wav_sent
            try:
                async for msg in ws:
                    if isinstance(msg, bytes) and len(msg) > 0:
                        if not wav_sent:
                            await stt_conn.send_media(_wav_header(MIC_SAMPLE_RATE) + msg)
                            wav_sent = True
                        else:
                            await stt_conn.send_media(msg)
            except websockets.ConnectionClosed:
                pass
            running = False

        # -- Conversation loop: transcript → Bedrock → TTS → browser -------
        async def conversation_loop():
            while running:
                try:
                    text = await asyncio.wait_for(transcript_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                await ws.send(json.dumps({"type": "user_transcript", "text": text}))
                logger.info("User: %s", text)

                messages.append({"role": "user", "content": [{"text": text}]})
                try:
                    resp = await asyncio.to_thread(
                        bedrock.converse,
                        modelId=config.BEDROCK_MODEL_ID,
                        messages=messages,
                        system=[{"text": system}],
                        inferenceConfig={"maxTokens": 600, "temperature": 0.4},
                    )
                    reply = resp["output"]["message"]["content"][0]["text"]
                    messages.append({"role": "assistant", "content": [{"text": reply}]})
                    logger.info("Agent: %s", reply[:80])

                    # TTS swaps factory, then restores — STT conn stays alive
                    await _speak(ws, reply)

                    # Re-install STT factory for any future STT connections
                    restore_transport()
                    AsyncDeepgramClient(api_key="unused", transport_factory=stt_factory)

                except Exception:
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
    """Standalone mic test — browser audio → STT → transcripts back."""
    logger.info("Mic test started")
    restore_transport()
    factory = SageMakerTransportFactory(
        endpoint_name=config.SAGEMAKER_ENDPOINT_STT, region=config.SAGEMAKER_STT_REGION)
    client = AsyncDeepgramClient(api_key="unused", transport_factory=factory)

    async with client.listen.v2.connect(model=config.DEEPGRAM_STT_MODEL) as conn:
        mic_connected_logged = False

        def on_msg(m):
            nonlocal mic_connected_logged
            transcript = getattr(m, "transcript", None)
            event = getattr(m, "event", None)
            if getattr(m, "request_id", None) and not transcript:
                if not mic_connected_logged:
                    logger.info("Mic test: STT connected")
                    mic_connected_logged = True
                return
            if transcript:
                is_final = "end" in str(event or "").lower()
                asyncio.get_event_loop().create_task(
                    ws.send(json.dumps({"type": "final" if is_final else "interim", "text": transcript})))

        conn.on(EventType.MESSAGE, on_msg)
        conn.on(EventType.ERROR, lambda e: None)
        task = asyncio.create_task(conn.start_listening())
        await asyncio.sleep(0.5)

        hdr_sent = False
        try:
            async for msg in ws:
                if isinstance(msg, bytes) and len(msg) > 0:
                    if not hdr_sent:
                        await conn.send_media(_wav_header() + msg)
                        hdr_sent = True
                    else:
                        await conn.send_media(msg)
        except websockets.ConnectionClosed:
            pass
        await conn.send_close_stream()
        await asyncio.sleep(1)
        task.cancel()
    logger.info("Mic test ended")


# ---------------------------------------------------------------------------
# HTTP request handler (REST API + debug pages)
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
    """Handle HTTP requests (REST API + HTML pages). Return None for WebSocket upgrade."""
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
            return connection.respond(
                http.HTTPStatus.INTERNAL_SERVER_ERROR,
                json.dumps({"detail": str(e)}))

    if path == "/api/start":
        return connection.respond(http.HTTPStatus.OK, json.dumps({"status": "ok"}))

    if path == "/mic-test":
        resp = connection.respond(http.HTTPStatus.OK, MIC_TEST_HTML)
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        return resp

    return connection.respond(http.HTTPStatus.NOT_FOUND, "Not found")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    logger.info("Patient Connect server on port %d", PORT)
    logger.info("STT: %s (%s)", config.SAGEMAKER_ENDPOINT_STT, config.SAGEMAKER_STT_REGION)
    logger.info("TTS: %s (%s)", config.SAGEMAKER_ENDPOINT_TTS, config.SAGEMAKER_TTS_REGION)
    logger.info("LLM: %s", config.BEDROCK_MODEL_ID)
    logger.info("Mic test: http://localhost:%d/mic-test", PORT)
    logger.info("Client:   http://localhost:5173")

    async with websockets.serve(
        handle_ws,
        "0.0.0.0",
        PORT,
        process_request=process_request,
        max_size=2**20,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped")
