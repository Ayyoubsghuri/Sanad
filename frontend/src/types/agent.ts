export enum ThemeId {
  Stone = "stone",
  Moss = "moss",
  Mist = "mist",
  Clay = "clay",
  Dusk = "dusk",
  Sakura = "sakura",
  Ink = "ink",
  Emerald = "emerald",
  Ember = "ember",
  Mono = "mono",
}

export enum LayoutDensity {
  Comfy = "comfy",
  Compact = "compact",
}

export enum ArtifactKind {
  Html = "html",
  Svg = "svg",
  Markdown = "markdown",
  Code = "code",
  Document = "document",
}

export enum StepStatus {
  Running = "running",
  Completed = "completed",
}

export interface AgentStep {
  id: string;
  kind: "thinking" | "search" | "artifact" | "analysis" | "memory" | "evidence";
  title: string;
  detail: string;
  status: StepStatus;
  durationMs?: number;
}

export interface PdfSnippet {
  id: string;
  page: string | number;
  totalPages?: number;
  sectionTitle?: string;
  highlightedSnippet: string;
  contextBefore?: string;
  contextAfter?: string;
  relevanceExplanation?: string;
  /** set when the snippet is a whole article of the law pack: lets the viewer show the real page of the official PDF */
  provisionId?: string;
  asOf?: string;
  pageStart?: number;
  pageEnd?: number;
  hasPdf?: boolean;
}

export interface DocumentMeta {
  filename: string;
  authorOrSource?: string;
  totalPages?: number;
  snippets?: PdfSnippet[];
  // Backwards compatibility / single snippet fields
  page?: string | number;
  sectionTitle?: string;
  highlightedSnippet?: string;
  contextBefore?: string;
  contextAfter?: string;
  relevanceExplanation?: string;
}

export interface ArtifactItem {
  id: string;
  title: string;
  kind: ArtifactKind;
  language: string;
  summary?: string;
  content: string;
  documentMeta?: DocumentMeta;
  createdAt: string;
}

export interface GroundingSource {
  title: string;
  uri: string;
}

export interface AttachmentItem {
  id: string;
  name: string;
  mimeType: string;
  sizeBytes: number;
  dataUrl?: string;
  textContent?: string;
  source?: "vault"; // plaintext from the encrypted vault: never persisted to localStorage
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  attachments?: AttachmentItem[];
  steps?: AgentStep[];
  artifacts?: ArtifactItem[];
  sources?: GroundingSource[];
  error?: string;
  isStreaming?: boolean;
}

export interface ChatThread {
  id: string;
  title: string;
  updatedAt: string;
  starred?: boolean;
  messages: ChatMessage[];
}

export interface ProjectDoc {
  id: string;
  title: string;
  content: string;
}

export interface PseudonymMapping {
  id: string;
  original: string;
  replacement: string;
  category: "person" | "org" | "contact" | "financial" | "secret" | "custom";
  detectedAt?: string;
  active: boolean;
}

export interface VaultItem {
  id: string;
  title: string;
  category: "dossier" | "contract" | "identity" | "notes";
  encryptedData: string; // base64 package { salt, iv, ciphertext }
  previewSnippet: string; // safe non-sensitive summary
  updatedAt: string;
  isCustom?: boolean;
}

export interface WorkspaceSettings {
  theme: ThemeId;
  darkMode: boolean;
  headingScale: number; // 85 to 120 (%)
  bodyScale: number; // 85 to 115 (%)
  density: LayoutDensity;
  showContinueCard: boolean;
  showExplorePrompts: boolean;
  showRecentSidebar: boolean;
  thinkingMode: boolean;
  thinkingBudget?: number; // token budget for reasoning (1024 - 32768)
  enableWebSearch: boolean;
  systemInstruction: string;
  autoPseudonymise: boolean;
  alwaysPreviewBeforeSend: boolean;
  restorePseudonymsInReplies: boolean;
  // Moroccan Legal RAG Blueprint Settings
  operatingMode: "offline" | "hybrid" | "cloud-assisted";
  audienceMode: "citizen" | "professional";
  asOfDate: string; // ISO date YYYY-MM-DD (e.g. 2026-10-24)
  strictMode: boolean; // For sensitive criminal/family matters
}

export type OperatingMode = "offline" | "hybrid" | "cloud-assisted";
export type TrustLevel = "verified" | "single_source" | "derived" | "disputed" | "draft";
export type ContestedStatus = "active" | "active_contested" | "repealed" | "not_yet_in_force";
export type ImplementingStatus = "self_executing" | "issued" | "pending" | "unknown";

export interface LawStatusMeta {
  lawNumber: string;
  lawTitle: string;
  titleAr?: string;
  dahirNumber: string;
  boNumber: string;
  boDate: string;
  validFrom: string;
  validTo?: string | null;
  trustLevel: TrustLevel;
  implementingStatus: ImplementingStatus;
  contestedStatus?: ContestedStatus;
  sourceUrl?: string;
  packBuildDate?: string;
}

export interface BilingualArticle {
  id: string;
  provisionId: string;
  instrumentId?: string;
  lawNumber: string;
  lawTitle: string;
  titleAr?: string;
  articleNumber: string;
  path: string;
  validFrom: string;
  validTo?: string | null;
  textAr: string;
  textFr: string;
  controllingLang: "ar" | "fr";
  trustLevel: TrustLevel;
  dahirNumber: string;
  boNumber: string;
  boDate: string;
  implementingStatus: ImplementingStatus;
  contestedStatus?: ContestedStatus;
  sourceUrl?: string;
  transitionalRule?: string;
}

export interface VerificationReport {
  citationExists: boolean;
  quoteMatches: boolean;
  placeholdersIntact: boolean;
  versionValid: boolean;
  noStrayNumbers: boolean;
  claimSupportRate: number; // 0-100%
  overallStatus: "passed" | "retried" | "abstained";
  abstainReason?: string;
}

export interface AuditTraceRecord {
  id: string;
  timestamp: string;
  rawQuestionLength: number;
  pseudonymisedQuery: string;
  asOfDate: string;
  operatingMode: OperatingMode;
  retrievedChunkIds: string[];
  verification: VerificationReport;
  outboundPayloadJson: string;
  claimsCount: number;
  latencyMs: number;
}

export interface ConcordanceRule {
  id: string;
  topic: string;
  oldLaw: string;
  oldArticle: string;
  newLaw: string;
  newArticle: string;
  effectiveDate: string;
  transitionalRuleText: string;
  oldSummary: string;
  newSummary: string;
  keyChange: string;
}

export interface CitizenSituation {
  id: string;
  title: string;
  titleAr: string;
  category: "employment" | "housing" | "family" | "inheritance" | "commercial" | "dispute" | "traffic";
  description: string;
  typicalQuestions: string[];
  keyArticles: {
    law: string;
    article: string;
    summary: string;
  }[];
  documentsToBring: string[];
  practicalNextSteps: string[];
}
