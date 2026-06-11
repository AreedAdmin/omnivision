// One hook = one live voice session against /ws/voice?persona=...
// Manages: WS lifecycle, mic capture gating (push-to-talk), TTS playback,
// and the live transcript (user partials + agent sentences).

import { useCallback, useEffect, useRef, useState } from "react";
import { WS_URL } from "./supabase";
import { MicSession, PCMPlayer, startMic } from "./audio";

export interface TranscriptItem {
  id: number;
  speaker: "user" | "agent";
  text: string;
  final: boolean;
}

type Status = "connecting" | "ready" | "error" | "closed";

let nextId = 1;

export function useVoiceSession(persona: "ops" | "manager") {
  const [status, setStatus] = useState<Status>("connecting");
  const [talking, setTalking] = useState(false);
  const [items, setItems] = useState<TranscriptItem[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const micRef = useRef<MicSession | null>(null);
  const playerRef = useRef<PCMPlayer | null>(null);

  useEffect(() => {
    let closed = false;
    setItems([]);
    setStatus("connecting");

    const ws = new WebSocket(`${WS_URL}/ws/voice?persona=${persona}`);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => !closed && setStatus("ready");
    ws.onerror = () => !closed && setStatus("error");
    ws.onclose = () => !closed && setStatus("closed");

    ws.onmessage = (e) => {
      if (typeof e.data === "string") {
        try {
          const msg = JSON.parse(e.data);
          if (msg.type === "transcript") {
            setItems((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (msg.speaker === "user") {
                // replace a running interim user line; append on new/final
                if (last && last.speaker === "user" && !last.final) {
                  next[next.length - 1] = { ...last, text: msg.text, final: msg.final };
                } else {
                  next.push({ id: nextId++, speaker: "user", text: msg.text, final: msg.final });
                }
              } else {
                // agent sentences: merge consecutive agent lines into one bubble
                if (last && last.speaker === "agent") {
                  next[next.length - 1] = { ...last, text: `${last.text} ${msg.text}` };
                } else {
                  next.push({ id: nextId++, speaker: "agent", text: msg.text, final: true });
                }
              }
              return next.slice(-40);
            });
          }
        } catch { /* ignore malformed */ }
      } else {
        playerRef.current?.play(e.data as ArrayBuffer);
      }
    };

    return () => {
      closed = true;
      ws.close();
      micRef.current?.close();
      micRef.current = null;
      playerRef.current = null;
    };
  }, [persona]);

  const ensureMic = useCallback(async () => {
    if (micRef.current) return;
    const mic = await startMic((chunk) => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(chunk.buffer);
    });
    micRef.current = mic;
    playerRef.current = new PCMPlayer(mic.ctx);
  }, []);

  const startTalking = useCallback(async () => {
    await ensureMic();
    await micRef.current?.ctx.resume();
    playerRef.current?.flush(); // local barge-in: stop agent audio instantly
    micRef.current?.setSending(true);
    setTalking(true);
  }, [ensureMic]);

  const stopTalking = useCallback(() => {
    micRef.current?.setSending(false);
    setTalking(false);
  }, []);

  return { status, talking, items, startTalking, stopTalking };
}
