import { useCallback, useEffect, useRef, useState } from "react";

export type ChatMessage = { role: "agent" | "user"; text: string };
export type VoiceStatus = "idle" | "connecting" | "live" | "error";

const MIC_SAMPLE_RATE = 16000;
const SPEAKER_SAMPLE_RATE = 24000;
const PROCESSOR_BUFFER = 4096;

function float32ToInt16(float32: Float32Array): Int16Array {
  const int16 = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return int16;
}

function downsample(
  buffer: Float32Array,
  fromRate: number,
  toRate: number
): Float32Array {
  if (fromRate === toRate) return buffer;
  const ratio = fromRate / toRate;
  const newLen = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLen);
  for (let i = 0; i < newLen; i++) {
    const srcIdx = i * ratio;
    const lo = Math.floor(srcIdx);
    const hi = Math.min(lo + 1, buffer.length - 1);
    const frac = srcIdx - lo;
    result[i] = buffer[lo] * (1 - frac) + buffer[hi] * frac;
  }
  return result;
}

export function useVoiceSession() {
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [lastError, setLastError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const captureCtxRef = useRef<AudioContext | null>(null);
  const playCtxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const nextPlayTimeRef = useRef(0);

  const cleanup = useCallback(() => {
    if (flushTimerRef.current) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    audioBufRef.current = [];

    processorRef.current?.disconnect();
    processorRef.current = null;

    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;

    captureCtxRef.current?.close().catch(() => {});
    captureCtxRef.current = null;
    playCtxRef.current?.close().catch(() => {});
    playCtxRef.current = null;

    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) {
      wsRef.current.close();
    }
    wsRef.current = null;
    nextPlayTimeRef.current = 0;
  }, []);

  useEffect(() => {
    return () => cleanup();
  }, [cleanup]);

  const audioBufRef = useRef<Int16Array[]>([]);
  const audioBufSamplesRef = useRef(0);
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const MIN_SAMPLES = SPEAKER_SAMPLE_RATE / 4; // 250ms = 6000 samples at 24kHz

  const flushAudioBuffer = useCallback(() => {
    flushTimerRef.current = null;
    const ctx = playCtxRef.current;
    const chunks = audioBufRef.current;
    if (!ctx || chunks.length === 0) return;

    const totalLen = chunks.reduce((s, c) => s + c.length, 0);
    const merged = new Float32Array(totalLen);
    let offset = 0;
    for (const chunk of chunks) {
      for (let i = 0; i < chunk.length; i++) {
        merged[offset++] = chunk[i] / 32768;
      }
    }
    audioBufRef.current = [];
    audioBufSamplesRef.current = 0;

    const buffer = ctx.createBuffer(1, merged.length, SPEAKER_SAMPLE_RATE);
    buffer.getChannelData(0).set(merged);

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    const now = ctx.currentTime;
    if (nextPlayTimeRef.current < now) {
      nextPlayTimeRef.current = now + 0.02;
    }
    source.start(nextPlayTimeRef.current);
    nextPlayTimeRef.current += buffer.duration;
  }, []);

  const playAudioChunk = useCallback((pcm16: ArrayBuffer) => {
    if (!playCtxRef.current) return;
    const samples = new Int16Array(pcm16);
    audioBufRef.current.push(samples);
    audioBufSamplesRef.current += samples.length;

    // Flush when we have 250ms+ of audio (avoids splitting words)
    if (audioBufSamplesRef.current >= MIN_SAMPLES) {
      if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
      flushAudioBuffer();
    } else if (!flushTimerRef.current) {
      // Safety flush after 500ms if we don't reach the threshold (end of sentence)
      flushTimerRef.current = setTimeout(() => flushAudioBuffer(), 500);
    }
  }, [flushAudioBuffer]);

  const disconnect = useCallback(() => {
    cleanup();
    setMessages([]);
    setLastError(null);
    setStatus("idle");
  }, [cleanup]);

  const connect = useCallback(
    async (recordId: string | null) => {
      if (!recordId) {
        setLastError("Select a patient row before connecting.");
        setStatus("error");
        return;
      }

      setLastError(null);
      setMessages([]);
      setStatus("connecting");

      try {
        // Audio contexts
        const captureCtx = new AudioContext();
        const playCtx = new AudioContext({ sampleRate: SPEAKER_SAMPLE_RATE });
        captureCtxRef.current = captureCtx;
        playCtxRef.current = playCtx;
        await captureCtx.resume();
        await playCtx.resume();

        const nativeRate = captureCtx.sampleRate;

        // Microphone
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
          },
        });
        streamRef.current = stream;

        // WebSocket
        const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${proto}//${window.location.host}/ws/call?record_id=${encodeURIComponent(recordId)}`;
        const ws = new WebSocket(wsUrl);
        ws.binaryType = "arraybuffer";
        wsRef.current = ws;

        ws.onopen = () => {
          setStatus("live");

          // Start mic capture after WS is open
          const source = captureCtx.createMediaStreamSource(stream);
          const processor = captureCtx.createScriptProcessor(
            PROCESSOR_BUFFER,
            1,
            1
          );
          processorRef.current = processor;

          processor.onaudioprocess = (e) => {
            if (ws.readyState !== WebSocket.OPEN) return;
            const raw = e.inputBuffer.getChannelData(0);
            const resampled = downsample(raw, nativeRate, MIC_SAMPLE_RATE);
            const int16 = float32ToInt16(resampled);
            ws.send(int16.buffer);
          };

          source.connect(processor);
          processor.connect(captureCtx.destination);
        };

        ws.onmessage = (event) => {
          if (event.data instanceof ArrayBuffer) {
            console.log(`[voice] audio chunk: ${event.data.byteLength} bytes`);
            playAudioChunk(event.data);
          } else if (typeof event.data === "string") {
            console.log("[voice] message:", event.data);
            try {
              const msg = JSON.parse(event.data);
              if (msg.type === "agent_interrupted") {
                // Barge-in: discard pending audio and reset playback
                audioBufRef.current = [];
                if (flushTimerRef.current) {
                  clearTimeout(flushTimerRef.current);
                  flushTimerRef.current = null;
                }
                const ctx = playCtxRef.current;
                if (ctx) {
                  ctx.close().catch(() => {});
                  const newCtx = new AudioContext({ sampleRate: SPEAKER_SAMPLE_RATE });
                  playCtxRef.current = newCtx;
                  nextPlayTimeRef.current = 0;
                }
              } else if (msg.type === "agent_transcript") {
                setMessages((prev) => {
                  // Update last agent bubble if it exists (streaming accumulates)
                  if (prev.length > 0 && prev[prev.length - 1].role === "agent") {
                    return [...prev.slice(0, -1), { role: "agent", text: msg.text }];
                  }
                  return [...prev, { role: "agent", text: msg.text }];
                });
              } else if (msg.type === "user_transcript") {
                setMessages((prev) => [
                  ...prev,
                  { role: "user", text: msg.text },
                ]);
              } else if (msg.type === "error") {
                setLastError(msg.message);
              }
            } catch {
              // ignore malformed JSON
            }
          }
        };

        ws.onclose = () => {
          cleanup();
          setStatus("idle");
        };

        ws.onerror = () => {
          setLastError("WebSocket error");
          cleanup();
          setStatus("error");
        };
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Connection failed";
        setLastError(msg);
        cleanup();
        setStatus("error");
      }
    },
    [cleanup, playAudioChunk]
  );

  const finalize = useCallback(() => {
    disconnect();
  }, [disconnect]);

  return {
    status,
    messages,
    lastError,
    connect,
    disconnect,
    finalize,
  };
}
