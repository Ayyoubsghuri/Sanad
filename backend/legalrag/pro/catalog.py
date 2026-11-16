"""The professional tools: what each asks for, what it produces, and the instructions given to the model.

kind = courtroom (three model calls: lawyer A, lawyer B, judge), report (one call, sections of cited items) or
finder (search only, an optional model summary). Labels are {en, fr, ar}."""
from __future__ import annotations

from typing import Any


def L(en: str, fr: str, ar: str) -> dict[str, str]:
    return {"en": en, "fr": fr, "ar": ar}


F_FACTS = {"id": "facts", "kind": "textarea", "required": True,
           "label": L("Facts of the case", "Faits de l'affaire", "وقائع القضية"),
           "placeholder": L("What happened, when, between whom (names are masked before anything is sent), what has been done so far…",
                            "Ce qui s'est passé, quand, entre qui (les noms sont masqués avant tout envoi), les démarches déjà faites…",
                            "ما الذي حدث، ومتى، وبين من (تُخفى الأسماء قبل أي إرسال)، وما الإجراءات التي اتُّخذت…")}
F_GOAL = {"id": "goal", "kind": "text", "required": False,
          "label": L("What is asked / the goal", "Ce qui est demandé / l'objectif", "المطلوب / الهدف"),
          "placeholder": L("e.g. damages for dismissal, cancellation of the sale…", "ex. indemnité de licenciement, annulation de la vente…",
                           "مثال: التعويض عن الطرد، إبطال البيع…")}
F_DOC = {"id": "document", "kind": "textarea", "required": True,
         "label": L("Text of the document", "Texte du document", "نص الوثيقة"),
         "placeholder": L("Paste the contract, deed, notice or judgment.", "Collez le contrat, l'acte, la notification ou le jugement.",
                          "الصق العقد أو الرسم أو الإنذار أو الحكم.")}
F_QUESTION = {"id": "question", "kind": "text", "required": False,
              "label": L("Specific question (optional)", "Question précise (facultatif)", "سؤال محدد (اختياري)")}
F_SIDE = {"id": "side", "kind": "choice", "required": True, "label": L("Your client is", "Votre client est", "موكلك هو"),
          "options": [{"id": "claimant", "label": L("Claimant / appellant", "Demandeur / appelant", "المدعي / الطاعن")},
                      {"id": "defendant", "label": L("Defendant / respondent", "Défendeur / intimé", "المدعى عليه / المطلوب")}]}
F_CHAMBER = {"id": "chamber", "kind": "choice", "required": False, "label": L("Chamber", "Chambre", "الغرفة"),
             "options": [{"id": "", "label": L("All", "Toutes", "الكل")},
                         {"id": "civil", "label": L("Civil", "Civile", "المدنية")},
                         {"id": "family", "label": L("Family", "Statut personnel", "الأحوال الشخصية")},
                         {"id": "commercial", "label": L("Commercial", "Commerciale", "التجارية")},
                         {"id": "social", "label": L("Social (labour)", "Sociale", "الاجتماعية")},
                         {"id": "administrative", "label": L("Administrative", "Administrative", "الإدارية")},
                         {"id": "criminal", "label": L("Criminal", "Pénale", "الجنائية")},
                         {"id": "real_estate", "label": L("Real estate", "Immobilière", "العقارية")}]}


def T(id: str, group: str, kind: str, icon: str, label: dict, desc: dict, fields: list, instructions: str = "",
      sections: list[str] | None = None, rulings: bool = True, featured: bool = False) -> dict[str, Any]:
    return {"id": id, "group": group, "kind": kind, "icon": icon, "label": label, "description": desc, "fields": fields,
            "instructions": instructions, "sections": sections or [], "uses_rulings": rulings, "featured": featured}


GROUPS = [
    {"id": "featured", "label": L("Sanad Professional", "Sanad Professionnel", "سند للمهنيين")},
    {"id": "lawyer", "label": L("Lawyers", "Avocats", "المحامون")},
    {"id": "judge", "label": L("Judges & researchers", "Magistrats & chercheurs", "القضاة والباحثون")},
    {"id": "notary", "label": L("Notaries & adouls", "Notaires & adouls", "الموثقون والعدول")},
    {"id": "corporate", "label": L("Company legal department", "Service juridique d'entreprise", "المصلحة القانونية للمقاولة")},
    {"id": "bailiff", "label": L("Judicial officers (bailiffs)", "Commissaires judiciaires", "المفوضون القضائيون")},
]

TOOLS: list[dict[str, Any]] = [
    # ---------------------------------------------------------------------------------------------------- featured
    T("courtroom", "featured", "courtroom", "gavel",
      L("AI Courtroom", "Tribunal IA", "المحكمة الافتراضية"),
      L("Lawyer A builds the strongest case for your client, Lawyer B attacks it, and an independent judge weighs both: arguments, sources, risks and an estimated chance of success.",
        "L'avocat A construit la meilleure défense de votre client, l'avocat B l'attaque, et un juge indépendant tranche : arguments, sources, risques et chance de succès estimée.",
        "المحامي (أ) يبني أقوى دفاع لموكلك، والمحامي (ب) يهاجمه، ثم يزن قاضٍ مستقل الطرفين: الحجج والمصادر والمخاطر وتقدير لفرص النجاح."),
      [F_FACTS, F_SIDE, F_GOAL], featured=True),
    T("case_analyzer", "featured", "report", "briefcase",
      L("Case Analyzer", "Analyse de dossier", "محلل القضايا"),
      L("The legal questions in the file, the law in force on the date, what similar rulings decided, and what won or lost in them.",
        "Les questions juridiques du dossier, le droit en vigueur à la date, ce qu'ont décidé des arrêts similaires et ce qui y a gagné ou perdu.",
        "المسائل القانونية في الملف، والقانون الساري في التاريخ، وما قضت به قرارات مشابهة، وما الذي ربح أو خسر فيها."),
      [F_FACTS, F_GOAL],
      "Analyse the whole case file. Identify each legal issue, the rules that govern it (only from the passages), how the similar "
      "rulings decided comparable issues, which arguments succeeded in them (accepted grounds) and which failed and why (rejected grounds), "
      "the evidence the client needs, the procedural points (competent court, deadlines quoted in the passages) and the next steps.",
      ["Legal issues", "Applicable law", "What similar rulings decided", "Arguments that won in similar cases",
       "Arguments that lost and why", "Evidence and documents needed", "Procedure and deadlines", "Recommended next steps"], featured=True),
    T("jurisprudence", "featured", "finder", "library",
      L("Jurisprudence Finder", "Recherche de jurisprudence", "الباحث في الاجتهاد القضائي"),
      L("Comparable Court of Cassation rulings, with their outcome, principle and the grounds that were accepted or rejected.",
        "Arrêts comparables de la Cour de cassation, avec leur issue, leur principe et les moyens accueillis ou rejetés.",
        "قرارات مماثلة لمحكمة النقض، مع منطوقها ومبدئها والوسائل المقبولة أو المرفوضة."),
      [{**F_FACTS, "label": L("Describe the issue or the case", "Décrivez la question ou l'affaire", "صف المسألة أو القضية")}, F_CHAMBER],
      "Summarise the line of jurisprudence these rulings show on the user's issue: the principles the Court applies, how outcomes "
      "split, what made the appeals succeed or fail, and any rulings that point in different directions.",
      ["Principles applied by the Court", "What made appeals succeed", "What made appeals fail", "Divergent rulings"], featured=True),
    # ---------------------------------------------------------------------------------------------------- lawyers
    T("defence_memo", "lawyer", "report", "file-pen",
      L("Defence memorandum", "Mémoire en défense", "مذكرة دفاعية"),
      L("A structured draft memorandum (facts, pleas in law, requests) built on the articles and rulings found.",
        "Un projet de mémoire structuré (faits, moyens de droit, demandes) fondé sur les articles et arrêts trouvés.",
        "مسودة مذكرة منظمة (الوقائع، الوسائل القانونية، الطلبات) مبنية على المواد والقرارات المسترجعة."),
      [F_FACTS, F_SIDE, F_GOAL],
      "Draft a defence memorandum for the client's side in formal Moroccan court style: a short statement of facts, then each plea "
      "in law as its own item (procedural pleas first: competence, admissibility, limitation; then the merits), each relying on the "
      "passages, citing rulings that support it, then the requests to the court. Write it so a lawyer can adapt it.",
      ["Statement of facts", "Procedural pleas", "Pleas on the merits", "Supporting case law", "Requests to the court"]),
    T("consultation", "lawyer", "report", "message-square",
      L("Legal consultation", "Consultation juridique", "استشارة قانونية"),
      L("A written consultation for a client: the law, the options, the risks and a recommendation.",
        "Une consultation écrite pour un client : le droit, les options, les risques et une recommandation.",
        "استشارة مكتوبة للموكل: القانون والخيارات والمخاطر والتوصية."),
      [F_FACTS, F_QUESTION],
      "Write a professional legal consultation answering the client's question: the applicable rules, the options open to the client "
      "with their conditions, costs and deadlines where the passages give them, the risks of each option, and a reasoned recommendation.",
      ["Question", "Applicable law", "Options", "Risks", "Recommendation"]),
    T("strengths", "lawyer", "report", "scale",
      L("Strengths & weaknesses", "Forces et faiblesses", "نقاط القوة والضعف"),
      L("An honest audit of the client's position before going to court.", "Un audit honnête de la position du client avant l'audience.",
        "تقييم صريح لموقف الموكل قبل الذهاب إلى المحكمة."),
      [F_FACTS, F_SIDE],
      "Audit the client's position frankly. List its legal and factual strengths and its weaknesses, how the opponent will likely "
      "exploit each weakness, and how to cure or mitigate it (evidence, procedure, alternative claims).",
      ["Strengths", "Weaknesses", "How the opponent will attack", "How to fix the weak points"]),
    T("opponent", "lawyer", "report", "swords",
      L("Opposing lawyer simulator", "Simulateur d'avocat adverse", "محاكي المحامي الخصم"),
      L("What the other side will plead, and ready answers to each argument.", "Ce que plaidera la partie adverse, et des réponses prêtes à chaque argument.",
        "ما الذي سيدفع به الطرف الآخر، مع ردود جاهزة على كل حجة."),
      [F_FACTS, F_SIDE],
      "Play the opposing lawyer. Produce the arguments the other side will most likely raise (procedural and on the merits), each "
      "with its legal basis from the passages, and for each one the best reply for the client.",
      ["Arguments the other side will raise", "Replies for your client"]),
    T("contract_review", "lawyer", "report", "file-search",
      L("Contract review", "Revue de contrat", "مراجعة العقود"),
      L("Risky, unbalanced, missing or unlawful clauses, against Moroccan law.", "Clauses risquées, déséquilibrées, manquantes ou illégales, au regard du droit marocain.",
        "البنود الخطرة أو غير المتوازنة أو الناقصة أو المخالفة للقانون المغربي."),
      [F_DOC, F_QUESTION],
      "Review the contract clause by clause against the passages. Flag clauses that contradict mandatory rules (cite them), unbalanced "
      "or risky clauses, missing clauses the law requires or that are usual protection, and propose a corrected wording for each problem.",
      ["Unlawful clauses", "Risky or unbalanced clauses", "Missing clauses", "Suggested wording"], rulings=False),
    T("appeal_grounds", "lawyer", "report", "arrow-up-right",
      L("Appeal grounds analyser", "Analyse des moyens de recours", "محلل أسباب الطعن"),
      L("From a judgment: the grounds for appeal or cassation and how the Court of Cassation treated similar grounds.",
        "À partir d'un jugement : les moyens d'appel ou de cassation et le sort de moyens similaires devant la Cour de cassation.",
        "انطلاقا من حكم: أسباب الاستئناف أو النقض، وكيف تعاملت محكمة النقض مع وسائل مشابهة."),
      [{**F_DOC, "label": L("Text of the judgment (or its reasoning)", "Texte du jugement (ou ses motifs)", "نص الحكم (أو تعليله)")}, F_GOAL],
      "Find the possible grounds of appeal or cassation in this judgment, using the categories of the Moroccan Court of Cassation "
      "(violation of law, lack or insufficiency of reasoning, lack of legal basis, violation of procedure, distortion of documents, "
      "lack of competence). For each ground: the passage of the judgment it targets, the rule it relies on, and how the Court treated "
      "similar grounds in the rulings (accepted or rejected, and why). End with the grounds most likely to succeed and the deadlines quoted in the passages.",
      ["Possible grounds", "How the Court treated similar grounds", "Most promising grounds", "Deadlines and formalities"]),
    # ---------------------------------------------------------------------------------------------------- judges & researchers
    T("compare_rulings", "judge", "report", "git-compare",
      L("Compare two decisions", "Comparer deux décisions", "مقارنة قرارين"),
      L("Where two decisions agree, where they conflict, and which reasoning the law supports.",
        "Où deux décisions concordent, où elles divergent, et quel raisonnement le droit soutient.",
        "مواضع اتفاق قرارين ومواضع تعارضهما، وأي التعليلين يسنده القانون."),
      [{"id": "document", "kind": "textarea", "required": True, "label": L("First decision", "Première décision", "القرار الأول")},
       {"id": "document_b", "kind": "textarea", "required": True, "label": L("Second decision", "Seconde décision", "القرار الثاني")}],
      "Compare the two decisions given as DOCUMENT and DOCUMENT_B: the facts and question each decided, the rule each applied, where "
      "they agree, where they conflict, whether the conflict is real or due to different facts, and which reasoning is better supported "
      "by the passages and by the other rulings.",
      ["Question decided by each", "Points of agreement", "Points of conflict", "Which reasoning the law supports"]),
    T("applicable_law", "judge", "report", "book-open",
      L("Applicable provisions", "Dispositions applicables", "النصوص الواجبة التطبيق"),
      L("The articles that govern the facts on the given date, with their version in force.", "Les articles qui régissent les faits à la date donnée, dans leur version en vigueur.",
        "المواد التي تحكم الوقائع في التاريخ المحدد، بصيغتها السارية."),
      [F_FACTS],
      "Identify the provisions that govern these facts on the date, grouped by legal question: substantive rules, procedural rules, "
      "and any transitional rule. For each, say in one sentence why it applies. Do not decide the case.",
      ["Substantive rules", "Procedural rules", "Transitional rules and dates"], rulings=False),
    T("neutral_summary", "judge", "report", "align-left",
      L("Neutral case summary", "Résumé neutre de l'affaire", "ملخص محايد للقضية"),
      L("A balanced summary of a file: parties, facts, claims, defences, questions to decide.",
        "Un résumé équilibré d'un dossier : parties, faits, demandes, moyens de défense, questions à trancher.",
        "ملخص متوازن للملف: الأطراف والوقائع والطلبات والدفوع والمسائل المطلوب الفصل فيها."),
      [{**F_DOC, "label": L("Case file (claims, replies, documents)", "Dossier (demandes, réponses, pièces)", "الملف (المقالات، المذكرات، الوثائق)")}],
      "Write a strictly neutral summary of the file for a judge: the parties (as placeholders), the undisputed facts, the disputed facts, "
      "each side's claims and defences, the legal questions the court must decide with the provisions that govern them. No opinion on the outcome.",
      ["Parties", "Undisputed facts", "Disputed facts", "Claims and defences", "Questions to decide"], rulings=False),
    T("contradictions", "judge", "report", "split",
      L("Contradictions finder", "Détection des contradictions", "كاشف التناقضات"),
      L("Inconsistencies inside a pleading or between a party's statements and the law.", "Incohérences dans des écritures ou entre les déclarations d'une partie et le droit.",
        "التناقضات داخل مذكرة أو بين أقوال طرف والقانون."),
      [{**F_DOC, "label": L("Pleadings or statements", "Écritures ou déclarations", "المذكرات أو التصريحات")}],
      "Find contradictions: statements that contradict each other (dates, amounts, roles, sequence of events), statements contradicted "
      "by the documents described, and legal claims contradicted by the passages. Quote the conflicting statements and explain the conflict.",
      ["Internal contradictions", "Contradictions with the documents", "Contradictions with the law"], rulings=False),
    # ---------------------------------------------------------------------------------------------------- notaries
    T("property_check", "notary", "report", "home",
      L("Property documents check", "Contrôle des titres de propriété", "فحص وثائق العقار"),
      L("Whether the documents of a property support the transaction: title, registration, charges, missing pieces.",
        "Si les pièces d'un bien permettent l'opération : titre, immatriculation, charges, pièces manquantes.",
        "مدى صلاحية وثائق العقار للمعاملة: الرسم العقاري، التحفيظ، التحملات، الوثائق الناقصة."),
      [{**F_DOC, "label": L("Description of the property and its documents", "Description du bien et de ses pièces", "وصف العقار ووثائقه")}, F_GOAL],
      "Check the property documents described against the passages: registered (titled) or not, ownership chain, charges and "
      "precautionary registrations, restrictions (collective, habous, forest, agricultural land), and the documents still missing for the transaction.",
      ["Status of the property", "Charges and restrictions", "Problems found", "Missing documents"], rulings=False),
    T("sale_agreement", "notary", "report", "file-signature",
      L("Sale agreement analysis", "Analyse d'un compromis de vente", "تحليل عقد البيع"),
      L("Conditions of validity, mandatory mentions and risks of a sale agreement.", "Conditions de validité, mentions obligatoires et risques d'un compromis.",
        "شروط الصحة والبيانات الإلزامية ومخاطر عقد البيع."),
      [F_DOC],
      "Analyse the sale agreement against the passages: conditions of validity, mandatory mentions (for property: those required for "
      "sales of registered and of off-plan property where relevant), price and payment terms, transfer of ownership and risks, and clauses to add or correct.",
      ["Validity", "Mandatory mentions present or missing", "Risks", "Clauses to add or correct"], rulings=False),
    T("inheritance_checklist", "notary", "report", "users",
      L("Inheritance file checklist", "Liste de contrôle successorale", "قائمة وثائق التركة"),
      L("Documents and steps to settle an estate, from the death certificate to the division.",
        "Pièces et étapes pour régler une succession, de l'acte de décès au partage.",
        "الوثائق والخطوات لتصفية التركة، من رسم الوفاة إلى القسمة."),
      [{**F_FACTS, "label": L("The estate (heirs, assets, wills, debts)", "La succession (héritiers, biens, testament, dettes)", "التركة (الورثة، الأموال، الوصية، الديون)")}],
      "Build the checklist to settle this estate under the passages: documents (death certificate, heirs' certificate - اراثة, title deeds…), "
      "the order of steps (debts, bequests within the third, shares), points needing a court, and what is missing in the file.",
      ["Documents to gather", "Steps in order", "Points that need a court", "What is missing"], rulings=False),
    T("missing_documents", "notary", "report", "clipboard-list",
      L("Missing documents finder", "Pièces manquantes", "الوثائق الناقصة"),
      L("For a given deed or procedure, which legally required documents are missing.", "Pour un acte ou une procédure, quelles pièces légalement requises manquent.",
        "بالنسبة لرسم أو مسطرة، ما الوثائق المطلوبة قانونا والناقصة."),
      [{**F_FACTS, "label": L("The deed or procedure, and the documents you have", "L'acte ou la procédure, et les pièces dont vous disposez", "الرسم أو المسطرة، والوثائق المتوفرة")}],
      "List the documents the law requires for this deed or procedure (only those the passages require or clearly imply), mark those "
      "the user has and those missing, and say what happens if each missing one is not produced.",
      ["Required documents", "Missing documents", "Consequences"], rulings=False),
    T("clauses_vs_law", "notary", "report", "list-checks",
      L("Clauses vs legislation", "Clauses face à la loi", "مطابقة البنود مع التشريع"),
      L("Each clause of a deed compared with the rule that governs it.", "Chaque clause d'un acte comparée à la règle qui la gouverne.",
        "مقارنة كل بند من بنود الرسم بالقاعدة التي تحكمه."),
      [F_DOC],
      "Take the deed clause by clause. For each clause, name the rule that governs it from the passages and say whether the clause "
      "complies, departs from a suppletive rule (allowed) or breaches a mandatory rule (void or risky).",
      ["Compliant clauses", "Departures from suppletive rules", "Breaches of mandatory rules"], rulings=False),
    # ---------------------------------------------------------------------------------------------------- corporate
    T("employment_contract", "corporate", "report", "id-card",
      L("Employment contract analysis", "Analyse de contrat de travail", "تحليل عقد الشغل"),
      L("An employment contract against the Labour Code: trial period, duration, pay, non-compete, termination.",
        "Un contrat de travail au regard du Code du travail : période d'essai, durée, salaire, non-concurrence, rupture.",
        "عقد الشغل في ضوء مدونة الشغل: فترة الاختبار، المدة، الأجر، عدم المنافسة، الإنهاء."),
      [F_DOC, F_QUESTION],
      "Analyse the employment contract against the passages (Labour Code and related texts): type and duration, trial period limits, "
      "working time, pay and the minimum wage, leave, non-compete and confidentiality, disciplinary and termination clauses. Flag every "
      "clause below the legal minimum and every risk for the company.",
      ["Clauses below the legal minimum", "Risks for the company", "Missing clauses", "Suggested wording"], rulings=False),
    T("compliance", "corporate", "report", "shield-check",
      L("Compliance check", "Contrôle de conformité", "فحص المطابقة"),
      L("A document or practice checked against the applicable law: obligations, gaps, sanctions.",
        "Un document ou une pratique vérifiés au regard du droit applicable : obligations, écarts, sanctions.",
        "فحص وثيقة أو ممارسة في ضوء القانون الساري: الالتزامات والثغرات والجزاءات."),
      [{**F_DOC, "label": L("Document, policy or practice", "Document, politique ou pratique", "الوثيقة أو السياسة أو الممارسة")}, F_QUESTION],
      "Check the document or practice against the passages: list each legal obligation that applies, whether it is met, the gap, the "
      "sanction the passages provide, and the corrective action. Personal data (law 09-08) and labour rules deserve particular attention when relevant.",
      ["Obligations that apply", "Gaps", "Sanctions", "Corrective actions"], rulings=False),
    T("procurement", "corporate", "report", "package",
      L("Procurement contract review", "Revue de marché / achat", "مراجعة عقود الصفقات والشراء"),
      L("Supply and public-procurement contracts: guarantees, penalties, price revision, termination.",
        "Contrats de fourniture et marchés publics : garanties, pénalités, révision des prix, résiliation.",
        "عقود التوريد والصفقات العمومية: الضمانات والغرامات ومراجعة الأثمان والفسخ."),
      [F_DOC],
      "Review the procurement or supply contract against the passages: object and price, price revision, delivery and acceptance, "
      "penalties for delay, guarantees and retentions, payment deadlines and late-payment interest, termination and disputes.",
      ["Key obligations", "Risky clauses", "Missing protections", "Suggested wording"], rulings=False),
    T("risk_identification", "corporate", "report", "alert-triangle",
      L("Legal risk identification", "Identification des risques juridiques", "تحديد المخاطر القانونية"),
      L("The legal risks of a project, decision or situation, ranked, with how to reduce them.",
        "Les risques juridiques d'un projet, d'une décision ou d'une situation, classés, avec les mesures de réduction.",
        "المخاطر القانونية لمشروع أو قرار أو وضعية، مرتبة، مع سبل الحد منها."),
      [{**F_FACTS, "label": L("The project, decision or situation", "Le projet, la décision ou la situation", "المشروع أو القرار أو الوضعية")}],
      "Identify the legal risks of this project or situation from the passages and rulings: for each risk, the rule behind it, how likely "
      "and how serious it is (high, medium, low, explained), the possible sanction or liability, and how to reduce it.",
      ["High risks", "Medium risks", "Low risks", "Measures to reduce them"]),
    T("policy_assistant", "corporate", "report", "book",
      L("Internal policy assistant", "Assistant politique interne", "مساعد السياسات الداخلية"),
      L("Draft or check an internal policy (rules of procedure, data protection, discipline) against the law.",
        "Rédiger ou vérifier une politique interne (règlement intérieur, données personnelles, discipline) au regard du droit.",
        "صياغة أو مراجعة سياسة داخلية (النظام الداخلي، حماية المعطيات، التأديب) في ضوء القانون."),
      [{**F_DOC, "required": False, "label": L("Existing policy (optional)", "Politique existante (facultatif)", "السياسة الحالية (اختياري)")},
       {**F_GOAL, "required": True, "label": L("Which policy and for what company", "Quelle politique et pour quelle entreprise", "أي سياسة ولأي مقاولة")}],
      "Draft or improve the internal policy requested, section by section, each section stating the rule it implements from the passages "
      "(for example the Labour Code's rules on internal regulations and discipline, or law 09-08 for personal data). Flag what must be "
      "submitted to or filed with an authority when the passages say so.",
      ["Policy sections", "Legal requirements it implements", "Filing and formalities"], rulings=False),
    # ---------------------------------------------------------------------------------------------------- bailiffs
    T("notice_drafting", "bailiff", "report", "mail",
      L("Notice & formal demand drafting", "Rédaction de notifications et mises en demeure", "صياغة الإنذارات والتبليغات"),
      L("A formal demand or notice with its mandatory mentions and legal basis.", "Une mise en demeure ou notification avec ses mentions obligatoires et sa base légale.",
        "إنذار أو تبليغ بالبيانات الإلزامية والأساس القانوني."),
      [F_FACTS, F_GOAL],
      "Draft the formal demand or notice requested, in the formal style used by Moroccan judicial officers, with every mention the "
      "passages make mandatory (parties as placeholders, object, legal basis, deadline given, consequences), then list the mandatory mentions you included and the rule for each.",
      ["Draft", "Mandatory mentions and their legal basis", "Deadlines that start running"], rulings=False),
    T("deadline_tracking", "bailiff", "report", "calendar-clock",
      L("Procedural deadline tracking", "Suivi des délais de procédure", "تتبع الآجال الإجرائية"),
      L("The deadlines that run from a service or judgment, each with its article. Check the dates with the deadline calculator.",
        "Les délais qui courent à partir d'une notification ou d'un jugement, chacun avec son article. Vérifiez les dates avec le calculateur.",
        "الآجال التي تسري من تبليغ أو حكم، كل أجل مع مادته. تحقق من التواريخ بحاسبة الآجال."),
      [{**F_FACTS, "label": L("What was served or decided, and when", "Ce qui a été signifié ou jugé, et quand", "ما الذي بُلِّغ أو صدر، ومتى")}],
      "List every deadline that runs from the event described, ONLY when a passage states it: the act concerned (appeal, opposition, "
      "cassation, execution…), the length as written in the passage, the starting point, and the consequence of missing it. Do not compute "
      "calendar dates; tell the user to use the deadline calculator for that.",
      ["Deadlines that run", "Starting points", "Consequences of missing them"], rulings=False),
    T("execution_checklist", "bailiff", "report", "list-ordered",
      L("Execution procedure checklist", "Liste de contrôle de l'exécution", "قائمة إجراءات التنفيذ"),
      L("The steps to execute a judgment: enforceable copy, notice, seizure, sale, report.",
        "Les étapes pour exécuter un jugement : grosse, commandement, saisie, vente, procès-verbal.",
        "خطوات تنفيذ حكم: النسخة التنفيذية، الإنذار، الحجز، البيع، المحضر."),
      [{**F_FACTS, "label": L("The judgment to execute and the situation", "Le jugement à exécuter et la situation", "الحكم المراد تنفيذه والوضعية")}],
      "Build the execution checklist from the passages: conditions for execution (final or provisionally enforceable judgment, "
      "enforceable copy), the notice and its deadline, the seizure options, the sale, difficulties of execution, and the reports to draw up. One item per step, in order.",
      ["Conditions for execution", "Steps in order", "Possible difficulties", "Reports to draw up"], rulings=False),
    T("service_record", "bailiff", "report", "file-check",
      L("Service-of-process record", "Procès-verbal de signification", "محضر التبليغ"),
      L("Organise a service report: who, where, how, refusals, and the mentions the law requires.",
        "Organiser un procès-verbal de signification : qui, où, comment, refus, et les mentions exigées.",
        "تنظيم محضر التبليغ: من، أين، كيف، الرفض، والبيانات التي يشترطها القانون."),
      [{**F_FACTS, "label": L("How the service went", "Comment s'est déroulée la signification", "كيف جرى التبليغ")}],
      "Organise the service-of-process record from the facts: the mentions the passages require (date, place, person served and their "
      "capacity, method, refusal and what to do then), check that the service as described is valid, and list what is missing.",
      ["Record", "Required mentions present or missing", "Validity of the service"], rulings=False),
]

BY_ID = {t["id"]: t for t in TOOLS}


def public_catalog(rulings_available: bool) -> dict[str, Any]:
    strip = ("instructions",)
    return {"groups": GROUPS, "tools": [{k: v for k, v in t.items() if k not in strip} for t in TOOLS], "rulings_available": rulings_available}
