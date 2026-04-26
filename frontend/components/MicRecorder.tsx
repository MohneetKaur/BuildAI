"use client";

import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, Mic, MicOff, Wifi } from "lucide-react";
import { useEffect, useRef, useState } from "react";

type Props = {
  onFinalUtterance: (text: string) => void;
  disabled?: boolean;
};

const MAX_RETRIES = 3;

const ERROR_MESSAGES: Record<string, { msg: string; hint: string }> = {
  "not-allowed": {
    msg: "Microphone permission denied",
    hint: "Click the lock icon in the address bar → Site settings → allow microphone, then refresh.",
  },
  network: {
    msg: "Web Speech can't reach Google's servers",
    hint: "Common Chrome/macOS issue. Try: (1) disable VPN, (2) sign into Chrome with a Google account, (3) use Edge instead, or (4) use the text input below.",
  },
  "service-not-allowed": {
    msg: "Speech service blocked",
    hint: "Browser policy blocking speech recognition. Use the text input below.",
  },
  "audio-capture": {
    msg: "No microphone detected",
    hint: "Plug in / enable a microphone and try again.",
  },
};

export function MicRecorder({ onFinalUtterance, disabled }: Props) {
  const [supported, setSupported] = useState<boolean | null>(null);
  const [recording, setRecording] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<{ code: string; msg: string; hint: string } | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const recognitionRef = useRef<any>(null);
  const recordingRef = useRef(false);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    setSupported(!!SR);
  }, []);

  function buildRecognition() {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) return null;
    const recognition = new SR();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    return recognition;
  }

  function start(isRetry = false) {
    if (typeof window === "undefined") return;
    const recognition = buildRecognition();
    if (!recognition) {
      setSupported(false);
      return;
    }

    if (!isRetry) {
      setError(null);
      setRetryCount(0);
    }
    setInterim("");

    recognition.onresult = (event: any) => {
      // any successful result clears error state and resets retry counter
      if (error) setError(null);
      if (retryCount > 0) setRetryCount(0);

      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        if (r.isFinal) {
          const text = r[0].transcript.trim();
          if (text) onFinalUtterance(text);
          interimText = "";
        } else {
          interimText += r[0].transcript;
        }
      }
      setInterim(interimText);
    };

    recognition.onerror = (event: any) => {
      const code = event.error || "unknown";
      if (code === "no-speech" || code === "aborted") {
        // benign — chrome ends after silence; onend will restart if still recording
        return;
      }
      const known = ERROR_MESSAGES[code] || { msg: code, hint: "Use the text input below as a fallback." };
      setError({ code, ...known });

      // network errors are often transient — auto-retry with backoff
      if (code === "network" && recordingRef.current) {
        setRetryCount((n) => {
          const next = n + 1;
          if (next <= MAX_RETRIES) {
            retryTimerRef.current = setTimeout(() => {
              try {
                recognition.start();
              } catch {
                /* will trigger onend → restart */
              }
            }, 1500 * next);
          } else {
            // give up, stop recording
            recordingRef.current = false;
            setRecording(false);
          }
          return next;
        });
      }
    };

    recognition.onend = () => {
      // chrome cuts off after ~10s of silence — auto-restart if we're still in recording mode
      if (recordingRef.current && !error) {
        try {
          recognition.start();
        } catch {
          setRecording(false);
        }
      }
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
      setRecording(true);
      recordingRef.current = true;
    } catch (e: any) {
      setError({ code: "start-failed", msg: e.message || "Failed to start", hint: "Refresh the page and try again." });
    }
  }

  function stop() {
    recordingRef.current = false;
    setRecording(false);
    setInterim("");
    setRetryCount(0);
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {}
    }
  }

  useEffect(() => {
    recordingRef.current = recording;
  }, [recording]);

  useEffect(() => () => stop(), []);

  if (supported === false) {
    return (
      <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/10 p-3 text-xs text-yellow-200">
        <AlertCircle className="mb-1 inline h-3.5 w-3.5" /> Web Speech API not supported in this browser. Use Chrome
        or Edge for live microphone, or use the text input below.
      </div>
    );
  }

  const hasNetworkError = error?.code === "network";
  const exhaustedRetries = hasNetworkError && retryCount > MAX_RETRIES;

  return (
    <div className="space-y-2">
      <button
        onClick={recording ? stop : () => start()}
        disabled={disabled || supported === null}
        className={`flex w-full items-center justify-center gap-2 rounded-xl py-3 text-sm font-semibold text-white shadow-glow transition hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100 ${
          recording
            ? "bg-gradient-to-r from-red-500 to-red-600 animate-pulse-soft"
            : "bg-gradient-to-r from-accent-violet to-accent-fuchsia"
        }`}
      >
        {recording ? (
          <>
            <MicOff className="h-4 w-4" />
            Stop recording
          </>
        ) : (
          <>
            <Mic className="h-4 w-4" />
            Start recording
          </>
        )}
      </button>

      <AnimatePresence>
        {recording && !error && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200"
          >
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-red-500" />
            </span>
            Listening — speak now
          </motion.div>
        )}

        {recording && hasNetworkError && retryCount <= MAX_RETRIES && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center gap-2 rounded-xl border border-yellow-500/30 bg-yellow-500/10 px-3 py-2 text-xs text-yellow-200"
          >
            <Wifi className="h-3.5 w-3.5 animate-pulse" />
            Network hiccup · retry {retryCount}/{MAX_RETRIES}...
          </motion.div>
        )}
      </AnimatePresence>

      {interim && (
        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-2 text-xs italic text-ink-100/60">
          "{interim}"
        </div>
      )}

      {error && (!recording || exhaustedRetries) && (
        <div className="space-y-1.5 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs">
          <div className="flex items-center gap-1.5 font-semibold text-red-200">
            <AlertCircle className="h-3.5 w-3.5" />
            {error.msg}
          </div>
          <p className="text-red-100/80">{error.hint}</p>
        </div>
      )}

      <p className="text-center text-[10px] uppercase tracking-wider text-ink-100/30">
        Web Speech API · Chrome / Edge · text input below works always
      </p>
    </div>
  );
}
