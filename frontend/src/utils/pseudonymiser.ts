/**
 * Intelligent Pseudonymisation & Entity De-identification Engine
 * Protects enterprise privacy by masking sensitive PII before model calls
 * and deanonymizing the assistant's responses locally.
 */

import { PseudonymMapping } from "../types/agent";

export const DEFAULT_INITIAL_MAPPINGS: PseudonymMapping[] = [
  {
    id: "map-1",
    original: "Acme Corporation",
    replacement: "[ORG_ALPHA]",
    category: "org",
    detectedAt: "Pre-configured",
    active: true,
  },
  {
    id: "map-2",
    original: "Dr. Sarah Jenkins",
    replacement: "[PERSON_LEAD_RESEARCHER]",
    category: "person",
    detectedAt: "Pre-configured",
    active: true,
  },
  {
    id: "map-3",
    original: "Helios Bio-Analytics AG",
    replacement: "[TARGET_COMPANY_HELIOS]",
    category: "org",
    detectedAt: "Pre-configured",
    active: true,
  },
  {
    id: "map-4",
    original: "$48,000,000",
    replacement: "[VALUATION_AMOUNT_A]",
    category: "financial",
    detectedAt: "Pre-configured",
    active: true,
  },
  {
    id: "map-5",
    original: "sarah.jenkins@acme-research.org",
    replacement: "[EMAIL_RESEARCH_DIRECTOR]",
    category: "contact",
    detectedAt: "Pre-configured",
    active: true,
  },
];

/**
 * Regex patterns for PII detection
 */
const EMAIL_REGEX = /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g;
const PHONE_REGEX = /\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/g;
const IBAN_REGEX = /\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b/g;
const CREDIT_CARD_REGEX = /\b(?:\d{4}[-\s]?){3}\d{4}\b/g;
const API_KEY_REGEX = /\b(?:sk[-_][a-zA-Z0-9]{20,}|AIzaSy[a-zA-Z0-9_-]{33}|ghp_[a-zA-Z0-9]{36})\b/g;
const CURRENCY_REGEX = /\b(?:\$|€|£|CHF)\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?(?:\s?(?:million|billion|M|B))?\b/gi;
const ORG_SUFFIX_REGEX = /\b([A-Z][a-zA-Z0-9'&]+(?:\s[A-Z][a-zA-Z0-9'&]+)*\s(?:Corp|Corporation|Inc|LLC|AG|GmbH|Ltd|Holdings|Capital|Technologies|Partners|Group))\b/g;

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

  // 3. Phones
  while ((match = PHONE_REGEX.exec(text)) !== null) {
    addIfNew(match[0], "contact", "PHONE");
  }

  // 4. Financial / IBAN / Card
  while ((match = IBAN_REGEX.exec(text)) !== null) {
    addIfNew(match[0], "financial", "IBAN");
  }
  while ((match = CREDIT_CARD_REGEX.exec(text)) !== null) {
    addIfNew(match[0], "financial", "CARD_NUM");
  }

  // 5. Large Currency amounts
  while ((match = CURRENCY_REGEX.exec(text)) !== null) {
    addIfNew(match[0], "financial", "AMOUNT");
  }

  // 6. Organization Suffixes
  while ((match = ORG_SUFFIX_REGEX.exec(text)) !== null) {
    addIfNew(match[1], "org", "ORG");
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
