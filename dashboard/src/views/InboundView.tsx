// Inbound PO board — the demo centerpiece (plan/09).
// LOCAL MODE: Chase → the "supplier" (teammate) answers the call in the
// browser → live two-column transcript via Realtime → PO chip flips when
// post-call extraction lands.

import { useCallback, useEffect, useState } from "react";
import { SCHEMA, SERVER_URL, supabase } from "../lib/supabase";
import { useSupplierCall } from "../lib/useSupplierCall";

interface PORow {
  id: string;
  po_number: string;
  qty: number;
  expected_date: string;
  status: string;
  eta_date: string | null;
  delay_reason: string | null;
  suppliers: { name: string } | null;
  products: { name: string } | null;
}

interface TranscriptTurn {
  id: string;
  turn_no: number;
  speaker: string;
  text: string;
}

const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  overdue: "Overdue",
  chasing: "📞 Calling…",
  confirmed_on_time: "On time",
  delayed: "Delayed",
  shipped: "Shipped",
  received: "Received",
  needs_review: "Needs review",
};

function daysOverdue(expected: string): number {
  const diff = Date.now() - new Date(expected + "T00:00:00").getTime();
  return Math.max(0, Math.floor(diff / 86_400_000));
}

export function InboundView() {
  const [pos, setPos] = useState<PORow[]>([]);
  const [activeCallId, setActiveCallId] = useState<string | null>(null);
  const [pendingCtxId, setPendingCtxId] = useState<string | null>(null);
  const [callMeta, setCallMeta] = useState<{ po: string; supplier: string } | null>(null);
  const [turns, setTurns] = useState<TranscriptTurn[]>([]);
  const [chasing, setChasing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const call = useSupplierCall();

  const load = useCallback(async () => {
    const { data, error: err } = await supabase
      .from("purchase_orders")
      .select("id, po_number, qty, expected_date, status, eta_date, delay_reason, suppliers(name), products(name)")
      .order("expected_date");
    if (err) setError(err.message);
    else setPos((data as unknown as PORow[]) ?? []);
  }, []);

  useEffect(() => { void load(); }, [load]);

  // PO status flips live
  useEffect(() => {
    const channel = supabase
      .channel("po-board")
      .on("postgres_changes",
        { event: "*", schema: SCHEMA, table: "purchase_orders" },
        () => void load())
      .subscribe();
    return () => { void supabase.removeChannel(channel); };
  }, [load]);

  // live call transcript
  useEffect(() => {
    if (!activeCallId) return;
    setTurns([]);
    const channel = supabase
      .channel(`call-${activeCallId}`)
      .on("postgres_changes",
        { event: "INSERT", schema: SCHEMA, table: "call_transcripts",
          filter: `call_id=eq.${activeCallId}` },
        (payload) => {
          const r = payload.new as unknown as TranscriptTurn;
          setTurns((t) => [...t, r].sort((a, b) => a.turn_no - b.turn_no));
        })
      .subscribe();
    return () => { void supabase.removeChannel(channel); };
  }, [activeCallId]);

  const chase = async (po: PORow) => {
    setChasing(po.id);
    setError(null);
    call.reset();
    try {
      const res = await fetch(`${SERVER_URL}/calls/initiate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ po_id: po.id }),
      });
      if (!res.ok) throw new Error((await res.json()).detail ?? "call failed to start");
      const data = await res.json();
      setActiveCallId(data.call_id);
      setPendingCtxId(data.ctx_id ?? null);
      setCallMeta({ po: data.po_number, supplier: data.supplier ?? po.suppliers?.name ?? "supplier" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to start call");
    } finally {
      setChasing(null);
    }
  };

  return (
    <div className="view two-col">
      <section className="panel panel-wide">
        <h2>Purchase Orders</h2>
        {error && <div className="error">{error}</div>}
        <table className="po-table">
          <thead>
            <tr>
              <th>PO</th><th>Supplier</th><th>Product</th><th>Qty</th>
              <th>Expected</th><th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            {pos.map((po) => {
              const overdue = daysOverdue(po.expected_date);
              const chaseable = ["overdue", "open", "needs_review"].includes(po.status) && overdue > 0;
              return (
                <tr key={po.id}>
                  <td className="mono">{po.po_number}</td>
                  <td>{po.suppliers?.name}</td>
                  <td>{po.products?.name}</td>
                  <td>{po.qty}</td>
                  <td>
                    {po.expected_date}
                    {overdue > 0 && !["received", "shipped", "delayed", "confirmed_on_time"].includes(po.status) && (
                      <span className="tag tag-overdue">{overdue}d overdue</span>
                    )}
                  </td>
                  <td>
                    <span className={`chip chip-${po.status}`}>
                      {STATUS_LABEL[po.status] ?? po.status}
                      {po.status === "delayed" && po.eta_date && ` — ETA ${po.eta_date}`}
                    </span>
                    {po.delay_reason && <div className="muted small">{po.delay_reason}</div>}
                  </td>
                  <td>
                    {chaseable && (
                      <button className="btn-chase" disabled={chasing === po.id}
                              onClick={() => void chase(po)}>
                        {chasing === po.id ? "Dialing…" : "Chase"}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <h2>Live Call</h2>
        {!activeCallId && (
          <p className="muted">
            Hit “Chase” on an overdue PO — the agent calls the supplier and the
            conversation streams here live. (Local mode: the supplier answers in
            this browser; their mic is the supplier side of the call.)
          </p>
        )}

        {activeCallId && call.state === "idle" && pendingCtxId && (
          <div className="call-ring">
            <div className="call-ring-pulse">📞</div>
            <p>Calling <strong>{callMeta?.supplier}</strong> about <strong>{callMeta?.po}</strong>…</p>
            <button className="btn-chase" onClick={() => void call.answer(pendingCtxId)}>
              Answer as supplier
            </button>
            <p className="muted small">The teammate playing the supplier clicks this and speaks into the mic.</p>
          </div>
        )}

        {call.state === "ringing" && <p className="muted">Connecting audio…</p>}

        {call.state === "live" && (
          <div className="call-live-bar">
            <span className="tag tag-live">● live</span>
            <button className="btn-hangup" onClick={call.hangup}>Hang up</button>
          </div>
        )}
        {call.state === "ended" && (
          <p className="muted">Call ended — extracting outcome and updating the order…</p>
        )}
        {call.state === "error" && <div className="error">Call audio failed — check mic permission and server.</div>}

        {activeCallId && (
          <div className="call-transcript">
            {turns.length === 0 && call.state === "live" && <p className="muted">Listening…</p>}
            {turns.map((t) => (
              <div key={t.id} className={`bubble bubble-${t.speaker === "agent" ? "agent" : "user"}`}>
                <span className="bubble-speaker">{t.speaker === "agent" ? "Omnivision" : "Supplier"}</span>
                {t.text}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
