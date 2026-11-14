import { ChatThread, ProjectDoc } from "../types/agent";

// A new installation starts empty: no demo sessions, no demo project documents.
export const INITIAL_PROJECT_DOCS: ProjectDoc[] = [];
export const SEED_THREADS: ChatThread[] = [];

/** Demo sessions and documents shipped by earlier versions: removed from what a browser saved back then. */
export const REMOVED_DEMO_THREAD_IDS = ["thread-pdf-evidence-showcase", "thread-forest-rain", "thread-cohort-nrr"];
export const REMOVED_DEMO_DOC_IDS = ["doc-brand-voice"];

export interface StarterPrompt {
  id: string;
  category: string;
  title: string;
  prompt: string;
}

export const STARTER_PROMPTS: StarterPrompt[] = [
  {
    id: "sp-labour-dismissal",
    category: "Labour law",
    title: "Dismissal and severance pay",
    prompt:
      "My employer dismissed me after 6 years without written notice. What does the Labour Code say about notice, severance pay and damages, and which articles apply?",
  },
  {
    id: "sp-family-nafaqa",
    category: "Family law",
    title: "Divorce and child maintenance",
    prompt:
      "What does the Family Code (Moudawana) provide for child maintenance (nafaqa) and custody after a divorce? Cite the articles.",
  },
  {
    id: "sp-rent-eviction",
    category: "Housing",
    title: "Rent arrears and eviction",
    prompt:
      "A residential tenant has not paid rent for three months. What procedure must the landlord follow to recover the rent and end the lease, and what are the deadlines?",
  },
  {
    id: "sp-cheque",
    category: "Commercial law",
    title: "Cheque without provision",
    prompt:
      "What are the penalties and the regularisation options for a cheque without provision under the Commercial Code?",
  },
];
