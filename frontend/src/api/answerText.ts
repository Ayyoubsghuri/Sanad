/** The fixed wording of an answer, in the language of the answer (not the app's language): an Arabic question gets an Arabic reply. */
export type ALang = "ar" | "fr" | "en";

export function answerLang(l?: string | null): ALang {
  return l === "ar" || l === "fr" ? l : "en";
}

type Row = Record<ALang, string>;
const R = (en: string, fr: string, ar: string): Row => ({ en, fr, ar });

const TXT = {
  partial: R("Partially verified answer", "Réponse partiellement vérifiée", "جواب تم التحقق من جزء منه فقط"),
  extractive_only: R("Could not verify an answer: quoted articles only", "Impossible de vérifier une réponse : articles cités uniquement", "تعذر التحقق من جواب: المواد المقتبسة فقط"),
  abstained: R("Not answered", "Pas de réponse", "لا جواب"),
  why: R("Why", "Pourquoi", "السبب"),
  lawAsOf: R("Law as of", "Loi à la date du", "القانون المعمول به بتاريخ"),
  sources: R("Sources", "Sources", "المصادر"),
  rulings: R("Similar Court of Cassation rulings", "Arrêts similaires de la Cour de cassation", "قرارات مشابهة لمحكمة النقض"),
  rulingsNote: R("how the Court has decided similar cases: an aid to interpretation, not the law itself, and every case depends on its facts",
    "comment la Cour a tranché des affaires proches : une aide à l'interprétation, pas la loi, et chaque affaire dépend de ses faits",
    "كيف قضت المحكمة في قضايا قريبة: وسيلة للفهم وليست نصا قانونيا، وكل قضية تتوقف على وقائعها"),
  rulingsAmong: R("Among the {0} most similar rulings found", "Parmi les {0} arrêts les plus proches trouvés", "من بين {0} قرارا الأقرب التي وُجدت"),
  web: R("Official websites", "Sites officiels", "مواقع رسمية"),
  webNote: R("links found by web research: not verified and not used in the answer, open them to read the source",
    "liens trouvés par la recherche web : non vérifiés et non utilisés dans la réponse, ouvrez-les pour lire la source",
    "روابط وجدها البحث في الويب: غير متحقَّق منها ولم تُستعمل في الجواب، افتحها لقراءة المصدر"),
  webNone: R("Web research found no page on an official site for this question.", "La recherche web n'a trouvé aucune page d'un site officiel pour cette question.", "لم يجد البحث في الويب أي صفحة في موقع رسمي لهذا السؤال."),
  webError: R("Web research was not available (no connection or the search engine refused).", "La recherche web n'était pas disponible (pas de connexion ou refus du moteur).", "البحث في الويب لم يكن متاحا (لا اتصال أو رفض محرك البحث)."),
  webIdentifier: R("Web research skipped: the question still contains an identifier (ID card, phone…).", "Recherche web non faite : la question contient encore un identifiant (CIN, téléphone…).", "لم يُجرَ البحث في الويب: لا يزال السؤال يتضمن معرّفا (بطاقة، هاتف…)."),
  nextSteps: R("What you can do now", "Ce que vous pouvez faire maintenant", "ما يمكنك فعله الآن"),
  nextNote: R("practical steps drawn from the articles above: they guide you but do not replace a professional who has read your file",
    "étapes pratiques tirées des articles ci-dessus : elles vous orientent mais ne remplacent pas un professionnel qui a lu votre dossier",
    "خطوات عملية مستخلصة من المواد أعلاه: توجهك ولا تغني عن مختص اطلع على ملفك"),
  deadline: R("Time limit", "Délai", "الأجل"),
  where: R("Where", "Où", "أين"),
  documents: R("Papers to prepare", "Pièces à préparer", "الوثائق المطلوب تحضيرها"),
  whenPro: R("When to see a professional", "Quand consulter un professionnel", "متى تستشير مختصا"),
  ruling: R("Ruling", "Arrêt", "القرار"),
  chamber: R("chamber", "chambre", "الغرفة"),
  pdf: R("PDF", "PDF", "PDF"),
  more: R("other retrieved passage(s): see the evidence card.", "autre(s) passage(s) retrouvé(s) : voir la carte de preuves.", "مقاطع أخرى تم العثور عليها: انظر بطاقة الأدلة."),
  notInForce: R("not in force on that date", "non en vigueur à cette date", "غير ساري في ذلك التاريخ"),
  contested: R("contested", "contesté", "محل نزاع"),
  bring: R("Bring to a professional:", "À apporter à un professionnel :", "ما ينبغي إحضاره إلى مختص:"),
  calculations: R("Calculations", "Calculs", "الحسابات"),
  oneMore: R("I need one more detail to answer.", "J'ai besoin d'un détail de plus pour répondre.", "أحتاج إلى معلومة إضافية للإجابة."),
  moreInput: R("More input needed.", "Informations complémentaires nécessaires.", "يلزم مزيد من المعلومات."),
  review: R("Review required before sending.", "Relecture requise avant l'envoi.", "يلزم التحقق قبل الإرسال."),
  packUnavailable: R("Law pack unavailable.", "Pack de lois indisponible.", "حزمة القوانين غير متاحة."),
  deep: R("Deep search", "Recherche approfondie", "بحث معمّق"),
  rounds: R("round(s)", "tour(s)", "جولات"),
  morePassages: R("more passage(s)", "passage(s) de plus", "مقاطع إضافية"),
  noAnswerHere: R("The articles below mention the subject, but none of them states the answer.", "Les articles ci-dessous évoquent le sujet, mais aucun ne donne la réponse.", "المواد أدناه تذكر الموضوع لكن لا واحدة منها تنص على الجواب."),
  maybeMissing: R(
    "The text that answers it may not be in the law pack (older laws and the Constitution are often missing): check in the law browser.",
    "Le texte qui y répond n'est peut-être pas dans le pack de lois (les textes anciens et la Constitution manquent souvent) : vérifiez dans l'explorateur de textes.",
    "قد لا يكون النص الذي يجيب عنه في حزمة القوانين (النصوص القديمة والدستور غالبا غير موجودة): تحقق في مستكشف النصوص."
  ),
};
export type Key = keyof typeof TXT;

/** Outcome of a Court of Cassation ruling, with what it means for the decision that was appealed. */
export const OUTCOME: Record<string, Row> = {
  cassation: R("set aside (cassation)", "cassation (décision annulée)", "نقض (أُلغي القرار المطعون فيه)"),
  partial_cassation: R("partly set aside", "cassation partielle", "نقض جزئي"),
  rejected: R("appeal rejected (the decision stands)", "pourvoi rejeté (la décision est maintenue)", "رفض الطلب (بقي القرار قائما)"),
  inadmissible: R("appeal inadmissible", "pourvoi irrecevable", "عدم قبول الطلب"),
  reversed: R("judgment reversed", "jugement infirmé", "إلغاء الحكم المستأنف"),
  affirmed: R("judgment affirmed", "jugement confirmé", "تأييد الحكم المستأنف"),
  rectified: R("clerical error corrected", "erreur matérielle rectifiée", "إصلاح خطأ مادي"),
  lapsed: R("appeal lapsed", "déchéance du pourvoi", "سقوط الطلب"),
  withdrawn: R("withdrawn", "désistement", "تنازل / تشطيب"),
  other: R("other", "autre", "أخرى"),
  unknown: R("outcome unclear", "issue non déterminée", "منطوق غير واضح"),
};
export const CHAMBER: Record<string, Row> = {
  civil: R("civil", "civile", "المدنية"), family: R("family", "statut personnel", "الأحوال الشخصية"),
  commercial: R("commercial", "commerciale", "التجارية"), administrative: R("administrative", "administrative", "الإدارية"),
  social: R("social", "sociale", "الاجتماعية"), criminal: R("criminal", "pénale", "الجنائية"), real_estate: R("real estate", "immobilière", "العقارية"),
};
export const T = (l: ALang, k: Key): string => TXT[k][l];

const CHECK: Record<string, Row> = {
  citation_exists: R("the claim has no supporting citation", "l'affirmation n'a pas de citation à l'appui", "الادعاء لا يستند إلى أي نص مستشهد به"),
  quote_matches: R("the quote does not match the article's text", "la citation ne correspond pas au texte de l'article", "الاقتباس لا يطابق نص المادة"),
  placeholders_intact: R("names or identifiers that are not in the cited texts", "noms ou identifiants absents des textes cités", "أسماء أو معرّفات غير موجودة في النصوص المستشهد بها"),
  claim_is_supported: R("the quoted text does not support the claim", "le texte cité ne soutient pas l'affirmation", "النص المقتبس لا يدعم الادعاء"),
  version_is_right: R("the article version is not the one in force on the law date", "la version de l'article n'est pas celle en vigueur à la date retenue", "نسخة المادة ليست السارية في التاريخ المعتمد"),
  conflicts_are_shown: R("two versions of an article apply: both must be stated with their dates", "deux versions d'un article s'appliquent : les deux doivent être indiquées avec leurs dates", "تنطبق نسختان من مادة: يجب ذكرهما معا بتاريخيهما"),
  no_stray_numbers: R("numbers in the answer that are not in the cited texts", "chiffres de la réponse absents des textes cités", "أرقام في الجواب غير موجودة في النصوص المستشهد بها"),
};

/** "claim 0: [no_stray_numbers] numbers ['1', '2'] do not appear…" -> a plain sentence in the answer language. */
export function failureText(raw: string, l: ALang): string {
  const m = raw.match(/^(?:claim (\d+): )?\[(\w+)\]\s*(.*)$/s);
  if (!m) return raw;
  const [, idx, code, rest] = m;
  const base = CHECK[code]?.[l];
  if (!base) return raw;
  const nums = code === "no_stray_numbers" ? rest.match(/\[(.*?)\]/)?.[1]?.replace(/'/g, "") : "";
  const claim = idx === undefined ? "" : l === "ar" ? `الادعاء ${Number(idx) + 1}: ` : l === "fr" ? `affirmation ${Number(idx) + 1} : ` : `claim ${Number(idx) + 1}: `;
  return `${claim}${base}${nums ? `: ${nums}` : ""}`;
}

function dt(l: ALang, d: string) {
  return d;
}

/** The backend's English notes (law date assumption, notices, fallbacks) in the answer language. Unknown text is left as it is. */
export function noteText(s: string, l: ALang): string {
  if (l === "en") return s;
  return s
    .split(" · ")
    .map((seg) => oneNote(seg, l))
    .join(" · ");
}

function oneNote(s: string, l: ALang): string {
  const ar = l === "ar";
  let m: RegExpMatchArray | null;
  if ((m = s.match(/^no date given: law applied as in force today \((.+)\)$/)))
    return ar ? `لم يُذكر تاريخ: طُبّق القانون السائر المفعول اليوم (${m[1]})` : `aucune date indiquée : loi appliquée telle qu'en vigueur aujourd'hui (${m[1]})`;
  if ((m = s.match(/^law applied as in force on (\S+) \(chosen by the user\)$/)))
    return ar ? `طُبّق القانون السائر المفعول بتاريخ ${m[1]} (التاريخ الذي اخترته)` : `loi appliquée telle qu'en vigueur le ${m[1]} (date choisie par vous)`;
  if ((m = s.match(/^law applied as in force on (\S+) \(date found in the question\)$/)))
    return ar ? `طُبّق القانون السائر المفعول بتاريخ ${m[1]} (التاريخ الوارد في السؤال)` : `loi appliquée telle qu'en vigueur le ${m[1]} (date trouvée dans la question)`;
  if ((m = s.match(/^law applied as in force on (\S+) \(start of (.+)\)$/)))
    return ar ? `طُبّق القانون السائر المفعول بتاريخ ${m[1]} (بداية ${m[2]})` : `loi appliquée telle qu'en vigueur le ${m[1]} (début de ${m[2]})`;
  if ((m = s.match(/^law applied as in force on (\S+) \(resolved from the device clock\)$/)))
    return ar ? `طُبّق القانون السائر المفعول بتاريخ ${m[1]} (حُسب من ساعة الجهاز)` : `loi appliquée telle qu'en vigueur le ${m[1]} (calculée d'après l'horloge de l'appareil)`;
  if (s === "several dates in the question; the latest was used")
    return ar ? "وردت عدة تواريخ في السؤال؛ اعتُمد أحدثها" : "plusieurs dates dans la question ; la plus récente a été retenue";
  if ((m = s.match(/^the year (\d{4}) is read as the subject of the question: .*$/)))
    return ar
      ? `السنة ${m[1]} تُفهم على أنها موضوع السؤال: تُستعمل النصوص السارية اليوم بما فيها اللاحقة؛ اذكر تاريخا دقيقا لتطبيق القانون كما كان حينها`
      : `l'année ${m[1]} est comprise comme le sujet de la question : les textes en vigueur aujourd'hui sont utilisés, y compris les plus récents ; donnez une date exacte pour appliquer la loi telle qu'elle était alors`;
  if ((m = s.match(/^The law pack is (\d+) days old: newer laws may exist\. Update the law pack\.$/)))
    return ar ? `عمر حزمة القوانين ${m[1]} يوما: قد توجد قوانين أحدث. حدّث الحزمة.` : `Le pack de lois a ${m[1]} jours : des textes plus récents peuvent exister. Mettez-le à jour.`;
  if (s === "The law pack is unsigned (development mode): its authenticity is not verified.")
    return ar ? "حزمة القوانين غير موقّعة (وضع التطوير): لم يتم التحقق من أصالتها." : "Le pack de lois n'est pas signé (mode développement) : son authenticité n'est pas vérifiée.";
  if (s === "Part of the answer could not be verified and was left out: rely on the quoted articles below.")
    return ar ? "تعذر التحقق من جزء من الجواب فحُذف: اعتمد على المواد المقتبسة أدناه." : "Une partie de la réponse n'a pas pu être vérifiée et a été retirée : appuyez-vous sur les articles cités ci-dessous.";
  if (s === "Two versions of an article apply on different dates; both are shown in the sources with their dates.")
    return ar ? "تنطبق نسختان من مادة في تاريخين مختلفين؛ تظهر النسختان في المصادر مع تاريخيهما." : "Deux versions d'un article s'appliquent à des dates différentes ; les deux figurent dans les sources avec leurs dates.";
  if ((m = s.match(/^deep search: (\d+) more passage\(s\) found in (\d+) round\(s\)$/)))
    return ar ? `بحث معمّق: ${m[1]} مقاطع إضافية في ${m[2]} جولات` : `recherche approfondie : ${m[1]} passage(s) de plus en ${m[2]} tour(s)`;
  void dt;
  return s;
}
