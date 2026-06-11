import { useEffect, useState } from "react";
import { PushToTalk } from "../components/PushToTalk";
import { TranscriptPane } from "../components/TranscriptPane";
import { SCHEMA, supabase } from "../lib/supabase";
import { useVoiceSession } from "../lib/useVoiceSession";

interface FeedItem {
  id: string;
  kind: "variance" | "disposition";
  text: string;
  flagged?: boolean;
}

export function FloorView() {
  const { status, talking, items, startTalking, stopTalking } = useVoiceSession("ops");
  const [feed, setFeed] = useState<FeedItem[]>([]);

  // live "voice → database" proof: new writes appear instantly
  useEffect(() => {
    const channel = supabase
      .channel("floor-feed")
      .on("postgres_changes",
        { event: "INSERT", schema: SCHEMA, table: "variance_logs" },
        (payload) => {
          const r = payload.new as Record<string, unknown>;
          setFeed((f) => [{
            id: String(r.id),
            kind: "variance" as const,
            flagged: Boolean(r.flagged),
            text: `Variance logged: counted ${r.counted_qty} vs system ${r.system_qty} (Δ ${Number(r.counted_qty) - Number(r.system_qty)})`,
          }, ...f].slice(0, 12));
        })
      .on("postgres_changes",
        { event: "INSERT", schema: SCHEMA, table: "dispositions" },
        (payload) => {
          const r = payload.new as Record<string, unknown>;
          setFeed((f) => [{
            id: String(r.id),
            kind: "disposition" as const,
            text: `Disposition: ${r.qty} unit(s) ${r.reason} → ${r.to_zone}`,
          }, ...f].slice(0, 12));
        })
      .subscribe();
    return () => { void supabase.removeChannel(channel); };
  }, []);

  return (
    <div className="view two-col">
      <section className="panel">
        <h2>Floor Voice</h2>
        <PushToTalk talking={talking} status={status} onStart={startTalking} onStop={stopTalking} />
        <TranscriptPane items={items} />
      </section>
      <section className="panel">
        <h2>Action Feed</h2>
        <p className="muted">Every voice-committed write, live from the database.</p>
        <div className="feed">
          {feed.length === 0 && <div className="muted">No actions yet this session.</div>}
          {feed.map((f) => (
            <div key={f.id} className={`feed-card ${f.flagged ? "feed-flagged" : ""}`}>
              <span className={`tag tag-${f.kind}`}>{f.kind}</span>
              {f.text}
              {f.flagged && <span className="tag tag-flag">flagged</span>}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
