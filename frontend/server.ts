import "dotenv/config";
import express from "express";
import type { Request, Response } from "express";
import path from "path";
import { fileURLToPath } from "url";
import { createServer as createViteServer } from "vite";
import { GoogleGenAI, ThinkingLevel, Type } from "@google/genai";
import type {
  Content,
  FunctionCall,
  FunctionDeclaration,
  Part,
} from "@google/genai";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

interface ClientAttachment {
  id: string;
  name: string;
  mimeType: string;
  dataUrl?: string;
  textContent?: string;
}

interface ClientMessage {
  role: "user" | "assistant";
  content: string;
  attachments?: ClientAttachment[];
}

interface ProjectDoc {
  id: string;
  title: string;
  content: string;
}

interface ChatRequestBody {
  messages: ClientMessage[];
  systemInstruction?: string;
  thinkingMode?: boolean;
  thinkingBudget?: number;
  enableWebSearch?: boolean;
  projectDocs?: ProjectDoc[];
}

function getGenAIClient(): GoogleGenAI {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    throw new Error(
      "GEMINI_API_KEY is not configured. Please check the Settings > Secrets panel."
    );
  }
  return new GoogleGenAI({
    apiKey,
    httpOptions: {
      headers: {
        "User-Agent": "aistudio-build",
      },
    },
  });
}

function sendSse(res: Response, event: string, payload: unknown): void {
  if (res.writableEnded) return;
  res.write(`event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`);
}

const createArtifactTool: FunctionDeclaration = {
  name: "create_artifact",
  description:
    "Create or update a standalone visual or technical artifact in the right-hand Artifact Workbench. Use this whenever the user asks for an interactive UI mockup, HTML/CSS/JS widget, chart/data visualization, SVG illustration/diagram, comprehensive Markdown report/plan, or substantial code module (>20 lines). For 'html' artifacts, provide a complete self-contained HTML5 document with inline CSS/JS.",
  parameters: {
    type: Type.OBJECT,
    properties: {
      title: {
        type: Type.STRING,
        description: "Clear, human-readable title of the artifact.",
      },
      kind: {
        type: Type.STRING,
        description:
          "Artifact type: 'html' (interactive web preview/chart/app), 'svg' (vector graphic or diagram), 'markdown' (structured document/report), or 'code' (source file).",
      },
      language: {
        type: Type.STRING,
        description:
          "Language identifier such as 'html', 'svg', 'markdown', 'typescript', 'python', or 'json'.",
      },
      summary: {
        type: Type.STRING,
        description: "One-sentence description of what this artifact provides.",
      },
      content: {
        type: Type.STRING,
        description: "Complete, runnable, self-contained content of the artifact.",
      },
    },
    required: ["title", "kind", "language", "content"],
  },
};

const webSearchTool: FunctionDeclaration = {
  name: "web_search",
  description:
    "Search the live web for up-to-date facts, news, documentation, benchmarks, or market data. Returns grounded findings and verified source URLs.",
  parameters: {
    type: Type.OBJECT,
    properties: {
      query: {
        type: Type.STRING,
        description: "Focused search query to investigate.",
      },
      focus: {
        type: Type.STRING,
        description: "Optional aspect to prioritize (e.g., 'pricing', 'architecture', 'recent releases').",
      },
    },
    required: ["query"],
  },
};

const analyzeDatasetTool: FunctionDeclaration = {
  name: "analyze_dataset",
  description:
    "Run exact numerical and statistical analysis on a list of numbers or labeled values (sum, mean, median, min, max, standard deviation, growth percentage, and share breakdown).",
  parameters: {
    type: Type.OBJECT,
    properties: {
      label: {
        type: Type.STRING,
        description: "Name of the metric or dataset being analyzed.",
      },
      items: {
        type: Type.ARRAY,
        description: "Ordered list of labeled numeric observations.",
        items: {
          type: Type.OBJECT,
          properties: {
            name: { type: Type.STRING, description: "Row or period label." },
            value: { type: Type.NUMBER, description: "Numeric value." },
          },
          required: ["name", "value"],
        },
      },
    },
    required: ["label", "items"],
  },
};

const saveWorkspaceNoteTool: FunctionDeclaration = {
  name: "save_workspace_note",
  description:
    "Save an important architectural decision, user preference, or key takeaway into the persistent Project Knowledge notebook when the user asks to remember or log something.",
  parameters: {
    type: Type.OBJECT,
    properties: {
      title: {
        type: Type.STRING,
        description: "Short note heading.",
      },
      content: {
        type: Type.STRING,
        description: "Concise note body to persist in the workspace.",
      },
    },
    required: ["title", "content"],
  },
};

const citePdfEvidenceTool: FunctionDeclaration = {
  name: "cite_pdf_evidence",
  description:
    "Extract and present verified textual evidence from a PDF, academic study, research paper, whitepaper, or document to substantiate an answer. Opens a dedicated high-fidelity Document Evidence Artifact in the Artifact Workbench. Can include one or multiple snippets/passages across different pages in a single artifact.",
  parameters: {
    type: Type.OBJECT,
    properties: {
      documentTitle: {
        type: Type.STRING,
        description: "Title of the PDF or source document (e.g. 'Clinical_Neuro_Acoustics_Trial_2025.pdf').",
      },
      totalPages: {
        type: Type.NUMBER,
        description: "Total page count of the document if known (e.g. 42).",
      },
      authorOrSource: {
        type: Type.STRING,
        description: "Author, institution, or journal reference.",
      },
      snippets: {
        type: Type.ARRAY,
        description:
          "List of verified textual excerpts/snippets from the PDF. Provide multiple items when citing evidence across different pages or sections.",
        items: {
          type: Type.OBJECT,
          properties: {
            pageNumber: {
              type: Type.STRING,
              description: "Page number for this excerpt (e.g. '14' or 'p. 18').",
            },
            sectionTitle: {
              type: Type.STRING,
              description: "Header or chapter where this excerpt is located.",
            },
            highlightedSnippet: {
              type: Type.STRING,
              description: "The exact, verbatim passage that serves as primary evidence.",
            },
            contextBefore: {
              type: Type.STRING,
              description: "Preceding sentences or paragraph for context.",
            },
            contextAfter: {
              type: Type.STRING,
              description: "Succeeding sentences or paragraph for context.",
            },
            relevanceExplanation: {
              type: Type.STRING,
              description: "Why this specific excerpt grounds or proves your claim.",
            },
          },
          required: ["highlightedSnippet"],
        },
      },
      // Root-level fields for single-snippet fallback
      pageNumber: {
        type: Type.STRING,
        description: "Single snippet page number (e.g. '18').",
      },
      sectionTitle: {
        type: Type.STRING,
        description: "Single snippet section header.",
      },
      highlightedSnippet: {
        type: Type.STRING,
        description: "Single snippet verbatim text.",
      },
      contextBefore: {
        type: Type.STRING,
        description: "Single snippet context before.",
      },
      contextAfter: {
        type: Type.STRING,
        description: "Single snippet context after.",
      },
      relevanceExplanation: {
        type: Type.STRING,
        description: "Single snippet relevance explanation.",
      },
    },
    required: ["documentTitle"],
  },
};

function computeDatasetStats(
  label: string,
  items: Array<{ name: string; value: number }>
) {
  if (!Array.isArray(items) || items.length === 0) {
    return { label, count: 0, error: "Dataset was empty." };
  }
  const values = items.map((d) => Number(d.value) || 0);
  const count = values.length;
  const sum = values.reduce((acc, v) => acc + v, 0);
  const mean = sum / count;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(count / 2);
  const median =
    count % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  const min = sorted[0];
  const max = sorted[count - 1];
  const variance =
    values.reduce((acc, v) => acc + Math.pow(v - mean, 2), 0) / count;
  const stdDev = Math.sqrt(variance);
  const first = values[0];
  const last = values[count - 1];
  const netChangePct =
    first !== 0 ? Number((((last - first) / Math.abs(first)) * 100).toFixed(2)) : null;

  const breakdown = items.map((item) => ({
    name: item.name,
    value: item.value,
    sharePct: sum !== 0 ? Number(((item.value / sum) * 100).toFixed(2)) : 0,
  }));

  return {
    label,
    count,
    sum: Number(sum.toFixed(4)),
    mean: Number(mean.toFixed(4)),
    median: Number(median.toFixed(4)),
    min,
    max,
    stdDev: Number(stdDev.toFixed(4)),
    netChangePct,
    breakdown,
  };
}

function buildConversationContents(messages: ClientMessage[]): Content[] {
  return messages.map((msg) => {
    const parts: Part[] = [];

    if (msg.attachments && msg.attachments.length > 0) {
      for (const att of msg.attachments) {
        if (att.dataUrl && att.dataUrl.includes("base64,")) {
          const base64Data = att.dataUrl.split("base64,")[1];
          parts.push({
            inlineData: {
              mimeType: att.mimeType || "image/png",
              data: base64Data,
            },
          });
        } else if (att.textContent) {
          parts.push({
            text: `[Attached File: ${att.name}]\n\`\`\`\n${att.textContent}\n\`\`\``,
          });
        }
      }
    }

    if (msg.content && msg.content.trim().length > 0) {
      parts.push({ text: msg.content });
    } else if (parts.length === 0) {
      parts.push({ text: "Please examine the attached content." });
    }

    return {
      role: msg.role === "assistant" ? "model" : "user",
      parts,
    };
  });
}

function formatErrorMessage(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err);
  if (
    raw.includes("API_KEY_INVALID") ||
    raw.includes("PERMISSION_DENIED") ||
    raw.includes("403")
  ) {
    return "Unable to authenticate with Gemini API. Please verify your API key in the Settings > Secrets panel.";
  }
  if (raw.includes("RESOURCE_EXHAUSTED") || raw.includes("429")) {
    return "API rate limit reached. Upgrading to a billing-enabled key in Settings > Secrets increases your quota.";
  }
  return raw || "An unexpected error occurred while running the agent.";
}

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(express.json({ limit: "25mb" }));

  app.get("/api/health", (_req: Request, res: Response) => {
    res.json({ ok: true });
  });

  app.post("/api/agent/title", async (req: Request, res: Response) => {
    try {
      const { prompt } = req.body as { prompt?: string };
      if (!prompt || !prompt.trim()) {
        res.json({ title: "New Conversation" });
        return;
      }
      const ai = getGenAIClient();
      const response = await ai.models.generateContent({
        model: "gemini-3.8-flash",
        contents: `Write a concise, natural 3 to 5 word title-case heading summarizing this user request. Do not use quotes, punctuation, or prefixes:\n\n${prompt.slice(0, 500)}`,
        config: {
          thinkingConfig: { thinkingLevel: ThinkingLevel.LOW },
        },
      });
      const cleaned = (response.text || "New Conversation")
        .replace(/^["'#*\s]+|["'.\s]+$/g, "")
        .slice(0, 64);
      res.json({ title: cleaned || "New Conversation" });
    } catch {
      res.json({ title: "New Conversation" });
    }
  });

  app.post("/api/agent/chat", async (req: Request, res: Response) => {
    res.setHeader("Content-Type", "text/event-stream; charset=utf-8");
    res.setHeader("Cache-Control", "no-cache, no-transform");
    res.setHeader("Connection", "keep-alive");
    res.flushHeaders?.();

    let aborted = false;
    req.on("close", () => {
      aborted = true;
    });

    try {
      const {
        messages = [],
        systemInstruction = "",
        thinkingMode = true,
        thinkingBudget = 8000,
        enableWebSearch = true,
        projectDocs = [],
      } = req.body as ChatRequestBody;

      const ai = getGenAIClient();
      const contents = buildConversationContents(messages);

      const docsContext =
        projectDocs.length > 0
          ? `\n\nWorkspace Project Knowledge:\n${projectDocs
              .map((d) => `### ${d.title}\n${d.content}`)
              .join("\n\n")}`
          : "";

      const fullSystemInstruction = [
        "You are Sanad, a calm, perceptive, senior-level AI research, engineering, and design agent.",
        "Write with clarity, warmth, intellectual rigor, and zero filler.",
        "When the user requests an interactive prototype, visualization, dashboard, SVG diagram, calculator, soundscape, or substantial code/report, call `create_artifact` so it opens directly in the interactive Artifact Workbench.",
        "When creating an 'html' artifact, build a complete, responsive, self-contained HTML5 page with polished warm organic styling (soft stone/linen backgrounds `#F9F5EE` / `#EFE8DD`, deep espresso-oxblood typography `#4A2B24`, warm clay accents `#C59B7B`), interactive controls, and zero external broken images.",
        "After calling `create_artifact`, summarize your design or architectural choices concisely in chat rather than repeating the full artifact source code.",
        enableWebSearch
          ? "When a question involves current events, live facts, external benchmarks, or verifiable references, call `web_search` first."
          : "",
        "When analyzing numbers or tables, use `analyze_dataset` to guarantee exact figures.",
        "When providing answers substantiated by academic research, books, whitepapers, clinical trials, or user-attached documents, call `cite_pdf_evidence` to display the exact PDF page snippet, highlighted quotation, and verification context directly in the Artifact Workbench.",
        systemInstruction ? `\nCustom User Guidance:\n${systemInstruction}` : "",
        docsContext,
      ]
        .filter(Boolean)
        .join("\n");

      const declarations: FunctionDeclaration[] = [
        createArtifactTool,
        citePdfEvidenceTool,
        analyzeDatasetTool,
        saveWorkspaceNoteTool,
      ];
      if (enableWebSearch) {
        declarations.push(webSearchTool);
      }

      const maxIterations = 4;
      let iteration = 0;

      while (iteration < maxIterations && !aborted) {
        iteration += 1;
        const thinkStepId = `think-${iteration}-${Date.now()}`;
        const thinkStartedAt = Date.now();
        let emittedThinkStart = false;
        let thoughtBuffer = "";

        const stream = await ai.models.generateContentStream({
          model: "gemini-3.8-flash",
          contents,
          config: {
            systemInstruction: fullSystemInstruction,
            tools: [{ functionDeclarations: declarations }],
            thinkingConfig: {
              thinkingLevel: thinkingMode
                ? (thinkingBudget < 4000 ? ThinkingLevel.LOW : ThinkingLevel.HIGH)
                : ThinkingLevel.LOW,
              thinkingBudget: thinkingMode ? thinkingBudget : 0,
              includeThoughts: Boolean(thinkingMode),
            },
          },
        });

        const modelTurnParts: Part[] = [];
        const pendingFunctionCalls: FunctionCall[] = [];

        for await (const chunk of stream) {
          if (aborted) break;
          const parts = chunk.candidates?.[0]?.content?.parts || [];
          for (const part of parts) {
            modelTurnParts.push(part);

            if (part.thought && part.text) {
              if (!emittedThinkStart) {
                emittedThinkStart = true;
                sendSse(res, "step_start", {
                  id: thinkStepId,
                  kind: "thinking",
                  title:
                    iteration === 1
                      ? "Reasoning through request"
                      : "Synthesizing tool findings",
                  detail: "",
                });
              }
              thoughtBuffer += part.text;
              sendSse(res, "step_delta", {
                id: thinkStepId,
                delta: part.text,
              });
            } else if (part.functionCall) {
              pendingFunctionCalls.push(part.functionCall);
            } else if (part.text) {
              if (emittedThinkStart) {
                sendSse(res, "step_complete", {
                  id: thinkStepId,
                  detail: thoughtBuffer.trim(),
                  durationMs: Date.now() - thinkStartedAt,
                });
                emittedThinkStart = false;
              }
              sendSse(res, "text_delta", { text: part.text });
            }
          }
        }

        if (emittedThinkStart) {
          sendSse(res, "step_complete", {
            id: thinkStepId,
            detail: thoughtBuffer.trim(),
            durationMs: Date.now() - thinkStartedAt,
          });
        }

        if (aborted || pendingFunctionCalls.length === 0) {
          break;
        }

        contents.push({
          role: "model",
          parts: modelTurnParts,
        });

        const functionResponseParts: Part[] = [];

        for (const call of pendingFunctionCalls) {
          if (aborted) break;
          const stepId = `tool-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
          const startedAt = Date.now();
          const args = (call.args || {}) as Record<string, unknown>;

          if (call.name === "web_search") {
            const query = String(args.query || "");
            const focus = args.focus ? ` (${String(args.focus)})` : "";
            sendSse(res, "step_start", {
              id: stepId,
              kind: "search",
              title: `Searching web: ${query}`,
              detail: `Querying live sources${focus}`,
            });

            try {
              const searchRes = await ai.models.generateContent({
                model: "gemini-3.8-flash",
                contents: `Research the following query thoroughly and summarize key verifiable facts, dates, and numbers:\nQuery: ${query}${focus}`,
                config: {
                  tools: [{ googleSearch: {} }],
                  thinkingConfig: { thinkingLevel: ThinkingLevel.LOW },
                },
              });

              const groundingChunks =
                searchRes.candidates?.[0]?.groundingMetadata?.groundingChunks || [];
              const extractedSources: Array<{ title: string; uri: string }> = [];
              const seenUris = new Set<string>();

              for (const gc of groundingChunks) {
                const uri = gc.web?.uri;
                const title = gc.web?.title || "Web Source";
                if (uri && !seenUris.has(uri)) {
                  seenUris.add(uri);
                  extractedSources.push({ title, uri });
                }
              }

              if (extractedSources.length > 0) {
                sendSse(res, "sources", { sources: extractedSources });
              }

              const summaryText =
                searchRes.text || "Completed search with no additional text.";

              sendSse(res, "step_complete", {
                id: stepId,
                title: `Searched web · ${extractedSources.length} ${extractedSources.length === 1 ? "source" : "sources"}`,
                detail: summaryText.slice(0, 900),
                durationMs: Date.now() - startedAt,
              });

              functionResponseParts.push({
                functionResponse: {
                  id: call.id,
                  name: call.name,
                  response: {
                    summary: summaryText,
                    sources: extractedSources,
                  },
                },
              });
            } catch (searchErr) {
              const errMsg = formatErrorMessage(searchErr);
              sendSse(res, "step_complete", {
                id: stepId,
                title: "Web search encountered an issue",
                detail: errMsg,
                durationMs: Date.now() - startedAt,
              });
              functionResponseParts.push({
                functionResponse: {
                  id: call.id,
                  name: call.name,
                  response: { error: errMsg },
                },
              });
            }
          } else if (call.name === "create_artifact") {
            const title = String(args.title || "Untitled Artifact");
            const kind = String(args.kind || "html");
            const language = String(args.language || kind);
            const summary = String(args.summary || "");
            const content = String(args.content || "");

            sendSse(res, "step_start", {
              id: stepId,
              kind: "artifact",
              title: `Drafting artifact: ${title}`,
              detail: summary || `Generating ${language} workspace artifact`,
            });

            const artifactPayload = {
              id: `art-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
              title,
              kind: ["html", "svg", "markdown", "code"].includes(kind)
                ? kind
                : "code",
              language,
              summary,
              content,
              createdAt: new Date().toISOString(),
            };

            sendSse(res, "artifact", { artifact: artifactPayload });
            sendSse(res, "step_complete", {
              id: stepId,
              title: `Built artifact: ${title}`,
              detail: `${summary ? `${summary}\n` : ""}${content.split("\n").length} lines of ${language}`,
              durationMs: Date.now() - startedAt,
            });

            functionResponseParts.push({
              functionResponse: {
                id: call.id,
                name: call.name,
                response: {
                  status: "displayed_in_workbench",
                  artifactId: artifactPayload.id,
                  title,
                  note: "The artifact is now rendered live in the user's right-hand Artifact Workbench. Provide a concise, insightful overview without repeating the full code.",
                },
              },
            });
          } else if (call.name === "cite_pdf_evidence") {
            const documentTitle = String(args.documentTitle || "Document_Excerpt.pdf");
            const totalPages = typeof args.totalPages === "number" ? args.totalPages : undefined;
            const authorOrSource = args.authorOrSource ? String(args.authorOrSource) : undefined;

            interface RawSnippet {
              id?: string;
              pageNumber?: string | number;
              sectionTitle?: string;
              highlightedSnippet: string;
              contextBefore?: string;
              contextAfter?: string;
              relevanceExplanation?: string;
            }

            const rawSnippets: RawSnippet[] = Array.isArray(args.snippets) && args.snippets.length > 0
              ? (args.snippets as RawSnippet[])
              : [
                  {
                    id: "snip-1",
                    pageNumber: args.pageNumber ? String(args.pageNumber) : "1",
                    sectionTitle: args.sectionTitle ? String(args.sectionTitle) : undefined,
                    highlightedSnippet: String(args.highlightedSnippet || ""),
                    contextBefore: args.contextBefore ? String(args.contextBefore) : undefined,
                    contextAfter: args.contextAfter ? String(args.contextAfter) : undefined,
                    relevanceExplanation: args.relevanceExplanation ? String(args.relevanceExplanation) : undefined,
                  },
                ];

            const parsedSnippets = rawSnippets
              .filter((s) => Boolean(s.highlightedSnippet && s.highlightedSnippet.trim()))
              .map((s, idx) => ({
                id: s.id || `snip-${idx + 1}-${Date.now().toString(36)}`,
                page: String(s.pageNumber || args.pageNumber || "1"),
                totalPages,
                sectionTitle: s.sectionTitle,
                highlightedSnippet: s.highlightedSnippet.trim(),
                contextBefore: s.contextBefore?.trim(),
                contextAfter: s.contextAfter?.trim(),
                relevanceExplanation: s.relevanceExplanation?.trim(),
              }));

            const snippetCount = parsedSnippets.length;
            const uniquePages = [...new Set(parsedSnippets.map((s) => s.page))];
            const pageSummary =
              uniquePages.length === 1
                ? `p. ${uniquePages[0]}`
                : `pp. ${uniquePages.join(", ")}`;

            sendSse(res, "step_start", {
              id: stepId,
              kind: "evidence",
              title: `Citing PDF evidence: ${documentTitle}`,
              detail: `Extracting ${snippetCount} verified ${
                snippetCount === 1 ? "passage" : "passages"
              } (${pageSummary})`,
            });

            const firstSnippet = parsedSnippets[0] || {
              id: "snip-1",
              page: "1",
              highlightedSnippet: "",
            };

            const combinedContent = parsedSnippets
              .map(
                (s, i) =>
                  `### Excerpt ${i + 1} (Page ${s.page}${s.sectionTitle ? ` · ${s.sectionTitle}` : ""})\n\n> "${s.highlightedSnippet}"\n\n${
                    s.relevanceExplanation ? `*Significance: ${s.relevanceExplanation}*\n` : ""
                  }`
              )
              .join("\n---\n\n");

            const artifactPayload = {
              id: `art-doc-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
              title:
                snippetCount > 1
                  ? `${documentTitle} · ${snippetCount} Evidence Passages`
                  : `${documentTitle} · p. ${firstSnippet.page}`,
              kind: "document",
              language: "pdf",
              summary:
                firstSnippet.relevanceExplanation ||
                `Extracted ${snippetCount} verified ${
                  snippetCount === 1 ? "passage" : "passages"
                } from ${documentTitle} (${pageSummary})`,
              content: combinedContent || firstSnippet.highlightedSnippet,
              documentMeta: {
                filename: documentTitle,
                authorOrSource,
                totalPages,
                snippets: parsedSnippets,
                // Root fallbacks
                page: firstSnippet.page,
                sectionTitle: firstSnippet.sectionTitle,
                highlightedSnippet: firstSnippet.highlightedSnippet,
                contextBefore: firstSnippet.contextBefore,
                contextAfter: firstSnippet.contextAfter,
                relevanceExplanation: firstSnippet.relevanceExplanation,
              },
              createdAt: new Date().toISOString(),
            };

            sendSse(res, "artifact", { artifact: artifactPayload });
            sendSse(res, "step_complete", {
              id: stepId,
              title: `Cited PDF evidence · ${documentTitle} (${snippetCount} ${
                snippetCount === 1 ? "passage" : "passages"
              }, ${pageSummary})`,
              detail: parsedSnippets.map((s) => `[p. ${s.page}] "${s.highlightedSnippet}"`).join("\n\n"),
              durationMs: Date.now() - startedAt,
            });

            functionResponseParts.push({
              functionResponse: {
                id: call.id,
                name: call.name,
                response: {
                  status: "evidence_rendered_in_workbench",
                  artifactId: artifactPayload.id,
                  documentTitle,
                  snippetCount,
                  pages: uniquePages,
                  note: `All ${snippetCount} verified evidence snippets with page references and highlighted quotes are now displayed together in the user's Artifact Workbench. Provide your answer referencing these passages.`,
                },
              },
            });
          } else if (call.name === "analyze_dataset") {
            const label = String(args.label || "Dataset");
            const items = Array.isArray(args.items)
              ? (args.items as Array<{ name: string; value: number }>)
              : [];

            sendSse(res, "step_start", {
              id: stepId,
              kind: "analysis",
              title: `Analyzing ${label}`,
              detail: `Computing statistics across ${items.length} data points`,
            });

            const stats = computeDatasetStats(label, items);

            sendSse(res, "step_complete", {
              id: stepId,
              title: `Analyzed ${label} · ${items.length} rows`,
              detail: JSON.stringify(stats, null, 2),
              durationMs: Date.now() - startedAt,
            });

            functionResponseParts.push({
              functionResponse: {
                id: call.id,
                name: call.name,
                response: stats,
              },
            });
          } else if (call.name === "save_workspace_note") {
            const title = String(args.title || "Workspace Note");
            const content = String(args.content || "");

            sendSse(res, "step_start", {
              id: stepId,
              kind: "memory",
              title: `Saving note: ${title}`,
              detail: content,
            });

            const note = {
              id: `note-${Date.now()}`,
              title,
              content,
            };

            sendSse(res, "project_note", { note });
            sendSse(res, "step_complete", {
              id: stepId,
              title: `Saved to Project Knowledge: ${title}`,
              detail: content,
              durationMs: Date.now() - startedAt,
            });

            functionResponseParts.push({
              functionResponse: {
                id: call.id,
                name: call.name,
                response: { saved: true, title },
              },
            });
          } else {
            functionResponseParts.push({
              functionResponse: {
                id: call.id,
                name: call.name || "unknown_tool",
                response: { error: "Unsupported tool name" },
              },
            });
          }
        }

        contents.push({
          role: "user",
          parts: functionResponseParts,
        });
      }

      sendSse(res, "done", { ok: true });
      res.end();
    } catch (err) {
      sendSse(res, "error", { message: formatErrorMessage(err) });
      res.end();
    }
  });

  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(__dirname, "dist");
    app.use(express.static(distPath));
    app.get("*", (_req: Request, res: Response) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Sanad server listening on http://localhost:${PORT}`);
  });
}

startServer();
