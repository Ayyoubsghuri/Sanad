import React, { useState } from "react";
import { tr } from "../i18n";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";

interface MarkdownRendererProps {
  content: string;
}

const CodeBlock: React.FC<{ language: string; code: string }> = ({
  language,
  code,
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Fallback ignored safely
    }
  };

  return (
    <div
      className="my-4 rounded-xl border overflow-hidden"
      style={{
        backgroundColor: "var(--bg-surface)",
        borderColor: "var(--border-subtle)",
      }}
    >
      <div
        className="flex items-center justify-between px-3.5 py-2 border-b text-xs"
        style={{
          backgroundColor: "var(--bg-muted)",
          borderColor: "var(--border-subtle)",
          color: "var(--text-muted)",
        }}
      >
        <span className="font-code">{language || "code"}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex items-center gap-1.5 text-xs font-medium hover:opacity-80 transition-opacity cursor-pointer whitespace-nowrap shrink-0"
          style={{ color: "var(--text-primary)" }}
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5" />
              <span>{tr("Copied")}</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              <span>{tr("Copy")}</span>
            </>
          )}
        </button>
      </div>
      <pre className="p-4 overflow-x-auto text-[13px] leading-relaxed font-code m-0">
        <code style={{ color: "var(--text-primary)" }}>{code}</code>
      </pre>
    </div>
  );
};

const ARABIC = /[\u0600-\u06FF\u0750-\u077F]/;
function textOf(n: React.ReactNode): string {
  if (n == null || typeof n === "boolean") return "";
  if (typeof n === "string" || typeof n === "number") return String(n);
  if (Array.isArray(n)) return n.map(textOf).join("");
  if (React.isValidElement(n)) return textOf((n.props as { children?: React.ReactNode }).children);
  return "";
}
const hasArabic = (n: React.ReactNode) => ARABIC.test(textOf(n));

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  content,
}) => {
  return (
    <div className="prose-scalable space-y-3.5 break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1
              dir="auto"
              className="font-editorial font-medium heading-scalable-lg mt-6 mb-2.5"
              style={{ color: "var(--text-heading)" }}
            >
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2
              dir="auto"
              className="font-editorial font-medium text-lg mt-5 mb-2"
              style={{ color: "var(--text-heading)" }}
            >
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3
              dir="auto"
              className="font-editorial font-medium text-base mt-4 mb-1.5"
              style={{ color: "var(--text-heading)" }}
            >
              {children}
            </h3>
          ),
          p: ({ children }) => (
            <p dir="auto" className="leading-[1.7] my-2.5" style={{ color: "var(--text-primary)" }}>
              {children}
            </p>
          ),
          ul: ({ children }) => (
            <ul dir="auto" className="list-disc ps-5 space-y-1.5 my-2.5">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol dir="auto" className="list-decimal ps-5 space-y-1.5 my-2.5">{children}</ol>
          ),
          li: ({ children }) => (
            <li dir="auto" className="leading-[1.65]" style={{ color: "var(--text-primary)" }}>
              {children}
            </li>
          ),
          // Arabic is never slanted: a synthetic italic breaks the joined letters and moves the punctuation, so it looked "weird"
          em: ({ children }) => (
            <em className={hasArabic(children) ? "not-italic" : "italic"}>{children}</em>
          ),
          blockquote: ({ children }) => (
            <blockquote
              dir="auto"
              className={`my-3.5 p-3.5 rounded-xl border ${hasArabic(children) ? "" : "italic"} font-editorial`}
              style={{
                backgroundColor: "var(--bg-muted)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-primary)",
              }}
            >
              {children}
            </blockquote>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-3 transition-opacity hover:opacity-75"
              style={{ color: "var(--accent-primary)" }}
            >
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div
              className="my-4 overflow-x-auto rounded-xl border"
              style={{ borderColor: "var(--border-subtle)" }}
            >
              <table className="w-full border-collapse text-sm font-code">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead style={{ backgroundColor: "var(--bg-muted)" }}>
              {children}
            </thead>
          ),
          th: ({ children }) => (
            <th
              className="px-3.5 py-2.5 text-left text-xs font-semibold border-b"
              style={{
                borderColor: "var(--border-strong)",
                color: "var(--text-heading)",
              }}
            >
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td
              className="px-3.5 py-2.5 text-xs border-b"
              style={{
                borderColor: "var(--border-subtle)",
                color: "var(--text-primary)",
              }}
            >
              {children}
            </td>
          ),
          code: ({ className, children }) => {
            const match = /language-(\w+)/.exec(className || "");
            const rawCode = String(children).replace(/\n$/, "");
            const isBlock = Boolean(match || rawCode.includes("\n"));

            if (isBlock) {
              return (
                <CodeBlock
                  language={match ? match[1] : "text"}
                  code={rawCode}
                />
              );
            }

            return (
              <code
                className="px-1.5 py-0.5 rounded-md font-code text-[0.86em]"
                style={{
                  backgroundColor: "var(--bg-card)",
                  color: "var(--text-heading)",
                }}
              >
                {children}
              </code>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};
