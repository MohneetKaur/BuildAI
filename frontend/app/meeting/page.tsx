"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, Loader2, Play, Send, Sparkles, Square, Zap } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ActionItemsList } from "@/components/ActionItemsList";
import { AgentActivityPanel } from "@/components/AgentActivityPanel";
import { CaptionStream } from "@/components/CaptionStream";
import { LLMStatsFooter } from "@/components/LLMStatsFooter";
import { LanguagePicker } from "@/components/LanguagePicker";
import { MediaRecorderMic } from "@/components/MediaRecorderMic";
import { SignClipPlayer } from "@/components/SignClipPlayer";
import { SpeakerCard } from "@/components/SpeakerCard";
import { api } from "@/lib/api-client";
import type {
  AgentEvent,
  CreateMeetingResponse,
  MeetingSummary,
  Speaker,
  StreamEvent,
  TranscriptSegment,
} from "@/lib/types";

const DEMO_PROMPTS = [
  "Quick standup. Today I'm deploying the new auth service.",
  "I have a blocker with the database migration, need help.",
  "Sarah will own the deploy and Raj reviews tomorrow morning.",
  "Sounds good. The deadline for the deploy is end of day.",
  "Thank you. I'll send a question if I get stuck.",
];

export default function MeetingPage() {
  const [meeting, setMeeting] = useState<CreateMeetingResponse | null>(null);
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [activeSpeakerId, setActiveSpeakerId] = useState<string | null>(null);
  const [latestSegment, setLatestSegment] = useState<TranscriptSegment | null>(null);
  const [busy, setBusy] = useState(false);
  const [demoIndex, setDemoIndex] = useState(0);
  const [manualText, setManualText] = useState("");
  const [summary, setSummary] = useState<MeetingSummary | null>(null);
  const [language, setLanguage] = useState("en");
  const [useStreaming, setUseStreaming] = useState(false);
  const [health, setHealth] = useState<{
    has_gemini: boolean;
    has_claude: boolean;
    has_hf_token: boolean;
    status: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.health().then((h) => setHealth(h)).catch((e) => setError(`Backend offline: ${e.message}`));
  }, []);

  async function startMeeting() {
    setError(null);
    try {
      const m = await api.createMeeting("Sprint standup demo", ["Sarah", "Raj", "Priya"], "general", language);
      setMeeting(m);
      const initial: Speaker[] = [
        { id: "1", name: "Sarah", color: "#6366f1" },
        { id: "2", name: "Raj", color: "#ec4899" },
        { id: "3", name: "Priya", color: "#22c55e" },
      ];
      setSpeakers(initial);
      setSummary(null);
      setTranscript([]);
      setEvents([]);
      setDemoIndex(0);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function sendSegmentBatch(text: string) {
    if (!meeting) return;
    const res = await api.transcribe(meeting.meeting_id, text, language);
    setTranscript((t) => [...t, res.segment]);
    setLatestSegment(res.segment);
    setActiveSpeakerId(res.segment.speaker.id);
    setEvents((ev) => [...ev, ...res.events]);
    setTimeout(() => setActiveSpeakerId(null), 1500);
  }

  async function sendSegmentStreaming(text: string) {
    if (!meeting) return;
    await api.transcribeStream(meeting.meeting_id, text, language, (event: StreamEvent) => {
      if (event.type === "agent" && event.agent_event) {
        setEvents((ev) => [...ev, event.agent_event!]);
      } else if (event.type === "segment" && event.segment) {
        const seg = event.segment;
        setTranscript((t) => [...t, seg]);
        setLatestSegment(seg);
        setActiveSpeakerId(seg.speaker.id);
        setTimeout(() => setActiveSpeakerId(null), 1500);
      }
    });
  }

  async function sendSegment(text: string) {
    if (!meeting || busy) return;
    setBusy(true);
    setError(null);
    try {
      if (useStreaming) {
        await sendSegmentStreaming(text);
      } else {
        await sendSegmentBatch(text);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function sendAudio(wav: Blob) {
    if (!meeting || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.transcribeAudio(meeting.meeting_id, wav, language);
      setTranscript((t) => [...t, res.segment]);
      setLatestSegment(res.segment);
      setActiveSpeakerId(res.segment.speaker.id);
      setEvents((ev) => [...ev, ...res.events]);
      setTimeout(() => setActiveSpeakerId(null), 1500);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function nextDemoSegment() {
    if (demoIndex >= DEMO_PROMPTS.length) return;
    await sendSegment(DEMO_PROMPTS[demoIndex]);
    setDemoIndex(demoIndex + 1);
  }

  async function endMeeting() {
    if (!meeting) return;
    setBusy(true);
    try {
      const s = await api.endMeeting(meeting.meeting_id);
      setSummary(s);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden pb-16">
      <div className="absolute inset-0 grid-bg opacity-30" />
      <div className="absolute -top-40 left-1/2 h-[500px] w-[500px] -translate-x-1/2 rounded-full bg-accent-violet/20 blur-3xl" />

      <div className="relative z-10 mx-auto max-w-7xl px-6 py-10">
        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-sm text-ink-100/60 transition hover:text-ink-50"
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </Link>
          <div className="flex items-center gap-3">
            <LanguagePicker value={language} onChange={setLanguage} disabled={busy} />
            <button
              onClick={() => setUseStreaming((s) => !s)}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] uppercase tracking-wider transition ${
                useStreaming
                  ? "border-accent-lime/30 bg-accent-lime/10 text-accent-lime"
                  : "border-white/10 bg-white/5 text-ink-100/60"
              }`}
            >
              <Zap className="h-3 w-3" />
              {useStreaming ? "SSE on" : "SSE off"}
            </button>
            {health && (
              <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs">
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    health.status === "ok" ? "bg-accent-lime animate-pulse-soft" : "bg-yellow-400"
                  }`}
                />
                <span className="text-ink-100/70">
                  {health.has_gemini && "Gemini"}
                  {health.has_gemini && health.has_claude && " + "}
                  {health.has_claude && "Claude"}
                  {!health.has_gemini && !health.has_claude && "No LLM"}
                  {" · "}
                  {health.status}
                </span>
              </div>
            )}
            {health?.has_hf_token && (
              <div className="flex items-center gap-1.5 rounded-full border border-accent-lime/30 bg-accent-lime/10 px-2.5 py-1 text-[10px] uppercase tracking-wider text-accent-lime">
                <Sparkles className="h-3 w-3" />
                HF
              </div>
            )}
          </div>
        </div>

        <div className="mb-6">
          <h1 className="text-3xl font-bold md:text-4xl">
            Live <span className="text-gradient">meeting</span>
          </h1>
          <p className="mt-1 text-sm text-ink-100/60">
            {meeting
              ? `Meeting ${meeting.meeting_id} · ${meeting.title}`
              : "Start a meeting to see the agentic pipeline in action."}
          </p>
        </div>

        {error && (
          <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
            {error}
          </div>
        )}

        {!meeting && (
          <div className="grid place-items-center py-20">
            <motion.button
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              onClick={startMeeting}
              className="group inline-flex items-center gap-3 rounded-full bg-gradient-to-r from-accent-violet to-accent-fuchsia px-8 py-4 text-lg font-semibold text-white shadow-glow transition hover:scale-105"
            >
              <Play className="h-5 w-5" />
              Start the meeting
            </motion.button>
            <p className="mt-4 max-w-md text-center text-sm text-ink-100/50">
              Three speakers, six AI agents, one accessible meeting.
            </p>
          </div>
        )}

        {meeting && (
          <div className="grid gap-6 lg:grid-cols-12">
            {/* Speakers + controls */}
            <div className="space-y-6 lg:col-span-3">
              <div>
                <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-ink-100/70">
                  Participants
                </h3>
                <div className="space-y-2">
                  {speakers.map((s) => (
                    <SpeakerCard key={s.id} speaker={s} isActive={activeSpeakerId === s.id} />
                  ))}
                </div>
              </div>

              <div className="space-y-3">
                <h3 className="text-sm font-semibold uppercase tracking-wider text-ink-100/70">
                  Live input
                </h3>
                <MediaRecorderMic onAudioReady={sendAudio} disabled={!!summary} busy={busy} />

                <div className="flex gap-2">
                  <input
                    value={manualText}
                    onChange={(e) => setManualText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && manualText.trim()) {
                        sendSegment(manualText);
                        setManualText("");
                      }
                    }}
                    placeholder="Or type a line..."
                    disabled={busy || !!summary}
                    className="flex-1 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm placeholder:text-ink-100/30 focus:border-accent-violet/50 focus:outline-none disabled:opacity-40"
                  />
                  <button
                    onClick={() => {
                      if (manualText.trim()) {
                        sendSegment(manualText);
                        setManualText("");
                      }
                    }}
                    disabled={busy || !manualText.trim() || !!summary}
                    className="rounded-xl border border-white/10 bg-white/5 px-3 transition hover:bg-white/10 disabled:opacity-40"
                  >
                    <Send className="h-4 w-4" />
                  </button>
                </div>

                <button
                  onClick={nextDemoSegment}
                  disabled={busy || demoIndex >= DEMO_PROMPTS.length || !!summary}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] py-2 text-xs font-medium text-ink-100/70 transition hover:bg-white/[0.06] disabled:opacity-40"
                >
                  {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                  Scripted demo line ({demoIndex}/{DEMO_PROMPTS.length})
                </button>

                <button
                  onClick={endMeeting}
                  disabled={busy || transcript.length === 0 || !!summary}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 py-2.5 text-sm font-semibold text-red-300 transition hover:bg-red-500/20 disabled:opacity-40"
                >
                  <Square className="h-4 w-4" />
                  End & summarize
                </button>
              </div>
            </div>

            {/* Captions + signs */}
            <div className="space-y-6 lg:col-span-6">
              <CaptionStream segments={transcript} />
              <SignClipPlayer segment={latestSegment} />
            </div>

            {/* Agent panel */}
            <div className="lg:col-span-3">
              <AgentActivityPanel events={events} />
            </div>
          </div>
        )}

        <AnimatePresence>
          {summary && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-6 backdrop-blur-sm"
              onClick={() => setSummary(null)}
            >
              <motion.div
                initial={{ scale: 0.95, y: 20 }}
                animate={{ scale: 1, y: 0 }}
                exit={{ scale: 0.95, y: 20 }}
                onClick={(e) => e.stopPropagation()}
                className="max-h-[85vh] w-full max-w-3xl overflow-y-auto rounded-3xl border border-white/10 bg-ink-950 p-8 shadow-glow"
              >
                <h2 className="mb-2 text-2xl font-bold">
                  Meeting summary · <span className="text-gradient">{summary.title}</span>
                </h2>
                <p className="mb-6 text-sm text-ink-100/60">
                  {Math.floor(summary.duration_seconds / 60)}m {summary.duration_seconds % 60}s ·{" "}
                  {summary.transcript.length} segments · {summary.speakers.length} speakers
                </p>

                <div className="mb-6 rounded-2xl bg-white/[0.04] p-5">
                  <h3 className="mb-2 text-xs uppercase tracking-wider text-ink-100/50">Summary</h3>
                  <p className="leading-relaxed">{summary.summary}</p>
                </div>

                {summary.key_topics.length > 0 && (
                  <div className="mb-6">
                    <h3 className="mb-2 text-xs uppercase tracking-wider text-ink-100/50">Key topics</h3>
                    <div className="flex flex-wrap gap-2">
                      {summary.key_topics.map((t) => (
                        <span
                          key={t}
                          className="rounded-full border border-accent-violet/30 bg-accent-violet/10 px-3 py-1 text-sm text-accent-violet"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <ActionItemsList items={summary.action_items} />

                <button
                  onClick={() => {
                    setSummary(null);
                    setMeeting(null);
                  }}
                  className="mt-6 w-full rounded-xl bg-gradient-to-r from-accent-violet to-accent-fuchsia py-3 font-semibold text-white"
                >
                  Done
                </button>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <LLMStatsFooter />
    </div>
  );
}
