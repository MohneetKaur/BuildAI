"use client";

import { motion } from "framer-motion";
import { Activity, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import type { LLMStats } from "@/lib/types";

export function LLMStatsFooter({ pollMs = 2000 }: { pollMs?: number }) {
  const [stats, setStats] = useState<LLMStats | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const s = await api.stats();
        if (!cancelled) setStats(s);
      } catch {
        // backend offline — leave last known value
      }
    }
    tick();
    const id = setInterval(tick, pollMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [pollMs]);

  if (!stats) return null;

  const fallbackRate = stats.total_calls > 0 ? Math.round((stats.fallback_count / stats.total_calls) * 100) : 0;

  return (
    <motion.div
      initial={{ y: 30, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-ink-950/85 backdrop-blur"
    >
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-2.5 text-xs">
        <div className="flex items-center gap-2 text-ink-100/60">
          <Activity className="h-3.5 w-3.5 text-accent-violet" />
          <span className="hidden sm:inline">LLM router · live</span>
        </div>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
          <Stat label="Calls" value={stats.total_calls} />
          <Stat
            label="Gemini"
            value={stats.gemini_calls}
            color="text-accent-cyan"
          />
          <Stat
            label="Claude"
            value={stats.claude_calls}
            color="text-accent-violet"
          />
          {stats.fallback_count > 0 && (
            <Stat
              label="Fallbacks"
              value={`${stats.fallback_count} (${fallbackRate}%)`}
              color="text-yellow-300"
            />
          )}
          <Stat label="Avg" value={`${stats.avg_latency_ms}ms`} />
          <Stat label="Tokens" value={stats.total_tokens.toLocaleString()} />
          {stats.last_provider && (
            <div className="flex items-center gap-1 text-ink-100/60">
              <Zap className="h-3 w-3 text-accent-lime" />
              <span>last: {stats.last_provider}</span>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

function Stat({ label, value, color }: { label: string; value: number | string; color?: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-ink-100/40">{label}:</span>
      <span className={`font-semibold ${color || "text-ink-50"}`}>{value}</span>
    </div>
  );
}
