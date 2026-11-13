import React, { useEffect, useMemo, useRef, useState } from "react";
import { PdfPageImage } from "./PdfPageImage";
import { tr } from "../i18n";
import {
  Bookmark,
  Check,
  ChevronDown,
  Code2,
  Copy,
  Download,
  Eye,
  FileCheck2,
  FileCode,
  FileText,
  FileType,
  Layers,
  Maximize2,
  Minimize2,
  Quote,
  RotateCw,
  Sparkles,
  X,
} from "lucide-react";
import {
  ArtifactItem,
  ArtifactKind,
  DocumentMeta,
  PdfSnippet,
} from "../types/agent";
import { MOROCCAN_LAW_STATUSES } from "../data/moroccanLawData";
import {
  ShieldCheck,
  AlertTriangle,
  Scale,
  Languages,
  CheckCircle2,
  Calendar,
  Building,
} from "lucide-react";
import { MarkdownRenderer } from "./MarkdownRenderer";
import {
  createSnippetDocxBlob,
  createGenericDocxBlob,
} from "../utils/docxExport";

interface ArtifactWorkbenchProps {
  artifact: ArtifactItem;
  allArtifacts: ArtifactItem[];
  onSelectArtifact: (artifact: ArtifactItem) => void;
  onClose: () => void;
  isExpanded: boolean;
  onToggleExpand: () => void;
}

export const ArtifactWorkbench: React.FC<ArtifactWorkbenchProps> = ({
  artifact,
  allArtifacts,
  onSelectArtifact,
  onClose,
  isExpanded,
  onToggleExpand,
}) => {
  const canPreview =
    artifact.kind === ArtifactKind.Html ||
    artifact.kind === ArtifactKind.Svg ||
    artifact.kind === ArtifactKind.Markdown ||
    artifact.kind === ArtifactKind.Document;

  const [mode, setMode] = useState<"preview" | "code">(
    canPreview ? "preview" : "code"
  );

  useEffect(() => {
    if (artifact.kind === ArtifactKind.Document || canPreview) {
      setMode("preview");
    } else {
      setMode("code");
    }
  }, [artifact.id, artifact.kind, canPreview]);
  const [copied, setCopied] = useState(false);
  const [copiedQuoteId, setCopiedQuoteId] = useState<string | null>(null);
  const [copiedAllPassages, setCopiedAllPassages] = useState(false);
  const [selectedSnippetFilter, setSelectedSnippetFilter] = useState<
    "all" | string
  >("all");
  const [downloadMenuOpen, setDownloadMenuOpen] = useState(false);
  const [downloadedFormat, setDownloadedFormat] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [bilingualView, setBilingualView] = useState<"dual" | "fr" | "ar">("dual");

  const downloadDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        downloadDropdownRef.current &&
        !downloadDropdownRef.current.contains(e.target as Node)
      ) {
        setDownloadMenuOpen(false);
      }
    }
    if (downloadMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () =>
        document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [downloadMenuOpen]);

  const docMeta = artifact.documentMeta;

  const matchedLawStatus = useMemo(() => {
    const textToScan = `${artifact.title} ${docMeta?.filename || ""} ${artifact.content}`.toLowerCase();
    if (textToScan.includes("58.25") || textToScan.includes("procédure civile") || textToScan.includes("مسطرة مدنية"))
      return MOROCCAN_LAW_STATUSES["law-58-25"];
    if (textToScan.includes("03.23") || textToScan.includes("procédure pénale") || textToScan.includes("مسطرة جنائية"))
      return MOROCCAN_LAW_STATUSES["law-03-23"];
    if (textToScan.includes("1974") || textToScan.includes("1.74.447"))
      return MOROCCAN_LAW_STATUSES["cpc-1974"];
    if (textToScan.includes("65-99") || textToScan.includes("travail") || textToScan.includes("شغل"))
      return MOROCCAN_LAW_STATUSES["law-65-99"];
    if (textToScan.includes("doc") || textToScan.includes("1913") || textToScan.includes("obligations"))
      return MOROCCAN_LAW_STATUSES["doc-1913"];
    if (textToScan.includes("66.23") || textToScan.includes("avocat") || textToScan.includes("محاماة"))
      return MOROCCAN_LAW_STATUSES["law-66-23"];
    if (textToScan.includes("50-25") || textToScan.includes("liquidités") || textToScan.includes("espèces"))
      return MOROCCAN_LAW_STATUSES["finance-50-25"];
    return null;
  }, [artifact, docMeta]);

  const activeMode =
    artifact.kind === ArtifactKind.Document
      ? "preview"
      : canPreview
      ? mode
      : "code";

  const srcDoc = useMemo(() => {
    if (artifact.kind === ArtifactKind.Html) {
      return artifact.content;
    }
    if (artifact.kind === ArtifactKind.Svg) {
      return `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8" />
<style>
  html, body {
    margin: 0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #F9F5EE;
    padding: 24px;
    box-sizing: border-box;
  }
  svg { max-width: 100%; height: auto; }
</style>
</head>
<body>${artifact.content}</body>
</html>`;
    }
    return "";
  }, [artifact]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(artifact.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard fallback ignored safely
    }
  };

  const snippets: PdfSnippet[] = useMemo(() => {
    if (docMeta?.snippets && docMeta.snippets.length > 0) {
      return docMeta.snippets;
    }
    if (docMeta?.highlightedSnippet || artifact.content) {
      return [
        {
          id: "snip-primary",
          page: docMeta?.page || "1",
          totalPages: docMeta?.totalPages,
          sectionTitle: docMeta?.sectionTitle,
          highlightedSnippet: docMeta?.highlightedSnippet || artifact.content,
          contextBefore: docMeta?.contextBefore,
          contextAfter: docMeta?.contextAfter,
          relevanceExplanation:
            docMeta?.relevanceExplanation || artifact.summary,
        },
      ];
    }
    return [];
  }, [docMeta, artifact.content, artifact.summary]);

  const uniquePages = useMemo(() => {
    const pages = snippets.map((s) => String(s.page || "1"));
    return [...new Set(pages)];
  }, [snippets]);

  const pageSummaryText = useMemo(() => {
    if (uniquePages.length === 0) return "";
    if (uniquePages.length === 1) {
      return `Page ${uniquePages[0]}${
        docMeta?.totalPages ? ` of ${docMeta.totalPages}` : ""
      }`;
    }
    const pageList = uniquePages.join(", ");
    return docMeta?.totalPages
      ? `Pages ${pageList} (of ${docMeta.totalPages} total)`
      : `Pages ${pageList}`;
  }, [uniquePages, docMeta?.totalPages]);

  const handleCopySnippetOnly = async (snippetId: string, quote: string) => {
    try {
      await navigator.clipboard.writeText(quote);
      setCopiedQuoteId(snippetId);
      setTimeout(() => setCopiedQuoteId(null), 1800);
    } catch {
      // Clipboard fallback ignored safely
    }
  };

  const handleCopyAllPassages = async () => {
    try {
      const formatted = snippets
        .map(
          (s, idx) =>
            `[Excerpt ${idx + 1} · Page ${s.page}${
              s.sectionTitle ? ` · ${s.sectionTitle}` : ""
            }]\n"${s.highlightedSnippet}"${
              s.relevanceExplanation
                ? `\nSignificance: ${s.relevanceExplanation}`
                : ""
            }`
        )
        .join("\n\n---\n\n");
      await navigator.clipboard.writeText(formatted);
      setCopiedAllPassages(true);
      setTimeout(() => setCopiedAllPassages(false), 1800);
    } catch {
      // Clipboard fallback ignored safely
    }
  };

  const escapeHtml = (str: string): string => {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  };

  const generateStyledSnippetHtml = (
    title: string,
    meta: DocumentMeta | undefined,
    snips: PdfSnippet[],
    pages: string[]
  ): string => {
    const snipsHtml = snips
      .map(
        (s, idx) => `
    <div class="snippet-card">
      <div class="snippet-meta">
        <span class="badge">Passage ${idx + 1} of ${snips.length}</span>
        <span class="page-tag">Page ${s.page}${
          s.totalPages
            ? ` of ${s.totalPages}`
            : meta?.totalPages
            ? ` of ${meta.totalPages}`
            : ""
        }</span>
      </div>
      ${
        s.sectionTitle
          ? `<div class="section-title" dir="auto">${escapeHtml(s.sectionTitle)}</div>`
          : ""
      }
      ${
        s.contextBefore
          ? `<p class="context context-before" dir="auto">${escapeHtml(
              s.contextBefore
            )}</p>`
          : ""
      }
      <div class="quote-callout">
        <div class="quote-tag">VERIFIED TEXT EXCERPT · PAGE ${escapeHtml(
          String(s.page)
        )}</div>
        <blockquote dir="auto">&ldquo;${escapeHtml(s.highlightedSnippet)}&rdquo;</blockquote>
      </div>
      ${
        s.contextAfter
          ? `<p class="context context-after" dir="auto">${escapeHtml(s.contextAfter)}</p>`
          : ""
      }
      ${
        s.relevanceExplanation
          ? `
      <div class="rationale-box">
        <strong>Agent Evidence Verification:</strong>
        <p>${escapeHtml(s.relevanceExplanation)}</p>
      </div>`
          : ""
      }
    </div>`
      )
      .join("\n");

    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${escapeHtml(meta?.filename || title)}</title>
<style>
  :root {
    --bg: #F9F5EE;
    --surface: #FFFFFF;
    --card: #F4EFE6;
    --text-heading: #4A2B24;
    --text-body: #38241F;
    --text-muted: #8C7566;
    --accent: #59201A;
    --accent-warm: #C59B7B;
    --border: #DFD4C6;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text-body);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    padding: 40px 20px;
    line-height: 1.6;
  }
  .container {
    max-width: 740px;
    margin: 0 auto;
  }
  .doc-header {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 28px;
    margin-bottom: 24px;
    box-shadow: 0 2px 8px rgba(74, 43, 36, 0.04);
  }
  .doc-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 12px;
  }
  .badge {
    background: #EFE8DD;
    color: var(--accent);
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 4px 10px;
    border-radius: 6px;
  }
  .page-tag {
    font-size: 12px;
    color: var(--text-muted);
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    align-self: center;
  }
  h1 {
    font-family: Georgia, Cambria, "Times New Roman", Times, serif;
    font-weight: 500;
    font-size: 24px;
    color: var(--text-heading);
    margin-bottom: 6px;
    line-height: 1.3;
  }
  .author {
    font-family: Georgia, serif;
    font-style: italic;
    font-size: 13px;
    color: var(--text-muted);
  }
  .snippet-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 28px;
    margin-bottom: 20px;
    box-shadow: 0 2px 8px rgba(74, 43, 36, 0.04);
  }
  .snippet-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
    padding-bottom: 12px;
    margin-bottom: 16px;
  }
  .section-title {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    font-weight: 700;
    color: var(--accent-warm);
    margin-bottom: 12px;
    font-family: ui-monospace, monospace;
  }
  .context {
    font-family: Georgia, serif;
    font-style: italic;
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.6;
    margin-bottom: 14px;
  }
  .context-after {
    margin-top: 14px;
    margin-bottom: 0;
  }
  .quote-callout {
    background: var(--card);
    border: 1.5px solid var(--accent-warm);
    border-radius: 12px;
    padding: 20px;
    margin: 16px 0;
  }
  .quote-tag {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--accent);
    margin-bottom: 8px;
    font-family: ui-monospace, monospace;
  }
  blockquote {
    font-family: Georgia, Cambria, serif;
    font-size: 15px;
    font-style: italic;
    color: var(--text-heading);
    line-height: 1.65;
  }
  .rationale-box {
    margin-top: 18px;
    background: #EFE8DD;
    border-radius: 10px;
    padding: 14px 18px;
    font-size: 12px;
  }
  .rationale-box strong {
    color: var(--text-heading);
    display: block;
    margin-bottom: 4px;
  }
  .rationale-box p {
    color: var(--text-body);
    margin: 0;
    line-height: 1.5;
  }
  @media print {
    body { background: #FFFFFF; padding: 0; }
    .snippet-card, .doc-header { box-shadow: none; border-color: #CCC; page-break-inside: avoid; }
  }
</style>
</head>
<body>
  <div class="container">
    <div class="doc-header">
      <div class="doc-badges">
        <span class="badge">PDF Document Evidence</span>
        <span class="badge">${snips.length} Verified ${
      snips.length === 1 ? tr("Snippet") : "Snippets"
    }</span>
        ${
          pages.length > 0
            ? `<span class="page-tag">Pages: ${escapeHtml(
                pages.join(", ")
              )}</span>`
            : ""
        }
      </div>
      <h1>${escapeHtml(meta?.filename || title)}</h1>
      ${
        meta?.authorOrSource
          ? `<div class="author">${escapeHtml(meta.authorOrSource)}</div>`
          : ""
      }
    </div>
    ${snipsHtml}
  </div>
</body>
</html>`;
  };

  const generateSnippetPlainText = (
    title: string,
    meta: DocumentMeta | undefined,
    snips: PdfSnippet[],
    pages: string[]
  ): string => {
    const divider = "=".repeat(78);
    const subDivider = "-".repeat(78);

    const header = [
      divider,
      `EVIDENCE BRIEF: ${meta?.filename || title}`,
      meta?.authorOrSource ? `Source: ${meta.authorOrSource}` : null,
      `Total Passages: ${snips.length} Verified Snippets (Pages: ${pages.join(
        ", "
      )})`,
      divider,
      "",
    ]
      .filter(Boolean)
      .join("\n");

    const body = snips
      .map((s, idx) => {
        const parts = [
          `[PASSAGE ${idx + 1} OF ${snips.length}]`,
          `Page: ${s.page}${
            s.totalPages
              ? ` of ${s.totalPages}`
              : meta?.totalPages
              ? ` of ${meta.totalPages}`
              : ""
          }`,
          s.sectionTitle ? `Section: ${s.sectionTitle}` : null,
          "",
          s.contextBefore ? `Context Before:\n${s.contextBefore}\n` : null,
          `VERBATIM QUOTE:\n"${s.highlightedSnippet}"`,
          s.contextAfter ? `\nContext After:\n${s.contextAfter}` : null,
          s.relevanceExplanation
            ? `\nAgent Evidence Verification:\n${s.relevanceExplanation}`
            : null,
          "",
          subDivider,
          "",
        ];
        return parts.filter((p) => p !== null).join("\n");
      })
      .join("\n");

    return `${header}\n${body}`;
  };

  const handlePrintPdf = () => {
    // Real PDF through the browser's own engine (handles Arabic): opens the print dialog, choose "Save as PDF".
    const isDoc = artifact.kind === ArtifactKind.Document;
    const html = isDoc
      ? generateStyledSnippetHtml(artifact.title, docMeta, snippets, uniquePages)
      : `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escapeHtml(artifact.title)}</title><style>body{font-family:sans-serif;padding:24px;white-space:pre-wrap}</style></head><body dir="auto">${escapeHtml(artifact.content)}</body></html>`;
    const frame = document.createElement("iframe");
    frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
    document.body.appendChild(frame);
    const doc = frame.contentDocument;
    if (!doc || !frame.contentWindow) {
      document.body.removeChild(frame);
      return;
    }
    doc.open();
    doc.write(html);
    doc.close();
    const go = () => {
      try {
        frame.contentWindow?.focus();
        frame.contentWindow?.print();
      } finally {
        setTimeout(() => frame.parentNode && document.body.removeChild(frame), 60000);
      }
    };
    setTimeout(go, 400);
    setDownloadMenuOpen(false);
  };

  const handleDownloadAs = async (format: "html" | "docx" | "txt") => {
    const isDoc = artifact.kind === ArtifactKind.Document;
    const safeName = (docMeta?.filename || artifact.title)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");

    let blob: Blob;
    let fileExt: string;

    if (format === "docx") {
      fileExt = "docx";
      const serifStyle =
        typeof window !== "undefined"
          ? getComputedStyle(document.documentElement).getPropertyValue(
              "--font-serif"
            ) || ""
          : "";
      const isEmerald = serifStyle.toLowerCase().includes("cormorant");
      const fontOptions = {
        serifFont: isEmerald ? "Cormorant Garamond" : "Lora",
        sansFont: "Plus Jakarta Sans",
        monoFont: "JetBrains Mono",
      };

      if (isDoc) {
        blob = await createSnippetDocxBlob(
          artifact.title,
          docMeta,
          snippets,
          uniquePages,
          fontOptions
        );
      } else {
        blob = await createGenericDocxBlob(
          artifact.title,
          artifact.content,
          fontOptions
        );
      }
    } else if (format === "html") {
      fileExt = "html";
      const mimeType = "text/html;charset=utf-8";
      let content = "";
      if (isDoc) {
        content = generateStyledSnippetHtml(
          artifact.title,
          docMeta,
          snippets,
          uniquePages
        );
      } else {
        content =
          artifact.kind === ArtifactKind.Html
            ? artifact.content
            : `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escapeHtml(
                artifact.title
              )}</title><style>body{background:#F9F5EE;color:#4A2B24;font-family:sans-serif;padding:32px;}pre{background:#FFF;padding:20px;border-radius:12px;border:1px solid #DFD4C6;overflow-x:auto;}</style></head><body><h1>${escapeHtml(
                artifact.title
              )}</h1><pre><code>${escapeHtml(
                artifact.content
              )}</code></pre></body></html>`;
      }
      blob = new Blob([content], { type: mimeType });
    } else {
      fileExt = "txt";
      const mimeType = "text/plain;charset=utf-8";
      const content = isDoc
        ? generateSnippetPlainText(
            artifact.title,
            docMeta,
            snippets,
            uniquePages
          )
        : artifact.content;
      blob = new Blob([content], { type: mimeType });
    }

    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${safeName || "artifact"}.${fileExt}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    setDownloadedFormat(fileExt);
    setDownloadMenuOpen(false);
    setTimeout(() => setDownloadedFormat(null), 2400);
  };

  const lines = useMemo(() => artifact.content.split("\n"), [artifact.content]);

  const renderDownloadMenu = (align: "top" | "bottom" = "top") => (
    <div
      className={`absolute ${
        align === "top" ? "bottom-full mb-2" : "top-full mt-2"
      } right-0 w-72 rounded-xl border p-2 shadow-2xl z-50`}
      style={{
        backgroundColor: "var(--bg-surface)",
        borderColor: "var(--border-subtle)",
      }}
    >
      <div
        className="px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider border-b pb-1.5 mb-1"
        style={{
          color: "var(--text-muted)",
          borderColor: "var(--border-subtle)",
        }}
      >
        {tr("Choose Download Format")}
      </div>

      <button
        type="button"
        onClick={() => handleDownloadAs("html")}
        className="w-full flex items-start gap-2.5 px-2.5 py-2 rounded-lg text-left transition-colors cursor-pointer hover:opacity-90"
        style={{ backgroundColor: "transparent" }}
        onMouseEnter={(e) =>
          (e.currentTarget.style.backgroundColor = "var(--bg-card)")
        }
        onMouseLeave={(e) =>
          (e.currentTarget.style.backgroundColor = "transparent")
        }
      >
        <FileCode
          className="w-4 h-4 mt-0.5 shrink-0"
          style={{ color: "var(--accent-warm)" }}
        />
        <div className="min-w-0">
          <div
            className="text-xs font-semibold"
            style={{ color: "var(--text-heading)" }}
          >
            {tr("HTML Document (.html)")}
          </div>
          <div
            className="text-[11px] leading-tight"
            style={{ color: "var(--text-muted)" }}
          >
            {tr("Same style as shown · callouts, colors & fonts")}
          </div>
        </div>
      </button>

      <button
        type="button"
        onClick={() => handlePrintPdf()}
        className="w-full flex items-start gap-2.5 px-2.5 py-2 rounded-lg text-left transition-colors cursor-pointer hover:opacity-90"
        style={{ backgroundColor: "transparent" }}
        onMouseEnter={(e) =>
          (e.currentTarget.style.backgroundColor = "var(--bg-card)")
        }
        onMouseLeave={(e) =>
          (e.currentTarget.style.backgroundColor = "transparent")
        }
      >
        <FileText
          className="w-4 h-4 mt-0.5 shrink-0"
          style={{ color: "var(--accent-primary)" }}
        />
        <div className="min-w-0">
          <div
            className="text-xs font-semibold"
            style={{ color: "var(--text-heading)" }}
          >
            {tr("PDF (.pdf)")}
          </div>
          <div
            className="text-[11px] leading-tight"
            style={{ color: "var(--text-muted)" }}
          >
            {tr("Arabic-ready · pick Save as PDF in the print window")}
          </div>
        </div>
      </button>

      <button
        type="button"
        onClick={() => handleDownloadAs("docx")}
        className="w-full flex items-start gap-2.5 px-2.5 py-2 rounded-lg text-left transition-colors cursor-pointer hover:opacity-90"
        style={{ backgroundColor: "transparent" }}
        onMouseEnter={(e) =>
          (e.currentTarget.style.backgroundColor = "var(--bg-card)")
        }
        onMouseLeave={(e) =>
          (e.currentTarget.style.backgroundColor = "transparent")
        }
      >
        <FileText
          className="w-4 h-4 mt-0.5 shrink-0"
          style={{ color: "var(--accent-primary)" }}
        />
        <div className="min-w-0">
          <div
            className="text-xs font-semibold"
            style={{ color: "var(--text-heading)" }}
          >
            {tr("Word Document (.docx)")}
          </div>
          <div
            className="text-[11px] leading-tight"
            style={{ color: "var(--text-muted)" }}
          >
            {tr("Formatted rich document for Microsoft Word & Docs")}
          </div>
        </div>
      </button>

      <button
        type="button"
        onClick={() => handleDownloadAs("txt")}
        className="w-full flex items-start gap-2.5 px-2.5 py-2 rounded-lg text-left transition-colors cursor-pointer hover:opacity-90"
        style={{ backgroundColor: "transparent" }}
        onMouseEnter={(e) =>
          (e.currentTarget.style.backgroundColor = "var(--bg-card)")
        }
        onMouseLeave={(e) =>
          (e.currentTarget.style.backgroundColor = "transparent")
        }
      >
        <FileType
          className="w-4 h-4 mt-0.5 shrink-0 opacity-75"
          style={{ color: "var(--text-muted)" }}
        />
        <div className="min-w-0">
          <div
            className="text-xs font-semibold"
            style={{ color: "var(--text-heading)" }}
          >
            {tr("Plain Text (.txt)")}
          </div>
          <div
            className="text-[11px] leading-tight"
            style={{ color: "var(--text-muted)" }}
          >
            {tr("Clean structured text excerpts & rationale")}
          </div>
        </div>
      </button>
    </div>
  );

  return (
    <aside
      className={`h-full flex flex-col border-l transition-opacity duration-150 ${
        isExpanded ? "w-full lg:w-[62%]" : "w-full lg:w-[46%]"
      } shrink-0`}
      style={{
        backgroundColor: "var(--bg-surface)",
        borderColor: "var(--border-subtle)",
      }}
    >
      {/* Top Workbench Header */}
      <div
        className="flex items-center justify-between gap-3 px-4 py-3 border-b"
        style={{ borderColor: "var(--border-subtle)" }}
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {artifact.kind === ArtifactKind.Document ? (
              <FileCheck2
                className="w-4 h-4 shrink-0"
                style={{ color: "var(--accent-warm)" }}
              />
            ) : null}
            <h2
              className="font-editorial font-medium text-sm truncate"
              style={{ color: "var(--text-heading)" }}
            >
              {artifact.title}
            </h2>
          </div>
          {artifact.kind === ArtifactKind.Document ? (
            <div
              className="flex items-center gap-2 text-[11px] mt-1 font-code overflow-hidden whitespace-nowrap text-ellipsis"
              style={{ color: "var(--text-muted)" }}
            >
              <span
                className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider shrink-0"
                style={{
                  backgroundColor: "var(--bg-muted)",
                  color: "var(--accent-primary)",
                }}
              >
                {tr("PDF Evidence")}
              </span>
              <span className="shrink-0 font-medium">
                {snippets.length} {snippets.length === 1 ? "passage" : "passages"}
              </span>
              {pageSummaryText && (
                <>
                  <span
                    aria-hidden="true"
                    className="opacity-40 select-none shrink-0"
                  >
                    •
                  </span>
                  <span className="truncate">{pageSummaryText}</span>
                </>
              )}
            </div>
          ) : (
            <div
              className="flex items-center gap-1.5 text-[11px] mt-0.5 font-code truncate"
              style={{ color: "var(--text-muted)" }}
            >
              <span>{artifact.language}</span>
              <span aria-hidden="true" className="opacity-40 select-none">
                •
              </span>
              <span>{lines.length} {tr("lines")}</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {canPreview && artifact.kind !== ArtifactKind.Document && (
            <div
              className="flex items-center p-0.5 rounded-lg border"
              style={{
                backgroundColor: "var(--bg-canvas)",
                borderColor: "var(--border-subtle)",
              }}
            >
              <button
                type="button"
                onClick={() => setMode("preview")}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer whitespace-nowrap shrink-0"
                style={{
                  backgroundColor:
                    activeMode === "preview"
                      ? "var(--bg-surface)"
                      : "transparent",
                  color:
                    activeMode === "preview"
                      ? "var(--text-heading)"
                      : "var(--text-muted)",
                }}
              >
                <Eye className="w-3.5 h-3.5" />
                <span>{tr("Preview")}</span>
              </button>
              <button
                type="button"
                onClick={() => setMode("code")}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer whitespace-nowrap shrink-0"
                style={{
                  backgroundColor:
                    activeMode === "code" ? "var(--bg-surface)" : "transparent",
                  color:
                    activeMode === "code"
                      ? "var(--text-heading)"
                      : "var(--text-muted)",
                }}
              >
                <Code2 className="w-3.5 h-3.5" />
                <span>{tr("Source")}</span>
              </button>
            </div>
          )}

          <button
            type="button"
            onClick={onToggleExpand}
            title={isExpanded ? tr("Restore split width") : tr("Expand workbench")}
            className="hidden lg:inline-flex p-1.5 rounded-lg hover:opacity-75 transition-opacity cursor-pointer"
            style={{ color: "var(--text-muted)" }}
          >
            {isExpanded ? (
              <Minimize2 className="w-4 h-4" />
            ) : (
              <Maximize2 className="w-4 h-4" />
            )}
          </button>

          <button
            type="button"
            onClick={onClose}
            title={tr("Close workbench")}
            className="p-1.5 rounded-lg hover:opacity-75 transition-opacity cursor-pointer"
            style={{ color: "var(--text-muted)" }}
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Multi-Artifact Switcher if thread has >1 artifact */}
      {allArtifacts.length > 1 && (
        <div
          className="flex items-center gap-1.5 px-4 py-2 border-b overflow-x-auto"
          style={{
            backgroundColor: "var(--bg-canvas)",
            borderColor: "var(--border-subtle)",
          }}
        >
          {allArtifacts.map((item, idx) => {
            const active = item.id === artifact.id;
            const isDoc = item.kind === ArtifactKind.Document;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelectArtifact(item)}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer whitespace-nowrap shrink-0"
                style={{
                  backgroundColor: active ? "var(--bg-surface)" : "transparent",
                  color: active ? "var(--text-heading)" : "var(--text-muted)",
                  border: active
                    ? "1px solid var(--border-subtle)"
                    : "1px solid transparent",
                }}
              >
                {isDoc ? (
                  <FileText className="w-3.5 h-3.5 opacity-75" />
                ) : (
                  <span className="font-code opacity-70">v{idx + 1}</span>
                )}
                <span className="truncate max-w-[170px]">{item.title}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Main Content Stage */}
      <div className="flex-1 overflow-auto relative">
        {activeMode === "preview" &&
          (artifact.kind === ArtifactKind.Html ||
            artifact.kind === ArtifactKind.Svg) && (
            <iframe
              key={`${artifact.id}-${reloadKey}`}
              title={artifact.title}
              srcDoc={srcDoc}
              sandbox="allow-scripts"
              className="w-full h-full border-0 bg-[#F9F5EE]"
            />
          )}

        {activeMode === "preview" && artifact.kind === ArtifactKind.Markdown && (
          <div className="p-6 max-w-2xl mx-auto">
            <MarkdownRenderer content={artifact.content} />
          </div>
        )}

        {/* High-Fidelity PDF Document & Multi-Snippet Evidence Inspector */}
        {activeMode === "preview" && artifact.kind === ArtifactKind.Document && (
          <div
            className="p-5 sm:p-7 min-h-full flex flex-col justify-start items-center overflow-y-auto"
            style={{ backgroundColor: "var(--bg-canvas)" }}
          >
            <div className="w-full max-w-2xl space-y-6">
              {/* PDF Document Publication Master Header */}
              <div
                className="w-full rounded-2xl border p-6 sm:p-7 space-y-4 shadow-sm"
                style={{
                  backgroundColor: "var(--bg-surface)",
                  borderColor: "var(--border-subtle)",
                }}
              >
                <div
                  className="flex items-start justify-between gap-3 pb-3 border-b"
                  style={{ borderColor: "var(--border-subtle)" }}
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md font-code text-[11px] font-semibold uppercase tracking-wider"
                        style={{
                          backgroundColor: "var(--bg-muted)",
                          color: "var(--accent-primary)",
                        }}
                      >
                        <Bookmark className="w-3 h-3" />
                        {tr("PDF Document Evidence")}
                      </span>
                      <span
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md font-code text-[11px] font-medium"
                        style={{
                          backgroundColor: "var(--bg-card)",
                          color: "var(--text-heading)",
                        }}
                      >
                        <Layers className="w-3 h-3" />
                        {snippets.length} {tr("Verified")}{" "}
                        {snippets.length === 1 ? tr("Snippet") : "Snippets"}
                      </span>
                      {pageSummaryText && (
                        <span
                          className="font-code text-xs font-medium"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {pageSummaryText}
                        </span>
                      )}
                    </div>

                    <h3
                      className="font-editorial text-lg sm:text-xl font-medium leading-snug break-words pt-1"
                      style={{ color: "var(--text-heading)" }}
                    >
                      {docMeta?.filename || artifact.title}
                    </h3>

                    {docMeta?.authorOrSource && (
                      <div
                        className="text-xs font-serif italic"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {docMeta.authorOrSource}
                      </div>
                    )}
                  </div>

                {snippets.length > 0 && (
                  <button
                    type="button"
                    onClick={handleCopyAllPassages}
                    title={tr("Copy all verified citations formatted")}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium hover:opacity-85 transition-opacity cursor-pointer shrink-0"
                    style={{
                      backgroundColor: "var(--bg-canvas)",
                      borderColor: "var(--border-subtle)",
                      color: "var(--text-primary)",
                    }}
                  >
                    {copiedAllPassages ? (
                      <>
                        <Check className="w-3.5 h-3.5" />
                        <span>{tr("Copied All")}</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        <span>
                          {snippets.length > 1
                            ? tr("Copy All Snippets")
                            : tr("Copy Snippet")}
                        </span>
                      </>
                    )}
                  </button>
                )}
              </div>

                {/* Official Law Status Card (Moroccan Legal RAG Blueprint) */}
                {matchedLawStatus && (
                  <div
                    className="p-3.5 rounded-xl border text-xs space-y-2"
                    style={{
                      backgroundColor: "var(--bg-card)",
                      borderColor: "var(--border-subtle)",
                    }}
                  >
                    <div className="flex items-center justify-between">
                      <div
                        className="flex items-center gap-1.5 font-medium"
                        style={{ color: "var(--text-heading)" }}
                      >
                        <Scale className="w-3.5 h-3.5" style={{ color: "var(--accent-warm)" }} />
                        <span>{tr("Fiche Statut Législatif ·")} {matchedLawStatus.lawTitle}</span>
                      </div>
                      {matchedLawStatus.contestedStatus === "active_contested" ? (
                        <span
                          className="px-2 py-0.5 rounded text-[10px] font-semibold flex items-center gap-1"
                          style={{
                            backgroundColor: "var(--bg-muted)",
                            color: "var(--accent-warm)",
                          }}
                        >
                          <AlertTriangle className="w-3 h-3" /> ACTIVE_CONTESTED
                        </span>
                      ) : (
                        <span
                          className="px-2 py-0.5 rounded text-[10px] font-semibold flex items-center gap-1"
                          style={{
                            backgroundColor: "var(--bg-muted)",
                            color: "var(--accent-primary)",
                          }}
                        >
                          <ShieldCheck className="w-3 h-3" /> {tr("VERIFIED · BO")}
                        </span>
                      )}
                    </div>
                    <div
                      className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 text-[11px] border-t"
                      style={{ borderColor: "var(--border-subtle)" }}
                    >
                      <div>
                        <span
                          className="block text-[10px] uppercase font-semibold"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {tr("Dahir Royal")}
                        </span>
                        <span
                          className="font-medium truncate block"
                          style={{ color: "var(--text-heading)" }}
                        >
                          {matchedLawStatus.dahirNumber}
                        </span>
                      </div>
                      <div>
                        <span
                          className="block text-[10px] uppercase font-semibold"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {tr("Publication")}
                        </span>
                        <span
                          className="font-medium block"
                          style={{ color: "var(--text-heading)" }}
                        >
                          {matchedLawStatus.boNumber} ({matchedLawStatus.boDate})
                        </span>
                      </div>
                      <div>
                        <span
                          className="block text-[10px] uppercase font-semibold"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {tr("Vigueur")}
                        </span>
                        <span
                          className="font-semibold block"
                          style={{ color: "var(--accent-warm)" }}
                        >
                          {matchedLawStatus.validFrom}
                        </span>
                      </div>
                      <div>
                        <span
                          className="block text-[10px] uppercase font-semibold"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {tr("Type")}
                        </span>
                        <span
                          className="font-medium capitalize block"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {matchedLawStatus.implementingStatus.replace("_", " ")}
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Snippet Filter / Quick Jump Selector if multi-snippet */}
                {snippets.length > 1 && (
                  <div className="flex flex-wrap items-center gap-1.5 pt-1">
                    <span
                      className="text-[11px] font-medium mr-1"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {tr("View:")}
                    </span>
                    <button
                      type="button"
                      onClick={() => setSelectedSnippetFilter("all")}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors cursor-pointer"
                      style={{
                        backgroundColor:
                          selectedSnippetFilter === "all"
                            ? "var(--accent-primary)"
                            : "var(--bg-card)",
                        color:
                          selectedSnippetFilter === "all"
                            ? "var(--accent-primary-fg)"
                            : "var(--text-primary)",
                        border: "1px solid var(--border-subtle)",
                      }}
                    >
                      <Layers className="w-3 h-3" />
                      <span>{tr("All Snippets (")}{snippets.length})</span>
                    </button>

                    {snippets.map((snip, sIdx) => {
                      const isSelected = selectedSnippetFilter === snip.id;
                      return (
                        <button
                          key={snip.id}
                          type="button"
                          onClick={() => setSelectedSnippetFilter(snip.id)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors cursor-pointer"
                          style={{
                            backgroundColor: isSelected
                              ? "var(--accent-primary)"
                              : "var(--bg-canvas)",
                            color: isSelected
                              ? "var(--accent-primary-fg)"
                              : "var(--text-primary)",
                            border: "1px solid var(--border-subtle)",
                          }}
                        >
                          <span>
                            {tr("Snippet")} {sIdx + 1} · p. {snip.page}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Rendered Snippets Stream */}
              <div className="space-y-6">
                {(selectedSnippetFilter === "all"
                  ? snippets
                  : snippets.filter((s) => s.id === selectedSnippetFilter)
                ).map((snip, idx) => {
                  const globalIdx = snippets.findIndex((s) => s.id === snip.id);
                  const isCopied = copiedQuoteId === snip.id;

                  return (
                    <div
                      key={snip.id}
                      className="w-full rounded-2xl border p-6 sm:p-7 space-y-5 shadow-sm transition-all"
                      style={{
                        backgroundColor: "var(--bg-surface)",
                        borderColor: "var(--border-subtle)",
                      }}
                    >
                      {/* Individual Snippet Meta Header */}
                      <div
                        className="flex items-center justify-between gap-3 pb-3 border-b"
                        style={{ borderColor: "var(--border-subtle)" }}
                      >
                        <div className="flex items-center gap-2">
                          <span
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md font-code text-[11px] font-semibold"
                            style={{
                              backgroundColor: "var(--bg-muted)",
                              color: "var(--accent-warm)",
                            }}
                          >
                            {tr("Snippet")} {globalIdx + 1} {tr("of")} {snippets.length}
                          </span>
                          <span
                            className="font-code text-xs font-medium"
                            style={{ color: "var(--text-muted)" }}
                          >
                            {tr("Page")} {snip.page}
                            {snip.totalPages
                              ? ` of ${snip.totalPages}`
                              : docMeta?.totalPages
                              ? ` of ${docMeta.totalPages}`
                              : ""}
                          </span>
                        </div>

                        <button
                          type="button"
                          onClick={() =>
                            handleCopySnippetOnly(
                              snip.id,
                              snip.highlightedSnippet
                            )
                          }
                          title={tr("Copy this specific quote")}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-xs font-medium hover:opacity-85 transition-opacity cursor-pointer shrink-0"
                          style={{
                            backgroundColor: "var(--bg-canvas)",
                            borderColor: "var(--border-subtle)",
                            color: "var(--text-primary)",
                          }}
                        >
                          {isCopied ? (
                            <>
                              <Check className="w-3 h-3" />
                              <span>{tr("Copied")}</span>
                            </>
                          ) : (
                            <>
                              <Quote className="w-3 h-3" />
                              <span>{tr("Copy Quote")}</span>
                            </>
                          )}
                        </button>
                      </div>

                      {/* Section Context Header */}
                      {snip.sectionTitle && (
                        <div
                          className="font-code text-xs uppercase tracking-wider font-semibold"
                          style={{ color: "var(--accent-warm)" }}
                        >
                          {snip.sectionTitle}
                        </div>
                      )}

                      {/* Context Before */}
                      {snip.contextBefore && (
                        <p
                          className="text-xs sm:text-[13px] leading-relaxed font-serif opacity-80 italic"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {snip.contextBefore}
                        </p>
                      )}

                      {/* Verbatim Highlighted Evidence Excerpt */}
                      <div
                        className="relative p-4 sm:p-5 rounded-xl border space-y-2 transition-all"
                        style={{
                          backgroundColor: "var(--bg-card)",
                          borderColor: "var(--accent-warm)",
                        }}
                      >
                        <div className="flex items-center justify-between text-[11px] font-code">
                          <span
                            className="font-semibold uppercase tracking-wider flex items-center gap-1.5"
                            style={{ color: "var(--accent-primary)" }}
                          >
                            <Quote className="w-3.5 h-3.5" />
                            {tr("Verified Text Excerpt")}
                          </span>
                          <span style={{ color: "var(--text-muted)" }}>
                            p. {snip.page} {tr("· Verbatim")}
                          </span>
                        </div>

                        <blockquote dir="auto"
                          className="whitespace-pre-wrap font-editorial text-sm sm:text-base leading-relaxed tracking-wide italic font-medium"
                          style={{ color: "var(--text-heading)" }}
                        >
                          {/\|\s*:?-{3,}/.test(snip.highlightedSnippet) ? (
                            <MarkdownRenderer content={snip.highlightedSnippet} />
                          ) : (
                            <>&ldquo;{snip.highlightedSnippet}&rdquo;</>
                          )}
                        </blockquote>
                      </div>

                      {/* Context After */}
                      {snip.contextAfter && (
                        <p
                          className="text-xs sm:text-[13px] leading-relaxed font-serif opacity-80 italic"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {snip.contextAfter}
                        </p>
                      )}

                      {/* The real page(s) of the official PDF (only for articles of the law pack) */}
                      {snip.provisionId && snip.hasPdf && snip.pageStart ? (
                        <PdfPageImage provisionId={snip.provisionId} asOf={snip.asOf} pageStart={snip.pageStart} pageEnd={snip.pageEnd ?? snip.pageStart} />
                      ) : null}

                      {/* Agent Grounding Rationale Note for this Snippet */}
                      {snip.relevanceExplanation && (
                        <div
                          className="p-3.5 rounded-xl border flex items-start gap-2.5 text-xs"
                          style={{
                            backgroundColor: "var(--bg-muted)",
                            borderColor: "var(--border-subtle)",
                          }}
                        >
                          <Sparkles
                            className="w-4 h-4 shrink-0 mt-0.5"
                            style={{ color: "var(--accent-warm)" }}
                          />
                          <div className="space-y-0.5">
                            <span
                              className="font-semibold"
                              style={{ color: "var(--text-heading)" }}
                            >
                              {tr("Verification Rationale")}
                            </span>
                            <p
                              className="leading-relaxed"
                              style={{ color: "var(--text-primary)" }}
                            >
                              {snip.relevanceExplanation}
                            </p>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* Source / Code Mode */}
        {activeMode === "code" && (
          <div
            className="p-4 font-code text-xs leading-relaxed overflow-x-auto min-h-full"
            style={{ backgroundColor: "var(--bg-surface)" }}
          >
            <table className="w-full border-collapse">
              <tbody>
                {lines.map((line, idx) => (
                  <tr key={idx}>
                    <td
                      className="select-none pr-4 text-right align-top w-10 opacity-50"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {idx + 1}
                    </td>
                    <td
                      className="whitespace-pre align-top"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {line || " "}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Bottom Action Footer */}
      <div
        className="flex items-center justify-between gap-3 px-4 py-2.5 border-t text-xs"
        style={{
          backgroundColor: "var(--bg-canvas)",
          borderColor: "var(--border-subtle)",
        }}
      >
        <div className="flex items-center gap-2 min-w-0">
          {activeMode === "preview" &&
            (artifact.kind === ArtifactKind.Html ||
              artifact.kind === ArtifactKind.Svg) && (
              <button
                type="button"
                onClick={() => setReloadKey((k) => k + 1)}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border font-medium hover:opacity-85 transition-opacity cursor-pointer whitespace-nowrap shrink-0"
                style={{
                  backgroundColor: "var(--bg-surface)",
                  borderColor: "var(--border-subtle)",
                  color: "var(--text-primary)",
                }}
              >
                <RotateCw className="w-3.5 h-3.5" />
                <span>{tr("Reset preview")}</span>
              </button>
            )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={handleCopy}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border font-medium hover:opacity-85 transition-opacity cursor-pointer whitespace-nowrap shrink-0"
            style={{
              backgroundColor: "var(--bg-surface)",
              borderColor: "var(--border-subtle)",
              color: "var(--text-primary)",
            }}
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5" />
                <span>{tr("Copied")}</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>
                  {artifact.kind === ArtifactKind.Document
                    ? tr("Copy Excerpt")
                    : tr("Copy")}
                </span>
              </>
            )}
          </button>

          <div className="relative shrink-0" ref={downloadDropdownRef}>
            <button
              type="button"
              onClick={() => setDownloadMenuOpen((v) => !v)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium hover:opacity-90 transition-opacity cursor-pointer whitespace-nowrap shrink-0"
              style={{
                backgroundColor: "var(--accent-primary)",
                color: "var(--accent-primary-fg)",
              }}
            >
              {downloadedFormat ? (
                <>
                  <Check className="w-3.5 h-3.5" />
                  <span>{tr("Downloaded .")}{downloadedFormat}</span>
                </>
              ) : (
                <>
                  <Download className="w-3.5 h-3.5" />
                  <span>{tr("Download")}</span>
                  <ChevronDown
                    className={`w-3 h-3 transition-transform duration-150 ${
                      downloadMenuOpen ? "rotate-180" : ""
                    }`}
                  />
                </>
              )}
            </button>

            {downloadMenuOpen && renderDownloadMenu("top")}
          </div>
        </div>
      </div>
    </aside>
  );
};
