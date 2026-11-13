import React, { useEffect, useRef, useState } from "react";
import { Loader2, FileText } from "lucide-react";
import { tr } from "../i18n";
import { fetchPageImageUrl } from "../api/legalrag";

interface Props {
  provisionId: string;
  asOf?: string;
  pageStart: number;
  pageEnd: number;
}

/** The real page(s) of the official Bulletin Officiel PDF that hold the article. Hidden when the PDF is not on this machine. */
export function PdfPageImage({ provisionId, asOf, pageStart, pageEnd }: Props) {
  const [open, setOpen] = useState(false);
  const [urls, setUrls] = useState<(string | null)[]>([]);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "missing">("idle");
  const [error, setError] = useState("");
  const last = Math.min(pageEnd, pageStart + 2); // an article rarely spans more; never pull a whole bulletin
  // The request must not be cancelled by its own state change (that left the spinner turning forever): it is started once, runs to the
  // end, and its result is only dropped if the card is gone.
  const mounted = useRef(true);
  const started = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!open || started.current) return;
    started.current = true;
    setState("loading");
    (async () => {
      const out: (string | null)[] = [];
      let err = "";
      for (let p = pageStart; p <= last; p++) {
        try {
          out.push(await fetchPageImageUrl(provisionId, p, asOf));
        } catch (e) {
          out.push(null);
          err = (e as Error).message || String(e);
        }
      }
      if (!mounted.current) {
        out.forEach((u) => u && URL.revokeObjectURL(u));
        return;
      }
      setUrls(out);
      setError(err);
      setState(out.some(Boolean) ? "ready" : "missing");
    })();
  }, [open, provisionId, asOf, pageStart, last]);

  useEffect(() => () => urls.forEach((u) => u && URL.revokeObjectURL(u)), [urls]);

  const retry = () => {
    started.current = false;
    setState("idle");
    setError("");
    setOpen(false);
    setTimeout(() => setOpen(true), 0);
  };

  if (state === "missing") {
    return (
      <p className="text-xs" style={{ color: "var(--text-muted)" }}>
        {/404/.test(error) || !error
          ? tr("Le PDF de ce bulletin n'est pas disponible sur cet ordinateur.")
          : tr("La page n'a pas pu être affichée ({0}).", [error])}{" "}
        <button type="button" onClick={retry} className="underline cursor-pointer">
          {tr("Réessayer")}
        </button>
      </p>
    );
  }
  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-xs font-medium cursor-pointer hover:opacity-85"
        style={{ backgroundColor: "var(--bg-canvas)", borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}
      >
        <FileText className="w-3 h-3" />
        {open ? tr("Masquer la page du PDF") : tr("Voir la page du PDF officiel (p. {0})", [pageStart === pageEnd ? pageStart : `${pageStart}–${pageEnd}`])}
      </button>
      {open && state === "loading" && <Loader2 className="w-4 h-4 animate-spin" style={{ color: "var(--accent-primary)" }} />}
      {open && state === "ready" && (
        <div className="space-y-3">
          {urls.map((u, i) =>
            u ? (
              <img key={i} src={u} alt={tr("Page {0} du Bulletin Officiel", [pageStart + i])} className="w-full rounded-lg border" style={{ borderColor: "var(--border-subtle)" }} />
            ) : null
          )}
          {pageEnd > last && (
            <p className="text-xs" style={{ color: "var(--text-muted)" }}>
              {tr("L'article continue jusqu'à la page {0}.", [pageEnd])}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
