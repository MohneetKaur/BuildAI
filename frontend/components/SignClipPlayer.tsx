"use client";

import { motion } from "framer-motion";
import { ExternalLink, Hand } from "lucide-react";
import { useState } from "react";
import type { SignClip, TranscriptSegment } from "@/lib/types";

export function SignClipPlayer({ segment }: { segment: TranscriptSegment | null }) {
  if (!segment || segment.sign_clips.length === 0) {
    return (
      <div className="grid h-full place-items-center rounded-2xl border border-white/10 bg-white/[0.02] p-6 text-center min-h-[200px]">
        <div>
          <Hand className="mx-auto mb-3 h-8 w-8 text-ink-100/30" />
          <p className="text-sm text-ink-100/50">Sign clips will appear here</p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-6">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Hand className="h-4 w-4 text-accent-cyan" />
          <h3 className="text-sm font-semibold uppercase tracking-wider text-ink-100/70">
            Live signs · {segment.speaker.name}
          </h3>
        </div>
        <span className="text-[10px] uppercase tracking-wider text-ink-100/30">
          ASL vocabulary · {segment.sign_clips.length} matched
        </span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {segment.sign_clips.map((clip, i) => (
          <SignTile key={clip.id} clip={clip} delay={i * 0.08} />
        ))}
      </div>
    </div>
  );
}

function SignTile({ clip, delay }: { clip: SignClip; delay: number }) {
  const [errored, setErrored] = useState(false);
  const showVideo = !!clip.video_url && !errored;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.85 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay }}
      className="group relative aspect-square overflow-hidden rounded-xl border border-accent-cyan/20 bg-gradient-to-br from-accent-cyan/15 via-accent-violet/10 to-accent-fuchsia/10"
    >
      {/* subtle animated backdrop */}
      <motion.div
        className="absolute inset-0 opacity-30"
        animate={{
          background: [
            "radial-gradient(circle at 30% 30%, rgba(6,182,212,0.4), transparent 70%)",
            "radial-gradient(circle at 70% 70%, rgba(139,92,246,0.4), transparent 70%)",
            "radial-gradient(circle at 30% 30%, rgba(6,182,212,0.4), transparent 70%)",
          ],
        }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
      />

      {showVideo ? (
        <video
          src={clip.video_url}
          autoPlay
          loop
          muted
          playsInline
          onError={() => setErrored(true)}
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : (
        <div className="absolute inset-0 grid place-items-center">
          <motion.div
            animate={{ y: [0, -6, 0], rotate: [0, -5, 5, 0] }}
            transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut", delay }}
            className="text-6xl"
            aria-label={`Sign for ${clip.word}`}
          >
            🖐️
          </motion.div>
        </div>
      )}

      {/* word label gradient */}
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/50 to-transparent p-2 text-center text-xs font-semibold text-white">
        {clip.word}
      </div>

      {/* subtle dictionary link on hover (no apologetic 'fallback' badge) */}
      <a
        href={`https://www.handspeak.com/word/?word=${encodeURIComponent(clip.word)}`}
        target="_blank"
        rel="noopener noreferrer"
        className="absolute right-1.5 top-1.5 grid h-5 w-5 place-items-center rounded-full bg-black/40 opacity-0 backdrop-blur-sm transition group-hover:opacity-100"
        title={`Look up "${clip.word}" in ASL dictionary`}
      >
        <ExternalLink className="h-2.5 w-2.5 text-white" />
      </a>
    </motion.div>
  );
}
