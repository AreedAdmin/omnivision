// Local-mode supplier call (plan change: no Twilio).
// The teammate playing the supplier "answers" in the browser: their mic is the
// supplier side, the agent's TTS plays through the speakers.
//
// Half-duplex: mic frames are NOT sent while agent audio is playing, so the
// agent never transcribes its own voice off the speakers. (Trade-off: no
// barge-in on the local call — fine for a scripted demo.)

import { useCallback, useEffect, useRef, useState } from "react";
import { MicSession, PCMPlayer, startMic } from "./audio";
import { WS_URL } from "./supabase";

export type CallState = "idle" | "ringing" | "live" | "ended" | "error";

export function useSupplierCall() {
  const [state, setState] = useState<CallState>("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const micRef = useRef<MicSession | null>(null);
  const playerRef = useRef<PCMPlayer | null>(null);

  const cleanup = useCallback(() => {
    micRef.current?.close();
    micRef.current = null;
    playerRef.current = null;
    wsRef.current = null;
  }, []);

  /** "Answer" the call: connect audio and let the agent greet. */
  const answer = useCallback(async (ctxId: string) => {
    setState("ringing");
    try {
      const mic = await startMic((chunk) => {
        const ws = wsRef.current;
        // half-duplex gate: stay quiet while the agent is speaking
        if (ws && ws.readyState === WebSocket.OPEN && !playerRef.current?.isPlaying()) {
          ws.send(chunk.buffer);
        }
      });
      micRef.current = mic;
      playerRef.current = new PCMPlayer(mic.ctx);
      await mic.ctx.resume();

      const ws = new WebSocket(`${WS_URL}/ws/call?ctx_id=${ctxId}`);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () => {
        mic.setSending(true);
        setState("live");
      };
      ws.onmessage = (e) => {
        if (typeof e.data !== "string") playerRef.current?.play(e.data as ArrayBuffer);
      };
      ws.onclose = () => {
        setState("ended");
        cleanup();
      };
      ws.onerror = () => {
        setState("error");
        cleanup();
      };
    } catch {
      setState("error");
      cleanup();
    }
  }, [cleanup]);

  /** Manual hang-up (the agent normally ends the call itself after goodbye). */
  const hangup = useCallback(() => {
    wsRef.current?.close();
  }, []);

  const reset = useCallback(() => setState("idle"), []);

  useEffect(() => () => { wsRef.current?.close(); cleanup(); }, [cleanup]);

  return { state, answer, hangup, reset };
}
