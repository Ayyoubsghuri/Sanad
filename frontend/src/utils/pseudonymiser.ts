/**
 * Intelligent Pseudonymisation & Entity De-identification Engine
 * Protects enterprise privacy by masking sensitive PII before model calls
 * and deanonymizing the assistant's responses locally.
 */

import { PseudonymMapping } from "../types/agent";

/** Example rules shown on first use: a fictional Moroccan case (names, CIN, phone, amount, company). Users replace them. */
export const DEFAULT_INITIAL_MAPPINGS: PseudonymMapping[] = [
  { id: "ma-1", original: "Mohamed El Amrani", replacement: "[PERSONNE_1]", category: "person", detectedAt: "Example", active: true },
  { id: "ma-2", original: "Société Atlas Distribution SARL", replacement: "[SOCIETE_1]", category: "org", detectedAt: "Example", active: true },
  { id: "ma-3", original: "BK123456", replacement: "[CIN_1]", category: "secret", detectedAt: "Example", active: true },
  { id: "ma-4", original: "0612345678", replacement: "[TEL_1]", category: "contact", detectedAt: "Example", active: true },
  { id: "ma-5", original: "45 000 MAD", replacement: "[MONTANT_1]", category: "financial", detectedAt: "Example", active: true },
];

/** The example sentence of the "live masking" box. */
export const EXAMPLE_SANDBOX_TEXT =
  "La Société Atlas Distribution SARL a licencié M. Mohamed El Amrani (CIN BK123456) sans préavis après 6 ans de travail. Il réclame 45 000 MAD d'indemnités. Contact : 0612345678.";

/** The demo rules of the first prototype (an American company case): removed from what a browser saved back then. */
export const OLD_DEMO_ORIGINALS = ["Acme Corporation", "Dr. Sarah Jenkins", "Helios Bio-Analytics AG", "$48,000,000", "sarah.jenkins@acme-research.org"];

/**
 * Regex patterns for PII detection
 */
const EMAIL_REGEX = /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g;
const PHONE_REGEX = /\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/g;
const IBAN_REGEX = /\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b/g;
const CREDIT_CARD_REGEX = /\b(?:\d{4}[-\s]?){3}\d{4}\b/g;
const API_KEY_REGEX = /\b(?:sk[-_][a-zA-Z0-9]{20,}|AIzaSy[a-zA-Z0-9_-]{33}|ghp_[a-zA-Z0-9]{36})\b/g;
const CURRENCY_REGEX = /\b(?:\$|€|£|CHF)\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?(?:\s?(?:million|billion|M|B))?\b/gi;
const ORG_SUFFIX_REGEX = /\b([A-Z][a-zA-Z0-9'&]+(?:\s[A-Z][a-zA-Z0-9'&]+)*\s(?:Corp|Corporation|Inc|LLC|AG|GmbH|Ltd|Holdings|Capital|Technologies|Partners|Group|SARL|SARLAU|SA|SNC|SAS))\b/g;
// Morocco: national identity card (CIN: 1-2 letters + 4-6 digits), mobile/landline numbers, RIB (24 digits), amounts in dirhams
const CIN_REGEX = /\b[A-Z]{1,2}\d{4,6}\b/g;
const MA_PHONE_REGEX = /(?:\+212[\s.-]?|\b0)[5-7](?:[\s.-]?\d{2}){4}\b/g;
const RIB_REGEX = /\b\d{3}[\s-]?\d{3}[\s-]?\d{16}[\s-]?\d{2}\b/g;
const MAD_REGEX = /\b\d{1,3}(?:[\s.,]\d{3})*(?:[.,]\d+)?\s?(?:MAD|DH|Dhs?|dirhams?|درهم)(?![A-Za-z])/gi;

/**
 * Scans text and detects unmapped sensitive entities
 */
export function scanAndDetectEntities(
  text: string,
  existingMappings: PseudonymMapping[]
): PseudonymMapping[] {
  if (!text || text.trim().length === 0) return [];

  const existingOriginals = new Set(
    existingMappings.map((m) => m.original.toLowerCase())
  );
  const detected: PseudonymMapping[] = [];

  function addIfNew(original: string, category: PseudonymMapping["category"], prefix: string) {
    const trimmed = original.trim();
    if (!trimmed || trimmed.length < 3) return;
    if (existingOriginals.has(trimmed.toLowerCase())) return;
    if (detected.some((d) => d.original.includes(trimmed))) return; // part of something already found (a card-like run inside a RIB)
    existingOriginals.add(trimmed.toLowerCase());

    const idx = existingMappings.filter((m) => m.category === category).length + detected.filter((m) => m.category === category).length + 1;
    detected.push({
      id: `map-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      original: trimmed,
      replacement: `[${prefix}_${idx}]`,
      category,
      detectedAt: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      active: true,
    });
  }

  // 1. API Keys & Secrets
  let match: RegExpExecArray | null;
  while ((match = API_KEY_REGEX.exec(text)) !== null) {
    addIfNew(match[0], "secret", "SECRET_KEY");
  }

  // 2. Emails
  while ((match = EMAIL_REGEX.exec(text)) !== null) {
    addIfNew(match[0], "contact", "EMAIL");
  }

  // 3. Phones (Moroccan formats first)
  while ((match = MA_PHONE_REGEX.exec(text)) !== null) {
    addIfNew(match[0], "contact", "TEL");
  }
  while ((match = PHONE_REGEX.exec(text)) !== null) {
    addIfNew(match[0], "contact", "TEL");
  }

  // 3b. Moroccan identity card numbers (CIN)
  while ((match = CIN_REGEX.exec(text)) !== null) {
    addIfNew(match[0], "secret", "CIN");
  }

  // 4. Financial / RIB / IBAN / Card
  while ((match = RIB_REGEX.exec(text)) !== null) {
    addIfNew(match[0], "financial", "RIB");
  }
  while ((match = IBAN_REGEX.exec(text)) !== null) {
    addIfNew(match[0], "financial", "IBAN");
  }
  while ((match = CREDIT_CARD_REGEX.exec(text)) !== null) {
    addIfNew(match[0], "financial", "CARD_NUM");
  }

  // 5. Amounts (dirhams first)
  while ((match = MAD_REGEX.exec(text)) !== null) {
    addIfNew(match[0], "financial", "MONTANT");
  }
  while ((match = CURRENCY_REGEX.exec(text)) !== null) {
    addIfNew(match[0], "financial", "MONTANT");
  }

  // 6. Organization Suffixes
  while ((match = ORG_SUFFIX_REGEX.exec(text)) !== null) {
    addIfNew(match[1], "org", "SOCIETE");
  }

  return detected;
}

/**
 * Replaces original entities with pseudonym tokens
 */
export function applyPseudonyms(
  text: string,
  mappings: PseudonymMapping[]
): { text: string; replacedCount: number; appliedMappings: PseudonymMapping[] } {
  if (!text) return { text: "", replacedCount: 0, appliedMappings: [] };

  let result = text;
  let count = 0;
  const applied: PseudonymMapping[] = [];

  // Sort by length descending to prevent sub-string overlap
  const activeMappings = mappings
    .filter((m) => m.active && m.original.trim().length > 0)
    .sort((a, b) => b.original.length - a.original.length);

  for (const m of activeMappings) {
    // Escape regex special chars
    const escaped = m.original.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const regex = new RegExp(escaped, "gi");
    if (regex.test(result)) {
      result = result.replace(regex, m.replacement);
      count++;
      applied.push(m);
    }
  }

  return { text: result, replacedCount: count, appliedMappings: applied };
}

/**
 * Deanonymizes text locally: replaces pseudonyms back to real names
 */
export function restoreRealEntities(
  text: string,
  mappings: PseudonymMapping[]
): string {
  if (!text) return "";

  let result = text;
  const activeMappings = mappings.filter((m) => m.active);

  for (const m of activeMappings) {
    const escapedReplacement = m.replacement.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const regex = new RegExp(escapedReplacement, "g");
    result = result.replace(regex, m.original);
  }

  return result;
}

/**
 * Approximates token count for text payload
 */
export function estimateTokenCount(text: string): number {
  if (!text) return 0;
  // ~4 characters per token average in English & code
  return Math.ceil(text.length / 4);
}
