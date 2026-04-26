import type {
  CreateMeetingResponse,
  LLMStats,
  MeetingSummary,
  SignClip,
  StreamEvent,
  TranscribeResponse,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () =>
    request<{
      status: string;
      llm_provider_active: string | null;
      has_gemini: boolean;
      has_claude: boolean;
      has_hf_token: boolean;
      mock_mode: boolean;
    }>("/health"),

  stats: () => request<LLMStats>("/stats"),

  createMeeting: (
    title: string,
    expectedSpeakers: string[],
    mode = "general",
    target_language = "en",
  ) =>
    request<CreateMeetingResponse>("/meetings", {
      method: "POST",
      body: JSON.stringify({ title, expected_speakers: expectedSpeakers, mode, target_language }),
    }),

  transcribe: (meetingId: string, text: string, target_language = "en") =>
    request<TranscribeResponse>("/transcribe", {
      method: "POST",
      body: JSON.stringify({ meeting_id: meetingId, text, target_language }),
    }),

  /**
   * Streaming version: invokes onEvent for each StreamEvent as it arrives.
   * Resolves when the stream ends or rejects on error.
   */
  transcribeStream: async (
    meetingId: string,
    text: string,
    target_language: string,
    onEvent: (event: StreamEvent) => void,
  ): Promise<void> => {
    const res = await fetch(`${BASE}/transcribe-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ meeting_id: meetingId, text, target_language }),
    });
    if (!res.ok) {
      throw new Error(`Stream ${res.status}: ${await res.text()}`);
    }
    if (!res.body) throw new Error("No response body");

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const drain = (block: string) => {
      if (!block.trim()) return;
      const lines = block.split("\n");
      let dataLine: string | undefined;
      for (const line of lines) {
        if (line.startsWith("data:")) {
          dataLine = line.slice(5).trim();
        }
      }
      if (!dataLine) return;
      try {
        const event = JSON.parse(dataLine) as StreamEvent;
        onEvent(event);
      } catch {
        /* malformed chunk — skip */
      }
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) drain(block);
    }
    // Flush any final block left in the buffer when the stream closed
    buffer += decoder.decode();
    if (buffer.trim()) drain(buffer);
  },

  /**
   * Upload a WAV file: backend transcribes via Whisper, identifies speaker
   * via pyannote, and runs the full agent pipeline.
   */
  transcribeAudio: async (
    meetingId: string,
    audioBlob: Blob,
    target_language = "en",
    text_hint?: string,
  ): Promise<TranscribeResponse & { audio_bytes_size: number }> => {
    const fd = new FormData();
    fd.append("audio", audioBlob, "speech.wav");
    const params = new URLSearchParams({ meeting_id: meetingId, target_language });
    if (text_hint) params.set("text_hint", text_hint);
    const res = await fetch(`${BASE}/transcribe-audio?${params}`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return await res.json();
  },

  endMeeting: (meetingId: string) =>
    request<MeetingSummary>(`/meetings/${meetingId}/end`, { method: "POST" }),

  lookupSigns: (text: string) =>
    request<SignClip[]>(`/signs/lookup?text=${encodeURIComponent(text)}`),

  vocabulary: () => request<string[]>("/signs/vocabulary"),
};
