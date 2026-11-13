import {
  Document,
  Packer,
  Paragraph,
  TextRun,
  Table,
  TableRow,
  TableCell,
  WidthType,
  BorderStyle,
  AlignmentType,
  ShadingType,
} from "docx";
import { PdfSnippet, DocumentMeta } from "../types/agent";


const AR_RX = /[\u0600-\u06FF]/;
const AR_FONT = "Arial";

/** Text runs for one text; Arabic gets right-to-left runs, an Arabic font, no italics, and real line breaks. */
function textRuns(text: string, o: { font: ReturnType<typeof makeFont>; size: number; bold?: boolean; italics?: boolean; color: string }): TextRun[] {
  const ar = AR_RX.test(text);
  return text.split("\n").map(
    (line, i) =>
      new TextRun({
        text: line,
        break: i > 0 ? 1 : undefined,
        font: ar ? { name: AR_FONT, ascii: AR_FONT, hAnsi: AR_FONT, cs: AR_FONT } : o.font,
        size: o.size,
        bold: o.bold,
        italics: ar ? false : o.italics,
        color: o.color,
        rightToLeft: ar,
      })
  );
}
const isAr = (t: string) => AR_RX.test(t);

export interface DocxThemeFontOptions {
  serifFont?: string; // e.g. "Lora" or "Cormorant Garamond"
  sansFont?: string;  // e.g. "Plus Jakarta Sans"
  monoFont?: string;  // e.g. "JetBrains Mono"
}

/**
 * Creates font options with graceful system fallbacks (Georgia, Calibri, Consolas)
 * so Word, Google Docs, and Pages render the exact font style.
 */
function makeFont(primary: string, fallback: string) {
  return {
    name: primary,
    ascii: primary,
    hAnsi: primary,
    cs: fallback,
  };
}

/**
 * Evidence brief as a clean .docx: plain paragraphs (no nested tables), right-to-left and
 * Arabic labels when the evidence is Arabic.
 */
export async function createSnippetDocxBlob(
  title: string,
  docMeta: DocumentMeta | undefined,
  snippets: PdfSnippet[],
  uniquePages: string[],
  fontOptions: DocxThemeFontOptions = {}
): Promise<Blob> {
  const latin = makeFont(fontOptions.sansFont || "Calibri", "Calibri");
  const arabicDoc = snippets.some((s) => isAr(s.highlightedSnippet));
  const L = arabicDoc
    ? {
        brief: "ملف الأدلة",
        source: "المصدر",
        pages: "الصفحات",
        passage: "المقتطف",
        of: "من",
        page: "الصفحة",
        excerpt: "النص الحرفي من الجريدة الرسمية",
        verification: "التحقق",
        footer: "معلومات للاطلاع فقط وليست استشارة قانونية.",
      }
    : {
        brief: "Evidence brief",
        source: "Source",
        pages: "Pages",
        passage: "Passage",
        of: "of",
        page: "Page",
        excerpt: "Verbatim text from the official bulletin",
        verification: "Verification",
        footer: "Information only, not legal advice.",
      };
  const fileName = docMeta?.filename || title || "Document";
  const COLOR = { ink: "1F2937", muted: "6B7280", accent: "7C2D12", rule: "D6CFC4", quoteBg: "F7F3EC" };
  const align = arabicDoc ? AlignmentType.RIGHT : AlignmentType.LEFT;

  const p = (
    text: string,
    o: { size: number; bold?: boolean; italics?: boolean; color?: string; before?: number; after?: number; shade?: string; bar?: boolean; keepNext?: boolean }
  ) =>
    new Paragraph({
      bidirectional: arabicDoc || isAr(text),
      alignment: arabicDoc || isAr(text) ? AlignmentType.RIGHT : align,
      keepNext: o.keepNext,
      spacing: { before: o.before ?? 0, after: o.after ?? 100, line: 320 },
      shading: o.shade ? { type: ShadingType.CLEAR, color: "auto", fill: o.shade } : undefined,
      border: o.bar
        ? { [arabicDoc ? "right" : "left"]: { style: BorderStyle.SINGLE, size: 24, color: COLOR.accent, space: 8 } }
        : undefined,
      indent: o.bar ? { left: 200, right: 200 } : undefined,
      children: textRuns(text, { font: latin, size: o.size, bold: o.bold, italics: o.italics, color: o.color || COLOR.ink }),
    });

  const rule = () =>
    new Paragraph({
      spacing: { before: 200, after: 200 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: COLOR.rule, space: 1 } },
      children: [],
    });

  const children: Paragraph[] = [];
  children.push(p(L.brief, { size: 20, bold: true, color: COLOR.accent, after: 60 }));
  children.push(p(fileName, { size: 36, bold: true, after: 60 }));
  const meta = [
    docMeta?.authorOrSource ? `${L.source}: ${docMeta.authorOrSource}` : "",
    uniquePages.length ? `${L.pages}: ${uniquePages.join(", ")}` : "",
  ]
    .filter(Boolean)
    .join("   ·   ");
  if (meta) children.push(p(meta, { size: 21, color: COLOR.muted, after: 0 }));
  children.push(rule());

  snippets.forEach((sn, i) => {
    const total = sn.totalPages || docMeta?.totalPages;
    children.push(
      p(`${L.passage} ${i + 1} ${L.of} ${snippets.length}  ·  ${L.page} ${sn.page}${total ? ` ${L.of} ${total}` : ""}`, {
        size: 20,
        bold: true,
        color: COLOR.accent,
        after: 60,
        keepNext: true,
      })
    );
    if (sn.sectionTitle) children.push(p(sn.sectionTitle, { size: 26, bold: true, after: 140, keepNext: true }));
    if (sn.contextBefore) children.push(p(sn.contextBefore, { size: 22, color: COLOR.muted, after: 140 }));
    children.push(p(L.excerpt, { size: 18, bold: true, color: COLOR.muted, after: 40, keepNext: true }));
    children.push(p(sn.highlightedSnippet, { size: 28, shade: COLOR.quoteBg, bar: true, before: 40, after: 160 }));
    if (sn.contextAfter) children.push(p(sn.contextAfter, { size: 22, color: COLOR.muted, after: 140 }));
    if (sn.relevanceExplanation) {
      children.push(p(L.verification, { size: 18, bold: true, color: COLOR.muted, after: 40, keepNext: true }));
      children.push(p(sn.relevanceExplanation, { size: 23, after: 100 }));
    }
    children.push(rule());
  });
  children.push(p(L.footer, { size: 18, color: COLOR.muted, after: 0 }));

  const doc = new Document({
    styles: {
      default: {
        document: { run: { font: latin, size: 22, color: COLOR.ink } },
      },
    },
    sections: [
      {
        properties: { page: { margin: { top: 1200, bottom: 1200, left: 1300, right: 1300 } } },
        children,
      },
    ],
  });
  return await Packer.toBlob(doc);
}

/**
 * Creates a genuine Office Open XML (.docx) binary Blob for generic text/code artifacts,
 * applying the active editorial typography.
 */
export async function createGenericDocxBlob(
  title: string,
  content: string,
  fontOptions: DocxThemeFontOptions = {}
): Promise<Blob> {
  const serifName = fontOptions.serifFont || "Lora";
  const monoName = fontOptions.monoFont || "JetBrains Mono";
  const sansName = fontOptions.sansFont || "Plus Jakarta Sans";

  const serifFont = makeFont(serifName, "Georgia");
  const monoFont = makeFont(monoName, "Consolas");
  const sansFont = makeFont(sansName, "Calibri");

  const lines = content.split("\n");

  const doc = new Document({
    styles: {
      default: {
        document: {
          run: {
            font: sansFont,
            size: 20,
            color: "4A2B24",
          },
        },
      },
    },
    sections: [
      {
        properties: {
          page: {
            margin: {
              top: 1440,
              bottom: 1440,
              left: 1440,
              right: 1440,
            },
          },
        },
        children: [
          new Paragraph({
            spacing: { before: 0, after: 200 },
            children: [
              new TextRun({
                text: title,
                font: serifFont,
                size: 36, // 18pt
                bold: true,
                color: "59201A",
              }),
            ],
          }),
          new Table({
            width: { size: 100, type: WidthType.PERCENTAGE },
            rows: [
              new TableRow({
                children: [
                  new TableCell({
                    width: { size: 100, type: WidthType.PERCENTAGE },
                    shading: { fill: "F9F5EE" },
                    borders: {
                      top: {
                        style: BorderStyle.SINGLE,
                        size: 8,
                        color: "DFD4C6",
                      },
                      bottom: {
                        style: BorderStyle.SINGLE,
                        size: 8,
                        color: "DFD4C6",
                      },
                      left: {
                        style: BorderStyle.SINGLE,
                        size: 8,
                        color: "DFD4C6",
                      },
                      right: {
                        style: BorderStyle.SINGLE,
                        size: 8,
                        color: "DFD4C6",
                      },
                    },
                    margins: { top: 200, bottom: 200, left: 240, right: 240 },
                    children: lines.map(
                      (line) =>
                        new Paragraph({
                          spacing: { before: 20, after: 20 },
                          children: [
                            new TextRun({
                              text: line || " ",
                              font: monoFont,
                              size: 20, // 10pt
                              color: "38241F",
                            }),
                          ],
                        })
                    ),
                  }),
                ],
              }),
            ],
          }),
        ],
      },
    ],
  });

  return await Packer.toBlob(doc);
}
