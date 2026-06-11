import { useEffect, useRef } from "react";
import { TranscriptItem } from "../lib/useVoiceSession";

export function TranscriptPane({ items }: { items: TranscriptItem[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [items]);

  return (
    <div className="transcript">
      {items.length === 0 && (
        <div className="transcript-empty">Hold the button and speak — the live transcript appears here.</div>
      )}
      {items.map((it) => (
        <div key={it.id} className={`bubble bubble-${it.speaker} ${!it.final ? "bubble-interim" : ""}`}>
          <span className="bubble-speaker">{it.speaker === "user" ? "You" : "Omnivision"}</span>
          {it.text}
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
