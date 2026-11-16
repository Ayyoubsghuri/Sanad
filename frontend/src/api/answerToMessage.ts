import { tr } from "../i18n";
import { CHAMBER, OUTCOME, T, answerLang, failureText, noteText, type ALang } from "./answerText";
import { ArtifactKind, type ArtifactItem, type GroundingSource, type PdfSnippet } from "../types/agent";
import type { AnswerRulings, NextSteps, QueryAnswer, SourceEntry } from "./legalrag";

const STATUS_LABEL: Record<string, string> = {
  answered: "Verified answer",
  partial: "Partially verified answer",
  extractive_only: "Could not verify an answer: quoted articles only",
  abstained: "Not answered",
};

function srcUri(s: SourceEntry): string {
  if (s.source && typeof s.source === "object" && s.source.url) return s.source.url;
  return `legalrag://${s.id}`;
}

/** Similar Court of Cassation rulings: a block of its own after the law, never numbered like the law's sources. */
export function rulingsBlock(r: AnswerRulings | null | undefined, L: ALang): string {
  if (!r?.items?.length) return "";
  const ltr = (x: string) => `\u2066${x.replace(/-/g, "\u2011")}\u2069`;  // numbers and dates stay left-to-right inside Arabic
  const counts = Object.entries(r.by_outcome).sort((x, y) => y[1] - x[1])
    .map(([o, n]) => `${n} ${(OUTCOME[o] ?? OUTCOME.other)[L]}`).join(" · ");
  const lines = r.items.map((x) => {
    const head = [x.number ? `${T(L, "ruling")} ${ltr(x.number)}` : T(L, "ruling"), x.date ? ltr(x.date) : "",
      x.chamber && CHAMBER[x.chamber] ? (L === "ar" ? `${T(L, "chamber")} ${CHAMBER[x.chamber][L]}` : `${T(L, "chamber")} ${CHAMBER[x.chamber][L]}`) : ""]
      .filter(Boolean).join(" · ");
    const outcome = (OUTCOME[x.outcome || "unknown"] ?? OUTCOME.other)[L];
    const about = (x.principle || x.keywords || "").replace(/\s+/g, " ").trim();
    const link = x.source_url ? ` [${T(L, "pdf")}](${x.source_url})` : "";
    return `- **${head}** — ${outcome}${link}${about ? `\n  > ${about}` : ""}`;
  });
  return `**${T(L, "rulings")}**\n\n_${T(L, "rulingsNote")}._\n\n_${T(L, "rulingsAmong").replace("{0}", String(r.similar))}: ${counts}._\n\n${lines.join("\n")}`;
}

/** "What you can do now": the last part of an answer about a personal situation. [n] are the numbers of the answer's sources. */
export function nextStepsBlock(n: NextSteps | null | undefined, L: ALang, idx: Map<string, number>): string {
  if (!n?.steps?.length) return "";
  const lines = n.steps.map((s, i) => {
    const refs = (s.sources ?? []).map((id) => idx.get(id)).filter(Boolean).map((k) => `[${k}]`).join("");
    const extra = [
      s.deadline ? `   - **${T(L, "deadline")}:** ${s.deadline}` : "",
      s.where ? `   - **${T(L, "where")}:** ${s.where}` : "",
      s.documents?.length ? `   - **${T(L, "documents")}:** ${s.documents.join(L === "ar" ? "، " : ", ")}` : "",
    ].filter(Boolean).join("\n");
    return `${i + 1}. **${s.title}** ${refs}\n   ${s.text.replace(/\n+/g, " ")}${extra ? `\n${extra}` : ""}`;
  });
  const pro = n.professional ? `\n\n**${T(L, "whenPro")}:** ${n.professional}` : "";
  return `**${T(L, "nextSteps")}**\n\n_${T(L, "nextNote")}._\n\n${lines.join("\n")}${pro}`;
}

/** Turns a backend answer into markdown + grounding sources for the chat bubble. */
/** PDF evidence: the articles the answer rests on, each WHOLE (never the retrieval chunk), with the page of the official bulletin.
 *  Articles the verified claims cite come first; if nothing is cited (quoted-articles-only answers) every retrieved article is shown. */
export function evidenceArtifact(a: QueryAnswer): ArtifactItem | null {
  const sources = a.sources ?? [];
  if (!sources.length) return null;
  const cited = new Map<string, string[]>();
  for (const c of a.claims ?? []) for (const id of c.sources) cited.set(id, [...(cited.get(id) ?? []), c.text]);
  const ordered = [...sources].sort((x, y) => Number(cited.has(y.id)) - Number(cited.has(x.id)) || (y.relevance ?? 0) - (x.relevance ?? 0));
  const chosen = ordered.filter((s) => cited.has(s.id));
  const list = chosen.length ? chosen : ordered;
  const seen = new Set<string>();
  const snippets: PdfSnippet[] = [];
  for (const s of list) {
    const key = s.kind === "other_text" ? `${s.provision_id}#${s.chunk_id ?? s.id}` : (s.provision_id ?? s.id);
    if (seen.has(key)) continue; // several chunks of one article = one snippet
    seen.add(key);
    const supports = cited.get(s.id);
    snippets.push({
      id: `ev-${key}`,
      page: s.pages ? (s.pages.start === s.pages.end ? s.pages.start : `${s.pages.start}–${s.pages.end}`) : "—",
      sectionTitle: `${s.law}, ${s.article}${s.bo?.number ? ` · BO ${s.bo.number}` : ""}`,
      highlightedSnippet: s.text,
      relevanceExplanation: supports?.length ? supports[0] : undefined,
      provisionId: s.provision_id,
      asOf: a.as_of,
      pageStart: s.pages?.start,
      pageEnd: s.pages?.end,
      hasPdf: s.has_pdf,
    });
    if (snippets.length >= 8) break;
  }
  const first = list[0];
  return {
    id: `evidence-${Date.now()}`,
    title: `Preuves · ${first.law}${snippets.length > 1 ? ` (+${snippets.length - 1})` : ""}`,
    kind: ArtifactKind.Document,
    language: "ar",
    summary: "Articles complets cités, avec la page du Bulletin Officiel",
    content: snippets.map((x) => `${x.sectionTitle}\n${x.highlightedSnippet}`).join("\n\n"),
    documentMeta: { filename: first.bo?.number ? `BO_${first.bo.number}_Ar.pdf` : "Bulletin Officiel", authorOrSource: "SGG", snippets },
    createdAt: new Date().toISOString(),
  };
}

export function answerToMessage(a: QueryAnswer): { content: string; sources: GroundingSource[]; artifacts: ArtifactItem[] } {
  const L = answerLang(a.language);
  const sources = a.sources ?? [];
  const idx = new Map(sources.map((s, i) => [s.id, i + 1]));
  const parts: string[] = [];

  if (a.status === "needs_clarification") {
    parts.push(a.clarifying_question || T(L, "oneMore"));
  } else if (a.status === "needs_input") {
    parts.push(`**${a.needs_input?.message ?? T(L, "moreInput")}**`);
    if (a.needs_input?.missing?.length) parts.push(a.needs_input.missing.map((m) => `- ${m}`).join("\n"));
  } else if (a.status === "review_required") {
    parts.push(`**${T(L, "review")}** ${a.reason ?? ""}`);
    if (a.pseudonymised_text) parts.push(`> ${a.pseudonymised_text}`);
  } else if (a.status === "unavailable") {
    parts.push(`**${T(L, "packUnavailable")}** ${a.reason ?? ""}`);
  } else {
    if (a.status === "partial" || a.status === "extractive_only" || a.status === "abstained") parts.push(`_${T(L, a.status)}_`);
    if (a.status === "extractive_only" || a.status === "partial") {
      // Say WHY nothing could be verified (the model's claims are re-checked in code): the first reasons, and any model/provider problem.
      const v = a.verification as { failures?: string[]; claims_total?: number } | undefined;
      const why = [...(a.fallbacks ?? []).map((x) => noteText(String(x), L)), ...(v?.failures ?? []).map((x) => failureText(String(x), L))].slice(0, 3).map((x) => x.slice(0, 220));
      if (why.length) parts.push(`_${T(L, "why")}: ` + why.join(" · ") + "_");
      if (a.status === "extractive_only" && (v?.failures ?? []).some((f) => /citation_exists|no supporting citation/i.test(String(f)))) {
        parts.push(`**${T(L, "noAnswerHere")}** ${T(L, "maybeMissing")}`);
      }
    }
    // the date is isolated left-to-right: inside Arabic text 2026-11-15 would otherwise show as 15-11-2026
    if (a.as_of) parts.push(`_${T(L, "lawAsOf")} \u2066${a.as_of.replace(/-/g, "\u2011")}\u2069${a.as_of_assumption ? `: ${noteText(a.as_of_assumption, L)}` : ""}_`);
    for (const c of a.claims ?? []) {
      const refs = c.sources.map((id) => idx.get(id)).filter(Boolean).map((n) => `[${n}]`).join("");
      parts.push(`${c.text} ${refs}`.trim());
    }
    if (a.abstain) {
      parts.push(`**${a.abstain.reason}**`);
      if (a.abstain.bring_to_professional?.length)
        parts.push(T(L, "bring") + "\n" + a.abstain.bring_to_professional.map((b) => `- ${b}`).join("\n"));
    }
    const calcs = (a.calculators ?? []).filter((c) => c.status === "ok");
    if (calcs.length) parts.push(`**${T(L, "calculations")}**\n` + calcs.map((c) => `- ${c.tool}: \`${JSON.stringify(c)}\``).join("\n"));
    if (sources.length) {
      // Only the articles the verified claims rest on are listed here, with the numbers used in the answer ([5] stays 5).
      // Everything else that was retrieved is in the "Preuves" card; with no cited source (quoted-articles-only answers) the first ones are listed.
      const citedIds = new Set((a.claims ?? []).flatMap((c) => c.sources));
      const pick = sources.map((s, i) => ({ s, n: i + 1 })).filter(({ s }) => citedIds.has(s.id));
      const byRelevance = sources.map((s, i) => ({ s, n: i + 1 })).sort((x, y) => (y.s.relevance ?? 0) - (x.s.relevance ?? 0));
      const shown = pick.length ? pick : byRelevance.slice(0, 5);
      const rest = sources.length - shown.length;
      parts.push(
        `**${T(L, "sources")}**\n` +
          shown
            .map(({ s, n }) => {
              const bo = s.bo?.number ? ` \u2066(BO ${s.bo.number}${s.bo.date ? `, ${s.bo.date.replace(/-/g, "\u2011")}` : ""})\u2069` : ""; // left-to-right inside Arabic, the date never split
              const warn = s.in_force_on_as_of === false ? ` ⚠ ${T(L, "notInForce")}` : s.contested ? ` ⚠ ${T(L, "contested")}` : "";
              const text = s.text.length > 700 ? `${s.text.slice(0, 700).replace(/\n+/g, " ")}…` : s.text.replace(/\n+/g, " ");
              return `${n}. **${s.law}, ${s.article}**${bo}${warn}\n   > ${text}`;
            })
            .join("\n") +
          (rest > 0 ? `\n\n_+${rest} ${T(L, "more")}_` : "")
      );
    }
  }
  const rul = rulingsBlock(a.rulings, L);
  if (rul) parts.push(rul);
  const todo = nextStepsBlock(a.next_steps, L, idx);
  if (todo) parts.push(todo);
  if (a.research?.rounds?.length) {
    const more = a.research.rounds.reduce((n, r) => n + (r.added?.length ?? 0), 0);
    const tried = a.research.rounds.flatMap((r) => r.queries ?? []);
    parts.push(`_${T(L, "deep")}: ${a.research.rounds.length} ${T(L, "rounds")}, ${more} ${T(L, "morePassages")}${tried.length ? ` — ${tried.map((q) => `«${q}»`).join(" ")}` : ""}_`);
  }
  if (a.notices?.length) parts.push(a.notices.map((n) => `_${noteText(n, L)}_`).join("\n\n"));

  return {
    content: parts.join("\n\n"),
    sources: (() => {
      // the chips under the answer: real articles only (no preamble/annex pieces), one per article, the cited ones first, at most 6
      const cited = new Set((a.claims ?? []).flatMap((c) => c.sources));
      const seen = new Set<string>();
      return [...sources]
        .filter((s) => s.kind !== "other_text")
        .sort((x, y) => Number(cited.has(y.id)) - Number(cited.has(x.id)) || (y.relevance ?? 0) - (x.relevance ?? 0))
        .filter((s) => { const k = `${s.law}|${s.article}`; if (seen.has(k)) return false; seen.add(k); return true; })
        .slice(0, 6)
        .map((s) => ({ title: `${s.law}, ${s.article}`, uri: srcUri(s) }));
    })(),
    artifacts: ((): ArtifactItem[] => { const e = evidenceArtifact(a); return e ? [e] : []; })(),
  };
}
