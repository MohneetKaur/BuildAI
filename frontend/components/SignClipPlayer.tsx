"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ExternalLink, Hand, Pause, Play, RotateCcw, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { SignClip, TranscriptSegment } from "@/lib/types";

const FALLBACK_DURATION_MS = 1800;
const TRANSITION_MS = 250;

export function SignClipPlayer({ segment }: { segment: TranscriptSegment | null }) {
  const clips = segment?.sign_clips ?? [];
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [errored, setErrored] = useState<Set<string>>(new Set());
  const videoRef = useRef<HTMLVideoElement>(null);
  const fallbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Reset queue whenever a new segment arrives
  useEffect(() => {
    setIndex(0);
    setPlaying(true);
    setErrored(new Set());
  }, [segment?.id]);

  // Drive auto-advance for YouTube embeds + clips with no <video> end event
  useEffect(() => {
    if (fallbackTimerRef.current) clearTimeout(fallbackTimerRef.current);
    if (!playing || clips.length === 0) return;
    const current = clips[index];
    const isMp4 = current?.video_type === "mp4" && !errored.has(current.id);
    if (isMp4) return; // <video> onEnded will advance us

    const dur = current?.duration_ms || FALLBACK_DURATION_MS;
    fallbackTimerRef.current = setTimeout(() => advance(), dur);
    return () => {
      if (fallbackTimerRef.current) clearTimeout(fallbackTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, playing, clips, errored]);

  function advance() {
    setIndex((i) => (i + 1 < clips.length ? i + 1 : 0));
  }

  function jumpTo(i: number) {
    setIndex(i);
    setPlaying(true);
  }

  function togglePlay() {
    setPlaying((p) => !p);
    if (videoRef.current) {
      if (videoRef.current.paused) videoRef.current.play().catch(() => {});
      else videoRef.current.pause();
    }
  }

  function replay() {
    setIndex(0);
    setPlaying(true);
  }

  if (!segment || clips.length === 0) {
    return (
      <div className="grid h-full place-items-center rounded-2xl border border-white/10 bg-white/[0.02] p-6 text-center min-h-[280px]">
        <div>
          <Hand className="mx-auto mb-3 h-8 w-8 text-ink-100/30" />
          <p className="text-sm text-ink-100/50">Sign-language player ready</p>
          <p className="mt-1 text-xs text-ink-100/30">Speak or type a line — signs play continuously here</p>
        </div>
      </div>
    );
  }

  const current = clips[index];
  const isMp4 = current.video_type === "mp4" && !errored.has(current.id);
  const isYoutube = current.video_type === "youtube" && !errored.has(current.id);
  const youtubeEmbed = current.youtube_id
    ? buildYouTubeEmbed(current.youtube_id, current.start_seconds, current.end_seconds, playing)
    : null;

  return (
    <div className="rounded-2xl border border-white/10 bg-gradient-to-b from-white/[0.04] to-white/[0.01] p-5">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Hand className="h-4 w-4 text-accent-cyan" />
          <h3 className="text-sm font-semibold uppercase tracking-wider text-ink-100/70">
            Live signing · {segment.speaker.name}
          </h3>
        </div>
        <span className="text-[10px] uppercase tracking-wider text-ink-100/40">
          WLASL · clip {index + 1} of {clips.length}
        </span>
      </div>

      {/* Hero player */}
      <div className="relative mx-auto aspect-video max-w-[560px] overflow-hidden rounded-2xl border border-accent-cyan/20 bg-black shadow-glow">
        {/* Animated radial backdrop */}
        <motion.div
          className="absolute inset-0 opacity-25"
          animate={{
            background: [
              "radial-gradient(circle at 30% 30%, rgba(6,182,212,0.5), transparent 60%)",
              "radial-gradient(circle at 70% 70%, rgba(139,92,246,0.5), transparent 60%)",
              "radial-gradient(circle at 30% 30%, rgba(6,182,212,0.5), transparent 60%)",
            ],
          }}
          transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
        />

        <AnimatePresence mode="popLayout">
          {isMp4 && (
            <motion.video
              key={current.id}
              ref={videoRef}
              src={current.video_url}
              autoPlay={playing}
              muted
              playsInline
              onEnded={advance}
              onError={() => {
                setErrored((s) => {
                  const next = new Set(s);
                  next.add(current.id);
                  return next;
                });
              }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: TRANSITION_MS / 1000 }}
              className="absolute inset-0 h-full w-full object-contain bg-black"
            />
          )}
          {isYoutube && youtubeEmbed && (
            <motion.iframe
              key={current.id}
              src={youtubeEmbed}
              title={`ASL sign: ${current.word}`}
              allow="autoplay; encrypted-media; picture-in-picture"
              referrerPolicy="strict-origin-when-cross-origin"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: TRANSITION_MS / 1000 }}
              className="absolute inset-0 h-full w-full"
            />
          )}
          {!isMp4 && !isYoutube && (
            <motion.div
              key={current.id + "-fallback"}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 grid place-items-center"
            >
              <motion.div
                animate={{ y: [0, -8, 0], rotate: [0, -6, 6, 0] }}
                transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
                className="text-8xl"
              >
                🖐️
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Current word overlay */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/95 via-black/50 to-transparent p-4">
          <AnimatePresence mode="wait">
            <motion.div
              key={current.id + "-label"}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2 }}
              className="text-center"
            >
              <div className="text-3xl font-bold text-white drop-shadow-[0_2px_12px_rgba(0,0,0,0.8)]">
                {current.word}
              </div>
              <div className="mt-0.5 text-[10px] uppercase tracking-widest text-white/60">
                {current.source || current.video_type}
              </div>
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Top-right: original-clip link */}
        <a
          href={current.video_url}
          target="_blank"
          rel="noopener noreferrer"
          className="absolute right-2 top-2 grid h-7 w-7 place-items-center rounded-full bg-black/60 backdrop-blur-sm transition hover:bg-black/80"
          title="Open original clip"
        >
          <ExternalLink className="h-3.5 w-3.5 text-white" />
        </a>
      </div>

      {/* Transport controls */}
      <div className="mt-4 flex items-center justify-center gap-3">
        <button
          onClick={replay}
          className="flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/5 transition hover:bg-white/10"
          title="Replay sequence"
        >
          <RotateCcw className="h-4 w-4 text-ink-100/80" />
        </button>
        <button
          onClick={togglePlay}
          className="flex h-11 w-11 items-center justify-center rounded-full bg-gradient-to-br from-accent-violet to-accent-fuchsia text-white shadow-glow transition hover:scale-105"
          title={playing ? "Pause" : "Play"}
        >
          {playing ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5 translate-x-0.5" />}
        </button>
        <button
          onClick={advance}
          className="flex h-9 px-3 items-center justify-center rounded-full border border-white/10 bg-white/5 text-xs text-ink-100/80 transition hover:bg-white/10"
          title="Skip to next sign"
        >
          Next →
        </button>
      </div>

      {/* Word queue / chips */}
      <div className="mt-4 flex flex-wrap justify-center gap-1.5">
        {clips.map((c, i) => {
          const active = i === index;
          const past = i < index;
          return (
            <button
              key={c.id}
              onClick={() => jumpTo(i)}
              className={`rounded-full border px-2.5 py-1 text-xs transition ${
                active
                  ? "border-accent-cyan bg-accent-cyan/20 font-semibold text-white shadow-[0_0_18px_rgba(6,182,212,0.45)]"
                  : past
                    ? "border-white/10 bg-white/[0.02] text-ink-100/40"
                    : "border-white/10 bg-white/[0.04] text-ink-100/70 hover:bg-white/[0.08]"
              }`}
            >
              {active && (
                <motion.span
                  layoutId="active-dot"
                  className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-accent-cyan"
                />
              )}
              {c.word}
            </button>
          );
        })}
      </div>

      {/* Avatar mode placeholder (sign.mt-style 3D signing avatar — coming next) */}
      <div className="mt-4 flex items-center justify-center gap-2 rounded-full border border-white/5 bg-white/[0.02] py-1.5 px-3 text-[10px] uppercase tracking-wider text-ink-100/40">
        <Sparkles className="h-3 w-3 text-accent-violet" />
        <span>Avatar mode (3D continuous signing) — coming Q3</span>
      </div>
    </div>
  );
}

function buildYouTubeEmbed(
  videoId: string,
  startSec: number,
  endSec: number | null,
  autoplay: boolean,
): string {
  const params = new URLSearchParams({
    autoplay: autoplay ? "1" : "0",
    mute: "1",
    controls: "0",
    loop: "0",
    modestbranding: "1",
    rel: "0",
    playsinline: "1",
  });
  if (startSec > 0) params.set("start", String(Math.floor(startSec)));
  if (endSec && endSec > 0) params.set("end", String(Math.ceil(endSec)));
  return `https://www.youtube.com/embed/${videoId}?${params.toString()}`;
}
