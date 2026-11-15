// Android app only: offers the newest published version and installs it (MainActivity downloads the APK and opens
// Android's installer; the app's data stays, as every release is signed with the same key).
import React, { useEffect, useState } from "react";
import { Download, Loader2, X } from "lucide-react";
import { tr } from "../i18n";

interface Native { checkUpdate?: () => void; installUpdate?: () => void }
type State = "hidden" | "available" | "downloading" | "permission" | "installing" | "error";

export function UpdateBanner() {
  const [state, setState] = useState<State>("hidden");
  const [error, setError] = useState("");
  useEffect(() => {
    const n = (window as unknown as { SanadNative?: Native }).SanadNative;
    if (!n?.checkUpdate) return;
    (window as unknown as { __sanadUpdate?: (o: { state: string; error?: string }) => void }).__sanadUpdate = (o) => {
      if (o.state === "available" || o.state === "downloading" || o.state === "permission" || o.state === "installing") setState(o.state);
      else if (o.state === "error") { setState("error"); setError(o.error || ""); }
    };
    n.checkUpdate();
  }, []);
  if (state === "hidden") return null;
  const install = () => (window as unknown as { SanadNative?: Native }).SanadNative?.installUpdate?.();
  const text: Record<Exclude<State, "hidden">, string> = {
    available: tr("A new version of Sanad is available."),
    downloading: tr("Downloading the update… Android will then ask you to install it."),
    permission: tr("Allow Sanad to install updates, come back, then tap Update again."),
    installing: tr("Confirm the installation in the window Android opened."),
    error: tr("The update could not be downloaded: {0}", [error]),
  };
  return (
    <div className="flex items-center gap-2 px-3.5 py-2 text-xs border-b anim-fade-in shrink-0" style={{ backgroundColor: "var(--bg-card)", borderColor: "var(--border-subtle)", color: "var(--text-heading)" }}>
      {state === "downloading" ? <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" /> : <Download className="w-3.5 h-3.5 shrink-0" />}
      <span className="flex-1 min-w-0">{text[state]}</span>
      {(state === "available" || state === "permission" || state === "error") && (
        <button type="button" onClick={install} className="px-3 py-1 rounded-full text-xs font-semibold shrink-0 cursor-pointer" style={{ backgroundColor: "var(--accent-primary)", color: "var(--accent-primary-fg)" }}>
          {tr("Update")}
        </button>
      )}
      <button type="button" onClick={() => setState("hidden")} aria-label={tr("Later")} className="p-1 opacity-60 shrink-0 cursor-pointer">
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
