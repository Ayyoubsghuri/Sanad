import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type Lang = "en" | "fr" | "ar";
export const LANGS: { id: Lang; label: string; dir: "ltr" | "rtl" }[] = [
  { id: "en", label: "English", dir: "ltr" },
  { id: "fr", label: "Français", dir: "ltr" },
  { id: "ar", label: "العربية", dir: "rtl" },
];
const STORAGE_KEY = "sanad_language_v1";

import { DICT } from "./dict";

type Dict = Record<string, string>;

const en: Dict = {
  "lang.title": "Language",
  "greet.morning": "Good morning",
  "greet.afternoon": "Good afternoon",
  "greet.evening": "Good evening",
  "home.hero": "What legal question can I help you with today?",
  "home.explore": "Example questions",
  "sidebar.collapse": "Collapse sidebar",
  "sidebar.new": "New session",
  "sidebar.filter": "Filter sessions...",
  "sidebar.tab.all": "Recent",
  "sidebar.tab.starred": "Starred",
  "sidebar.tab.artifacts": "Artifacts",
  "sidebar.noArtifacts": "No artifacts match your filter yet. Ask Sanad to build a chart, UI mockup, or report.",
  "sidebar.historyHidden": "Recent thread history is hidden in Appearance settings.",
  "sidebar.noStarred": "Star important threads to keep them pinned here.",
  "sidebar.noConv": "No conversations found.",
  "sidebar.delete": "Delete session",
  "sidebar.pseudonymiser": "Pseudonymiser",
  "sidebar.rules": "rules",
  "sidebar.vault": "Encrypted vault",
  "sidebar.knowledge": "Project knowledge",
  "sidebar.appearance": "Appearance & palette",
  "mode.offline": "Offline",
  "mode.hybrid": "Hybrid",
  "mode.cloud": "Cloud",
  "aud.citizen": "Citizen",
  "aud.pro": "Pro Lawyer",
  "tools.title": "Legal tools",
  "tools.calc": "Simulators & Calculators",
  "tools.calc.sub": "Severance, Iddah, Mut'ah, salary",
  "tools.situations": "Citizen Situations",
  "tools.situations.sub": "Employee, Divorce, Inheritance",
  "tools.statutes": "Texts & Official Bulletin",
  "tools.statutes.sub": "Labour Code, Moudawana",
  "tools.concordance": "Concordance & Date",
  "tools.audit": "Audit Trace & NLI",
  "tools.audit.sub": "Fact check & sources",
  "tools.consult": "Consultation File",
  "tools.consult.sub": "Summary for a lawyer",
  "composer.placeholder": "Reply to Sanad or ask to explore an artifact...",
  "composer.attach": "Attach images, documents, or data",
  "composer.thinking": "Thinking",
  "composer.stop": "Stop generating",
  "composer.send": "Send message",
  "composer.vault": "Open Encrypted Vault (AES-256)",
  "composer.preview": "Inspect prompt payload & privacy (Send Preview)",
  "think.title": "Extended Thinking",
  "think.sub": "Claude-style step reasoning",
  "think.desc": "Allows Sanad to reason deeply before responding, cross-examining evidence, calculating data, and verifying edge cases.",
  "think.budget": "Thinking Budget",
  "think.done": "Done",
  "think.turnOnHint": "Turn switch on to set token budget",
  "think.turnOn": "Turn On",
  "app.appearance": "Appearance",
  "app.reset": "Reset appearance defaults",
  "app.close": "Close appearance panel",
  "app.dark": "Dark mode",
  "app.palette": "Theme Palette",
  "app.typography": "Typography",
  "app.heading": "Heading size",
  "app.body": "Body size",
  "app.sections": "Sections",
  "app.continue": "Continue",
  "app.explore": "Explore",
  "app.recent": "Recent",
  "app.density": "Layout Density",
  "app.comfy": "Comfy",
  "app.compact": "Compact",
  "header.workbench": "Workbench",
};

const fr: Dict = {
  "lang.title": "Langue",
  "greet.morning": "Bonjour",
  "greet.afternoon": "Bon après-midi",
  "greet.evening": "Bonsoir",
  "home.hero": "Quelle est votre question juridique aujourd'hui ?",
  "home.explore": "Exemples de questions",
  "sidebar.collapse": "Réduire la barre latérale",
  "sidebar.new": "Nouvelle session",
  "sidebar.filter": "Filtrer les sessions...",
  "sidebar.tab.all": "Récents",
  "sidebar.tab.starred": "Favoris",
  "sidebar.tab.artifacts": "Artefacts",
  "sidebar.noArtifacts": "Aucun artefact ne correspond. Demandez à Sanad de créer un graphique, une maquette ou un rapport.",
  "sidebar.historyHidden": "L'historique récent est masqué dans les réglages d'apparence.",
  "sidebar.noStarred": "Mettez des conversations en favori pour les retrouver ici.",
  "sidebar.noConv": "Aucune conversation trouvée.",
  "sidebar.delete": "Supprimer la session",
  "sidebar.pseudonymiser": "Pseudonymisation",
  "sidebar.rules": "règles",
  "sidebar.vault": "Coffre chiffré",
  "sidebar.knowledge": "Connaissances du projet",
  "sidebar.appearance": "Apparence et palette",
  "mode.offline": "Hors-ligne",
  "mode.hybrid": "Hybride",
  "mode.cloud": "Cloud",
  "aud.citizen": "Citoyen",
  "aud.pro": "Avocat Pro",
  "tools.title": "Outils juridiques",
  "tools.calc": "Simulateurs & Calculatrices",
  "tools.calc.sub": "Licenciement, Iddah, Mut'ah, salaire",
  "tools.situations": "Situations citoyennes",
  "tools.situations.sub": "Salarié, Divorce, Héritage",
  "tools.statutes": "Textes & Bulletin Officiel",
  "tools.statutes.sub": "Code du Travail, Moudawana",
  "tools.concordance": "Concordance & Date",
  "tools.audit": "Trace d'Audit & NLI",
  "tools.audit.sub": "Vérification factuelle & sources",
  "tools.consult": "Dossier Consultation",
  "tools.consult.sub": "Synthèse pour avocat",
  "composer.placeholder": "Répondez à Sanad ou demandez d'explorer un artefact...",
  "composer.attach": "Joindre des images, documents ou données",
  "composer.thinking": "Réflexion",
  "composer.stop": "Arrêter la génération",
  "composer.send": "Envoyer le message",
  "composer.vault": "Ouvrir le coffre chiffré (AES-256)",
  "composer.preview": "Inspecter la charge utile et la confidentialité (aperçu d'envoi)",
  "think.title": "Réflexion approfondie",
  "think.sub": "Raisonnement étape par étape",
  "think.desc": "Permet à Sanad de raisonner en profondeur avant de répondre : recoupement des preuves, calculs et vérification des cas limites.",
  "think.budget": "Budget de réflexion",
  "think.done": "Terminé",
  "think.turnOnHint": "Activez pour régler le budget de jetons",
  "think.turnOn": "Activer",
  "app.appearance": "Apparence",
  "app.reset": "Rétablir l'apparence par défaut",
  "app.close": "Fermer le panneau d'apparence",
  "app.dark": "Mode sombre",
  "app.palette": "Palette de thème",
  "app.typography": "Typographie",
  "app.heading": "Taille des titres",
  "app.body": "Taille du texte",
  "app.sections": "Sections",
  "app.continue": "Continuer",
  "app.explore": "Explorer",
  "app.recent": "Récents",
  "app.density": "Densité de l'interface",
  "app.comfy": "Confortable",
  "app.compact": "Compacte",
  "header.workbench": "Atelier",
};

const ar: Dict = {
  "lang.title": "اللغة",
  "greet.morning": "صباح الخير",
  "greet.afternoon": "مساء الخير",
  "greet.evening": "مساء الخير",
  "home.hero": "ما هو سؤالك القانوني اليوم؟",
  "home.explore": "أمثلة على الأسئلة",
  "sidebar.collapse": "طيّ الشريط الجانبي",
  "sidebar.new": "جلسة جديدة",
  "sidebar.filter": "تصفية الجلسات...",
  "sidebar.tab.all": "الأحدث",
  "sidebar.tab.starred": "المفضّلة",
  "sidebar.tab.artifacts": "المخرجات",
  "sidebar.noArtifacts": "لا توجد مخرجات مطابقة. اطلب من سند إنشاء رسم بياني أو نموذج أو تقرير.",
  "sidebar.historyHidden": "سجل المحادثات الأخيرة مخفي في إعدادات المظهر.",
  "sidebar.noStarred": "ضع نجمة على المحادثات المهمة لتجدها هنا.",
  "sidebar.noConv": "لم يتم العثور على محادثات.",
  "sidebar.delete": "حذف الجلسة",
  "sidebar.pseudonymiser": "إخفاء الهوية",
  "sidebar.rules": "قواعد",
  "sidebar.vault": "الخزنة المشفّرة",
  "sidebar.knowledge": "معرفة المشروع",
  "sidebar.appearance": "المظهر والألوان",
  "mode.offline": "دون اتصال",
  "mode.hybrid": "هجين",
  "mode.cloud": "سحابي",
  "aud.citizen": "مواطن",
  "aud.pro": "محامٍ محترف",
  "tools.title": "الأدوات القانونية",
  "tools.calc": "المحاكيات والحاسبات",
  "tools.calc.sub": "التعويض عن الفصل، العدّة، المتعة، الأجر",
  "tools.situations": "وضعيات المواطن",
  "tools.situations.sub": "الأجير، الطلاق، الإرث",
  "tools.statutes": "النصوص والجريدة الرسمية",
  "tools.statutes.sub": "مدونة الشغل، مدونة الأسرة",
  "tools.concordance": "التطابق والتاريخ",
  "tools.audit": "سجل التدقيق والاستدلال",
  "tools.audit.sub": "التحقق من الوقائع والمصادر",
  "tools.consult": "ملف الاستشارة",
  "tools.consult.sub": "ملخص للمحامي",
  "composer.placeholder": "ردّ على سند أو اطلب استكشاف مخرَج...",
  "composer.attach": "إرفاق صور أو مستندات أو بيانات",
  "composer.thinking": "التفكير",
  "composer.stop": "إيقاف التوليد",
  "composer.send": "إرسال الرسالة",
  "composer.vault": "فتح الخزنة المشفّرة (AES-256)",
  "composer.preview": "فحص الحمولة والخصوصية (معاينة الإرسال)",
  "think.title": "التفكير المعمّق",
  "think.sub": "استدلال خطوة بخطوة",
  "think.desc": "يتيح لسند التفكير بعمق قبل الإجابة: مقارنة الأدلة وإجراء الحسابات والتحقق من الحالات الحدّية.",
  "think.budget": "ميزانية التفكير",
  "think.done": "تم",
  "think.turnOnHint": "فعّل المفتاح لتحديد ميزانية الرموز",
  "think.turnOn": "تفعيل",
  "app.appearance": "المظهر",
  "app.reset": "استعادة المظهر الافتراضي",
  "app.close": "إغلاق لوحة المظهر",
  "app.dark": "الوضع الداكن",
  "app.palette": "لوحة الألوان",
  "app.typography": "الخطوط",
  "app.heading": "حجم العناوين",
  "app.body": "حجم النص",
  "app.sections": "الأقسام",
  "app.continue": "المتابعة",
  "app.explore": "استكشاف",
  "app.recent": "الأحدث",
  "app.density": "كثافة الواجهة",
  "app.comfy": "مريحة",
  "app.compact": "مضغوطة",
  "header.workbench": "مساحة العمل",
};

const DICTS: Record<Lang, Dict> = { en, fr, ar };

function detect(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY) as Lang | null;
    if (saved && saved in DICTS) return saved;
  } catch {
    /* ignore */
  }
  const nav = (typeof navigator !== "undefined" ? navigator.language : "fr").slice(0, 2).toLowerCase();
  return nav === "ar" || nav === "en" || nav === "fr" ? (nav as Lang) : "fr";
}

// ---- global translate function (used by components without the hook; they re-render with App on language change) ----
let activeLang: Lang = detect();
export const setActiveLang = (l: Lang) => {
  activeLang = l;
};
const IDX: Record<Lang, number> = { en: 0, fr: 1, ar: 2 };
/** tr("source text") or tr("text with {0}", [value]): translated string, falls back to the source text. */
export function tr(key: string, args?: ReadonlyArray<unknown>): string {
  const hit = DICT[key];
  let out = hit ? hit[IDX[activeLang]] || key : key;
  if (args) out = out.replace(/\{(\d+)\}/g, (_, i) => String(args[Number(i)] ?? ""));
  return out;
}

interface Ctx {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string) => string;
  dir: "ltr" | "rtl";
}
const I18nContext = createContext<Ctx>({ lang: "fr", setLang: () => {}, t: (k) => k, dir: "ltr" });

export const I18nProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [lang, setLangState] = useState<Lang>(detect);
  setActiveLang(lang); // before children render
  const dir = LANGS.find((l) => l.id === lang)!.dir;

  useEffect(() => {
    const root = document.documentElement;
    root.lang = lang;
    root.dir = dir;
  }, [lang, dir]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo<Ctx>(
    () => ({ lang, setLang, dir, t: (key) => DICTS[lang][key] ?? en[key] ?? key }),
    [lang, setLang, dir]
  );
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
};

export const useI18n = () => useContext(I18nContext);
