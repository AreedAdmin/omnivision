import { useEffect } from "react";

interface Props {
  talking: boolean;
  status: string;
  onStart: () => void;
  onStop: () => void;
}

/** Hold the button (or spacebar) to talk. */
export function PushToTalk({ talking, status, onStart, onStop }: Props) {
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.code === "Space" && !e.repeat && (e.target as HTMLElement)?.tagName !== "INPUT") {
        e.preventDefault();
        onStart();
      }
    };
    const up = (e: KeyboardEvent) => {
      if (e.code === "Space") {
        e.preventDefault();
        onStop();
      }
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [onStart, onStop]);

  const label =
    status !== "ready" ? status.toUpperCase()
    : talking ? "LISTENING…"
    : "HOLD TO TALK";

  return (
    <button
      className={`ptt ${talking ? "ptt-active" : ""} ${status !== "ready" ? "ptt-disabled" : ""}`}
      onPointerDown={onStart}
      onPointerUp={onStop}
      onPointerLeave={() => talking && onStop()}
      disabled={status !== "ready"}
    >
      <span className="ptt-dot" />
      {label}
      <span className="ptt-hint">(or hold space)</span>
    </button>
  );
}
