// Window buttons (minimise / maximise / close) and a resize grip for the desktop application, whose window has no Windows
// title bar (see backend/legalrag/desktop.py). In a normal browser this renders nothing.
import React, { useState } from "react";
import { Copy, Minus, Square, X } from "lucide-react";

interface DesktopApi {
  minimize: () => Promise<void>;
  toggle_maximize: () => Promise<boolean>;
  resize: (width: number, height: number) => Promise<void>;
  close: () => Promise<void>;
}

/** Elements with this class move the window when dragged. */
export const DRAG_REGION = "pywebview-drag-region";

export const IS_DESKTOP_FRAMELESS =
  typeof window !== "undefined" && new URLSearchParams(window.location.search).get("shell") === "frameless";

const api = (): DesktopApi | undefined => (window as unknown as { pywebview?: { api?: DesktopApi } }).pywebview?.api;

export function WindowControls() {
  const [maximized, setMaximized] = useState(false);
  if (!IS_DESKTOP_FRAMELESS) return null;

  const button = "w-9 h-7 inline-flex items-center justify-center rounded-md transition-colors cursor-pointer hover:bg-black/10";
  const startResize = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const ratio = window.devicePixelRatio || 1;
    const x0 = e.screenX;
    const y0 = e.screenY;
    const w0 = window.innerWidth * ratio;
    const h0 = window.innerHeight * ratio;
    let busy = false;
    const move = (ev: MouseEvent) => {
      if (busy) return;
      busy = true;
      const done = () => (busy = false);
      (api()?.resize(w0 + (ev.screenX - x0) * ratio, h0 + (ev.screenY - y0) * ratio) ?? Promise.resolve()).then(done, done);
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  return (
    <>
      <div
        className="flex items-center gap-0.5 shrink-0 ms-1"
        style={{ color: "var(--text-muted)" }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <button type="button" title="Minimise" className={button} onClick={() => api()?.minimize()}>
          <Minus className="w-4 h-4" />
        </button>
        <button
          type="button"
          title={maximized ? "Restore" : "Maximise"}
          className={button}
          onClick={() => api()?.toggle_maximize().then(setMaximized)}
        >
          {maximized ? <Copy className="w-3.5 h-3.5" /> : <Square className="w-3.5 h-3.5" />}
        </button>
        <button
          type="button"
          title="Close"
          className="w-9 h-7 inline-flex items-center justify-center rounded-md transition-colors cursor-pointer hover:bg-red-600 hover:text-white"
          onClick={() => api()?.close()}
        >
          <X className="w-4 h-4" />
        </button>
      </div>
      {!maximized && (
        <div
          title="Resize"
          onMouseDown={startResize}
          className="fixed bottom-0 right-0 w-4 h-4 z-[1000]"
          style={{ cursor: "nwse-resize" }}
        />
      )}
    </>
  );
}
