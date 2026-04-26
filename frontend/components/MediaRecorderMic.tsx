"use client";

import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, Loader2, Mic, MicOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { encodeWAV, mergeFloat32 } from "@/lib/wav-encoder";

const TARGET_SAMPLE_RATE = 16000; // pyannote + Whisper both like 16kHz mono
const MIN_CHUNK_SECONDS = 1.5; // discard accidental taps shorter than this

type Props = {
  onAudioReady: (wav: Blob) => Promise<void>;
  disabled?: boolean;
  busy?: boolean;
};

export function MediaRecorderMic({ onAudioReady, disabled, busy }: Props) {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [level, setLevel] = useState(0); // 0..1 input volume

  const audioCtxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const sampleRateRef = useRef<number>(TARGET_SAMPLE_RATE);
  const startTimeRef = useRef<number>(0);
  const tickerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function start() {
    setError(null);
    chunksRef.current = [];
    setElapsed(0);
    setLevel(0);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      });
      streamRef.current = stream;

      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)({
        sampleRate: TARGET_SAMPLE_RATE,
      });
      // Some browsers ignore the requested sampleRate — capture actual rate
      sampleRateRef.current = ctx.sampleRate;
      audioCtxRef.current = ctx;

      const source = ctx.createMediaStreamSource(stream);
      sourceRef.current = source;

      // ScriptProcessorNode is deprecated but works everywhere & is simpler than AudioWorklet
      const bufferSize = 4096;
      const processor = ctx.createScriptProcessor(bufferSize, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0);
        // copy because the underlying buffer is reused
        chunksRef.current.push(new Float32Array(input));
        // crude RMS for level meter
        let sum = 0;
        for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
        setLevel(Math.min(1, Math.sqrt(sum / input.length) * 4));
      };

      source.connect(processor);
      processor.connect(ctx.destination);

      startTimeRef.current = Date.now();
      tickerRef.current = setInterval(() => {
        setElapsed((Date.now() - startTimeRef.current) / 1000);
      }, 100);
      setRecording(true);
    } catch (e: any) {
      setError(e?.message || "Failed to access microphone");
    }
  }

  async function stop() {
    if (!recording) return;
    setRecording(false);

    if (tickerRef.current) clearInterval(tickerRef.current);
    tickerRef.current = null;

    // Disconnect the audio graph cleanly
    try {
      processorRef.current?.disconnect();
      sourceRef.current?.disconnect();
      streamRef.current?.getTracks().forEach((t) => t.stop());
      await audioCtxRef.current?.close();
    } catch {
      /* noop */
    }
    audioCtxRef.current = null;
    streamRef.current = null;
    sourceRef.current = null;
    processorRef.current = null;

    const totalSamples = chunksRef.current.reduce((n, c) => n + c.length, 0);
    const seconds = totalSamples / sampleRateRef.current;
    if (seconds < MIN_CHUNK_SECONDS) {
      setError(`Too short (${seconds.toFixed(1)}s) — speak for at least ${MIN_CHUNK_SECONDS}s`);
      chunksRef.current = [];
      setElapsed(0);
      return;
    }

    const merged = mergeFloat32(chunksRef.current);
    const wav = encodeWAV(merged, sampleRateRef.current);
    chunksRef.current = [];
    setElapsed(0);
    setLevel(0);

    try {
      await onAudioReady(wav);
    } catch (e: any) {
      setError(e?.message || "Failed to process audio");
    }
  }

  useEffect(
    () => () => {
      // teardown on unmount
      if (recording) stop();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const showProcessing = busy && !recording;

  return (
    <div className="space-y-2">
      <button
        onClick={recording ? stop : start}
        disabled={disabled || showProcessing}
        className={`flex w-full items-center justify-center gap-2 rounded-xl py-3 text-sm font-semibold text-white shadow-glow transition hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100 ${
          recording
            ? "bg-gradient-to-r from-red-500 to-red-600 animate-pulse-soft"
            : "bg-gradient-to-r from-accent-violet to-accent-fuchsia"
        }`}
      >
        {showProcessing ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Whisper transcribing...
          </>
        ) : recording ? (
          <>
            <MicOff className="h-4 w-4" />
            Stop & transcribe ({elapsed.toFixed(1)}s)
          </>
        ) : (
          <>
            <Mic className="h-4 w-4" />
            Start recording
          </>
        )}
      </button>

      <AnimatePresence>
        {recording && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200"
          >
            <div className="mb-1.5 flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-red-500" />
              </span>
              Capturing audio · stop when done
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
              <motion.div
                animate={{ width: `${level * 100}%` }}
                transition={{ type: "spring", damping: 30, stiffness: 200 }}
                className="h-full rounded-full bg-gradient-to-r from-red-400 to-red-500"
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {error && !recording && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs">
          <div className="flex items-center gap-1.5 font-semibold text-red-200">
            <AlertCircle className="h-3.5 w-3.5" />
            {error}
          </div>
        </div>
      )}

      <p className="text-center text-[10px] uppercase tracking-wider text-ink-100/30">
        MediaRecorder + Whisper · pyannote diarization · no Google
      </p>
    </div>
  );
}
