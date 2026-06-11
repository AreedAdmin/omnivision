import { PushToTalk } from "../components/PushToTalk";
import { TranscriptPane } from "../components/TranscriptPane";
import { useVoiceSession } from "../lib/useVoiceSession";

export function ManagerView() {
  const { status, talking, items, startTalking, stopTalking } = useVoiceSession("manager");

  return (
    <div className="view">
      <section className="panel panel-wide">
        <h2>Talk to Your Warehouse</h2>
        <p className="muted">
          Ask about stock levels, sale rates, low stock, open purchase orders, top movers —
          and follow up naturally ("so when do I run out?").
        </p>
        <PushToTalk talking={talking} status={status} onStart={startTalking} onStop={stopTalking} />
        <TranscriptPane items={items} />
      </section>
    </div>
  );
}
