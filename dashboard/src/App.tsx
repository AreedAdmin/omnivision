import { useState } from "react";
import { FloorView } from "./views/FloorView";
import { InboundView } from "./views/InboundView";
import { ManagerView } from "./views/ManagerView";

type Persona = "floor" | "manager" | "inbound";

const TABS: { key: Persona; label: string; hint: string }[] = [
  { key: "floor", label: "Floor", hint: "ops worker" },
  { key: "manager", label: "Manager", hint: "talk to data" },
  { key: "inbound", label: "Inbound", hint: "supplier calls" },
];

export default function App() {
  const [tab, setTab] = useState<Persona>("inbound");

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          OMNI<span className="brand-accent">VISION</span>
          <span className="brand-sub">warehouse voice backbone</span>
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.key}
                    className={`tab ${tab === t.key ? "tab-active" : ""}`}
                    onClick={() => setTab(t.key)}>
              {t.label}
              <span className="tab-hint">{t.hint}</span>
            </button>
          ))}
        </nav>
      </header>
      <main>
        {/* keyed so switching personas tears down the previous voice session */}
        {tab === "floor" && <FloorView key="floor" />}
        {tab === "manager" && <ManagerView key="manager" />}
        {tab === "inbound" && <InboundView key="inbound" />}
      </main>
    </div>
  );
}
