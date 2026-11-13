import React, { useState, useMemo } from "react";
import { tr } from "../i18n";
import { useBackendCalc, type BackendCalc } from "../api/useBackendCalc";
import { explainError, LimitationTab, SalaryProjectionTab, TaxTab, WageArrearsTab } from "./CalculatorExtraTabs";
import {
  Calculator,
  X,
  FileCheck2,
  Calendar,
  DollarSign,
  Briefcase,
  Scale,
  Users,
  Copy,
  Check,
  ArrowRight,
  Info,
} from "lucide-react";

interface LegalCalculatorsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAttachCalculationToPrompt: (text: string) => void;
  currentAsOfDate: string;
}

type CalculatorTab = "smig" | "arrears" | "cash_duty" | "severance" | "deadlines" | "inheritance" | "salary" | "limitation" | "tax";
const EXTRA_TABS: CalculatorTab[] = ["arrears", "salary", "limitation", "tax"];

export const LegalCalculatorsModal: React.FC<LegalCalculatorsModalProps> = ({
  isOpen,
  onClose,
  onAttachCalculationToPrompt,
  currentAsOfDate,
}) => {
  const [activeTab, setActiveTab] = useState<CalculatorTab>("smig");
  const [copied, setCopied] = useState(false);
  const [extraText, setExtraText] = useState("");

  // 1. SMIG/SMAG State
  const [hourlyWage, setHourlyWage] = useState<number>(15.5);
  const [monthlyHours, setMonthlyHours] = useState<number>(191);
  const [wageSector, setWageSector] = useState<"smig" | "smag">("smig");
  const [wageDate, setWageDate] = useState<string>(currentAsOfDate || new Date().toISOString().slice(0, 10));

  // 2. 2% Cash Duty State
  const [propertyPrice, setPropertyPrice] = useState<number>(1200000);
  const [cashAmount, setCashAmount] = useState<number>(200000);
  const [propertyType, setPropertyType] = useState<"residential" | "commercial" | "land">("residential");
  const [dutyDate, setDutyDate] = useState<string>(currentAsOfDate || new Date().toISOString().slice(0, 10));

  // 3. Severance & Notice State
  const [seniorityYears, setSeniorityYears] = useState<number>(7);
  const [monthlySalary, setMonthlySalary] = useState<number>(6500);
  const [employeeCategory, setEmployeeCategory] = useState<"non_cadre" | "cadre">("non_cadre");

  // 4. Deadlines State
  const [claimAmount, setClaimAmount] = useState<number>(8500);
  const [notificationDate, setNotificationDate] = useState<string>(currentAsOfDate || new Date().toISOString().slice(0, 10));
  const [procedureType, setProcedureType] = useState<"standard" | "refere">("standard");

  // 5. Inheritance State
  const [spouseType, setSpouseType] = useState<"none" | "husband" | "wife">("wife");
  const [numSons, setNumSons] = useState<number>(1);
  const [numDaughters, setNumDaughters] = useState<number>(2);
  const [hasFather, setHasFather] = useState<boolean>(true);
  const [hasMother, setHasMother] = useState<boolean>(true);
  const [totalEstate, setTotalEstate] = useState<number>(500000);

  // Calculations
  const smigLocal = useMemo(() => {
    const is2026OrLater = new Date(wageDate) >= new Date("2026-01-01");
    const rate = wageSector === "smig" ? (is2026OrLater ? 17.92 : 17.1) : (is2026OrLater ? 97.44 : 93.0);
    const standardMonthly = wageSector === "smig" ? rate * monthlyHours : rate * 26;
    const actualMonthly = hourlyWage * monthlyHours;
    const deficit = Math.max(0, standardMonthly - actualMonthly);
    const complies = actualMonthly >= standardMonthly;

    return {
      rate,
      is2026OrLater,
      legalDecree: is2026OrLater
        ? "Décret n° 2.25.983 du 29 Décembre 2025 (BO 7469)"
        : "Décret n° 2.24.1122 du 28 Décembre 2024",
      standardMonthly: Math.round(standardMonthly * 100) / 100,
      actualMonthly: Math.round(actualMonthly * 100) / 100,
      deficit: Math.round(deficit * 100) / 100,
      complies,
      legalText: `Taux légal applicable au ${wageDate} : ${rate} MAD (${wageSector.toUpperCase()}). Salaire minimum mensuel obligatoire : ${standardMonthly.toFixed(
        2
      )} MAD.`,
    };
  }, [hourlyWage, monthlyHours, wageSector, wageDate]);

  const cashDutyLocal = useMemo(() => {
    const isAfterJuly2026 = new Date(dutyDate) >= new Date("2026-07-01");
    const baseRate = propertyType === "residential" ? 0.04 : propertyType === "commercial" ? 0.06 : 0.05;
    const baseDuty = propertyPrice * baseRate;
    const cashSurcharge = isAfterJuly2026 ? cashAmount * 0.02 : 0;
    const bankPortion = Math.max(0, propertyPrice - cashAmount);
    const totalDuty = baseDuty + cashSurcharge;

    return {
      isAfterJuly2026,
      baseRatePercent: baseRate * 100,
      baseDuty,
      cashSurcharge,
      bankPortion,
      totalDuty,
      legalBasis:
        "Code Général des Impôts (CGI) - Art. 133 complété par la Loi de Finances n° 50-25 (Dahir 1-25-67, BO 7465 bis)",
    };
  }, [propertyPrice, cashAmount, propertyType, dutyDate]);

  const severanceLocal = useMemo(() => {
    // Law 65-99 Art. 53:
    // 1-5 yrs: 96h/yr; 6-10: 144h/yr; 11-15: 192h/yr; >15: 240h/yr
    const hourlyBase = monthlySalary / 191;
    let totalHours = 0;
    const y = seniorityYears;

    const t1 = Math.min(y, 5) * 96;
    const t2 = y > 5 ? Math.min(y - 5, 5) * 144 : 0;
    const t3 = y > 10 ? Math.min(y - 10, 5) * 192 : 0;
    const t4 = y > 15 ? (y - 15) * 240 : 0;

    totalHours = t1 + t2 + t3 + t4;
    const severanceIndemnity = totalHours * hourlyBase;

    // Notice period (Art. 51 & Decree 2.04.469)
    let noticeMonths = 1;
    if (employeeCategory === "cadre") {
      noticeMonths = y < 1 ? 1 : y <= 5 ? 2 : 3;
    } else {
      noticeMonths = y < 1 ? 0.25 : y <= 5 ? 1 : 2;
    }
    const noticeIndemnity = noticeMonths * monthlySalary;

    return {
      hourlyBase: Math.round(hourlyBase * 100) / 100,
      totalHours,
      severanceIndemnity: Math.round(severanceIndemnity * 100) / 100,
      noticeMonths,
      noticeIndemnity: Math.round(noticeIndemnity * 100) / 100,
      totalLegalCompensation: Math.round((severanceIndemnity + noticeIndemnity) * 100) / 100,
      legalBasis: "Loi n° 65-99 (Code du Travail) - Articles 41, 51, 52 et 53",
    };
  }, [seniorityYears, monthlySalary, employeeCategory]);

  const deadlineLocal = useMemo(() => {
    const isNewCPC = new Date(notificationDate) >= new Date("2026-08-24");
    const threshold = isNewCPC ? 10000 : 5000;
    const canAppeal = claimAmount > threshold;
    const appealDays = procedureType === "refere" ? 15 : 30;

    const notif = new Date(notificationDate);
    const expiry = new Date(notif);
    expiry.setDate(expiry.getDate() + appealDays);

    return {
      isNewCPC,
      governingLaw: isNewCPC ? "Loi n° 58.25 (Art. 30)" : "Dahir portant loi n° 1-74-447 (Art. 19)",
      threshold,
      canAppeal,
      appealDays,
      expiryDateStr: expiry.toISOString().split("T")[0],
    };
  }, [claimAmount, notificationDate, procedureType]);

  const inheritanceLocal = useMemo(() => {
    // Deterministic Moudawana share calculation
    const hasChildren = numSons > 0 || numDaughters > 0;
    let spouseShare = 0;
    let spouseLabel = "Aucun";

    if (spouseType === "wife") {
      spouseShare = hasChildren ? 1 / 8 : 1 / 4;
      spouseLabel = hasChildren ? tr("1/8 (présence d'enfants)") : tr("1/4 (sans enfant)");
    } else if (spouseType === "husband") {
      spouseShare = hasChildren ? 1 / 4 : 1 / 2;
      spouseLabel = hasChildren ? tr("1/4 (présence d'enfants)") : tr("1/2 (sans enfant)");
    }

    const motherShare = hasChildren ? 1 / 6 : 1 / 3;
    const fatherShare = hasChildren ? 1 / 6 : 0; // + Asaba if no sons

    const fixedSharesTotal =
      (spouseType !== "none" ? spouseShare : 0) +
      (hasMother ? motherShare : 0) +
      (hasFather ? fatherShare : 0);

    const remainder = Math.max(0, 1 - fixedSharesTotal);
    const childrenParts = numSons * 2 + numDaughters;

    return {
      spouseShare,
      spouseLabel,
      motherShare: hasMother ? (hasChildren ? "1/6" : "1/3") : "N/A",
      fatherShare: hasFather ? (hasChildren ? "1/6" : tr("Asaba résiduaire")) : "N/A",
      remainderFraction: (remainder * 100).toFixed(1) + "%",
      spouseAmount: Math.round(totalEstate * (spouseType !== "none" ? spouseShare : 0)),
      motherAmount: hasMother ? Math.round(totalEstate * motherShare) : 0,
      fatherAmount: hasFather ? Math.round(totalEstate * fatherShare) : 0,
      childrenAmount: Math.round(totalEstate * remainder),
      sonEachAmount:
        numSons > 0 ? Math.round((totalEstate * remainder * 2) / (childrenParts || 1)) : 0,
      daughterEachAmount:
        numDaughters > 0 ? Math.round((totalEstate * remainder * 1) / (childrenParts || 1)) : 0,
      legalBasis: "Loi 70.03 (Code de la Famille - Moudawana) Livre VI sur la Succession (Art. 334 à 350)",
    };
  }, [spouseType, numSons, numDaughters, hasFather, hasMother, totalEstate]);

  // ---- Backend (authoritative, dated rate tables, tested pure functions). Local maths is only a fallback. ----
  const dayMs = 86400000;
  const isoMinusYears = (iso: string, years: number) => {
    const d = new Date(iso);
    return new Date(d.getTime() - Math.round(years * 365.25 * dayMs)).toISOString().slice(0, 10);
  };
  const num = (v: unknown): number | undefined => (typeof v === "number" ? v : undefined);

  const smigB = useBackendCalc(
    "minimum_wage",
    {
      date: wageDate,
      sector: wageSector === "smig" ? "non_agricultural" : "agricultural",
      ...(wageSector === "smig"
        ? { hours_worked: monthlyHours, pay: hourlyWage * monthlyHours }
        : { days_worked: 26, pay: hourlyWage * monthlyHours }),
    },
    isOpen && activeTab === "smig"
  );
  const cashB = useBackendCalc(
    "registration_cash_surcharge",
    {
      date: dutyDate,
      transfer_type: propertyType === "commercial" ? "business" : "real_estate",
      price: propertyPrice,
      cash_portion: Math.min(cashAmount, propertyPrice),
    },
    isOpen && activeTab === "cash_duty"
  );
  const sevB = useBackendCalc(
    "severance",
    {
      start_date: isoMinusYears(currentAsOfDate || new Date().toISOString().slice(0, 10), seniorityYears),
      end_date: currentAsOfDate || new Date().toISOString().slice(0, 10),
      monthly_wage: monthlySalary,
      monthly_hours: 191,
    },
    isOpen && activeTab === "severance"
  );
  const dlB = useBackendCalc(
    "procedural_deadline",
    {
      case_type: "civil",
      decision_date: notificationDate,
      notification_date: notificationDate,
      claim_amount: claimAmount,
    },
    isOpen && activeTab === "deadlines"
  );
  const inhB = useBackendCalc(
    "inheritance_shares",
    {
      estate: totalEstate,
      husband: spouseType === "husband",
      wives: spouseType === "wife" ? 1 : 0,
      sons: numSons,
      daughters: numDaughters,
      father: hasFather,
      mother: hasMother,
    },
    isOpen && activeTab === "inheritance"
  );

  const smigResult = useMemo(() => {
    const r = smigB.data?.result;
    if (!r) return smigLocal;
    const due = num(r.minimum_due) ?? smigLocal.standardMonthly;
    return {
      ...smigLocal,
      rate: num(r.rate) ?? smigLocal.rate,
      standardMonthly: due,
      actualMonthly: num(r.pay) ?? smigLocal.actualMonthly,
      deficit: num(r.shortfall) ?? smigLocal.deficit,
      complies: typeof r.compliant === "boolean" ? r.compliant : smigLocal.complies,
      legalDecree: smigB.data!.legal_basis.join("; ") || smigLocal.legalDecree,
    };
  }, [smigB.data, smigLocal]);

  const cashDutyResult = useMemo(() => {
    const r = cashB.data?.result;
    if (!r) return cashDutyLocal;
    const surcharge = num(r.surcharge) ?? cashDutyLocal.cashSurcharge;
    return {
      ...cashDutyLocal,
      cashSurcharge: surcharge,
      totalDuty: cashDutyLocal.baseDuty + surcharge,
      legalBasis: cashB.data!.legal_basis.join("; ") || cashDutyLocal.legalBasis,
    };
  }, [cashB.data, cashDutyLocal]);

  const severanceResult = useMemo(() => {
    const r = sevB.data?.result;
    if (!r) return severanceLocal;
    const ind = num(r.severance_if_fraction_prorata) ?? severanceLocal.severanceIndemnity;
    return {
      ...severanceLocal,
      hourlyBase: num(r.hourly_wage) ?? severanceLocal.hourlyBase,
      totalHours: num(r.hours_prorata) ?? severanceLocal.totalHours,
      severanceIndemnity: ind,
      totalLegalCompensation: Math.round((ind + severanceLocal.noticeIndemnity) * 100) / 100,
      legalBasis: sevB.data!.legal_basis.join("; ") || severanceLocal.legalBasis,
    };
  }, [sevB.data, severanceLocal]);

  const deadlineResult = useMemo(() => {
    const r = dlB.data?.result;
    if (!r) return deadlineLocal;
    const days = typeof r.period === "string" ? parseInt(r.period, 10) : NaN;
    return {
      ...deadlineLocal,
      canAppeal: r.appealable === false ? false : typeof r.deadline === "string",
      appealDays: Number.isFinite(days) ? days : deadlineLocal.appealDays,
      expiryDateStr: typeof r.deadline === "string" ? r.deadline : deadlineLocal.expiryDateStr,
      governingLaw: dlB.data!.legal_basis.join("; ") || deadlineLocal.governingLaw,
    };
  }, [dlB.data, deadlineLocal]);

  const inheritanceResult = useMemo(() => {
    const r = inhB.data?.result;
    if (!r) return inheritanceLocal;
    const amt = (k: string) => num(r[`${k}_amount`]);
    const frac = (k: string) => (typeof r[k] === "string" ? (r[k] as string) : undefined);
    const spouseKey = spouseType === "husband" ? "husband" : "wives (shared equally)";
    const sonsAmt = amt("sons") ?? 0;
    const dauAmt = amt("daughters") ?? 0;
    return {
      ...inheritanceLocal,
      spouseLabel: frac(spouseKey) ?? inheritanceLocal.spouseLabel,
      motherShare: frac("mother") ?? inheritanceLocal.motherShare,
      fatherShare: frac("father") ?? inheritanceLocal.fatherShare,
      spouseAmount: Math.round(amt(spouseKey) ?? 0),
      motherAmount: Math.round(amt("mother") ?? 0),
      fatherAmount: Math.round(amt("father") ?? 0),
      childrenAmount: Math.round(sonsAmt + dauAmt),
      sonEachAmount: numSons > 0 ? Math.round(sonsAmt / numSons) : 0,
      daughterEachAmount: numDaughters > 0 ? Math.round(dauAmt / numDaughters) : 0,
      legalBasis: inhB.data!.legal_basis.join("; ") || inheritanceLocal.legalBasis,
    };
  }, [inhB.data, inheritanceLocal, spouseType, numSons, numDaughters]);

  const activeB: BackendCalc =
    activeTab === "smig" ? smigB : activeTab === "cash_duty" ? cashB : activeTab === "severance" ? sevB : activeTab === "deadlines" ? dlB : inhB;

  if (!isOpen) return null;

  const handleCopyWorkedMath = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getActiveWorkedText = (): string => {
    if (EXTRA_TABS.includes(activeTab)) return extraText;
    if (activeTab === "smig") {
      return `[CALCUL LÉGAL SMIG/SMAG - MAROC]\nDate d'application : ${wageDate}\nTaux minimum légal : ${smigResult.rate} MAD/h (${smigResult.legalDecree})\nHeures mensuelles : ${monthlyHours}h\nSalaire minimum légal obligatoire : ${smigResult.standardMonthly} MAD\nSalaire effectif constaté : ${smigResult.actualMonthly} MAD\nStatut de conformité : ${smigResult.complies ? "CONFORME" : `NON CONFORME (Déficit : ${smigResult.deficit} MAD/mois)`}`;
    }
    if (activeTab === "cash_duty") {
      return `[SURTAXE 2% LIQUIDITÉS IMMOBILIER - CGI ART. 133 / LOI 50-25]\nDate de l'acte : ${dutyDate}\nPrix de cession : ${propertyPrice.toLocaleString()} MAD\nPart payée par virement/chèque : ${cashDutyResult.bankPortion.toLocaleString()} MAD (Exemptée de surtaxe)\nPart payée en espèces : ${cashAmount.toLocaleString()} MAD\nDroits de base (${cashDutyResult.baseRatePercent}%) : ${cashDutyResult.baseDuty.toLocaleString()} MAD\nSurtaxe espèces 2% (Art. 133 CGI) : ${cashDutyResult.cashSurcharge.toLocaleString()} MAD\nTotal droits d'enregistrement exigibles : ${cashDutyResult.totalDuty.toLocaleString()} MAD`;
    }
    if (activeTab === "severance") {
      return `[INDEMNITÉ DE LICENCIEMENT & PRÉAVIS - LOI 65-99 ART. 51-53]\nAncienneté : ${seniorityYears} ans | Salaire mensuel : ${monthlySalary} MAD (Base horaire : ${severanceResult.hourlyBase} MAD/h)\nHeures cumulées indemnisables : ${severanceResult.totalHours} heures\nIndemnité légale de licenciement : ${severanceResult.severanceIndemnity.toLocaleString()} MAD\nIndemnité de préavis (${severanceResult.noticeMonths} mois) : ${severanceResult.noticeIndemnity.toLocaleString()} MAD\nTotal minimum légal garanti : ${severanceResult.totalLegalCompensation.toLocaleString()} MAD`;
    }
    if (activeTab === "deadlines") {
      return `[DÉLAI DE RECOURS & INAPPELLABILITÉ - ${deadlineResult.governingLaw}]\nMontant du litige : ${claimAmount.toLocaleString()} MAD\nSeuil d'inappellabilité applicable : ${deadlineResult.threshold.toLocaleString()} MAD\nRecevabilité de l'appel : ${deadlineResult.canAppeal ? "APPEL RECEVABLE" : "JUGEMENT EN DERNIER RESSORT (Pas d'appel)"}\nDélai de recours : ${deadlineResult.appealDays} jours\nDate limite de dépôt de recours : ${deadlineResult.expiryDateStr}`;
    }
    return `[PARTAGE SUCCESSORAL (IRTH) - MOUDAWANA LIVRE VI]\nPatrimoine total : ${totalEstate.toLocaleString()} MAD\nConjoint (${spouseType}) : ${inheritanceResult.spouseAmount.toLocaleString()} MAD (${inheritanceResult.spouseLabel})\nMère : ${inheritanceResult.motherAmount.toLocaleString()} MAD (${inheritanceResult.motherShare})\nPère : ${inheritanceResult.fatherAmount.toLocaleString()} MAD (${inheritanceResult.fatherShare})\nEnfants (Asaba résiduaire) : ${inheritanceResult.childrenAmount.toLocaleString()} MAD (Part garçon : ${inheritanceResult.sonEachAmount.toLocaleString()} MAD, Part fille : ${inheritanceResult.daughterEachAmount.toLocaleString()} MAD)`;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-black/45 backdrop-blur-xs animate-in fade-in duration-150">
      <div
        className="w-full max-w-3xl max-h-[92vh] flex flex-col rounded-2xl border shadow-2xl overflow-hidden sanad-liquid-modal"
        style={{
          backgroundColor: "var(--bg-surface)",
          borderColor: "var(--border-strong)",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-3.5 border-b shrink-0"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <div className="flex items-center gap-2.5">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{
                backgroundColor: "var(--bg-card)",
                color: "var(--accent-primary)",
              }}
            >
              <Calculator className="w-4 h-4" />
            </div>
            <div>
              <h2
                className="font-editorial text-base font-semibold"
                style={{ color: "var(--text-heading)" }}
              >
                {tr("Calculateurs Juridiques Vérifiés (Droit Marocain)")}
              </h2>
              <p className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                {tr("Calculs déterministes par code testé · Textes BO officiels · Aucune approximation LLM")}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg hover:opacity-70 transition-opacity cursor-pointer"
            style={{ color: "var(--text-muted)" }}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Selection */}
        <div
          className="flex items-center gap-1 px-5 pt-3 border-b overflow-x-auto scrollbar-none shrink-0"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <button
            type="button"
            onClick={() => setActiveTab("smig")}
            className={`px-3 py-2 rounded-t-lg text-xs font-medium border-b-2 transition-colors cursor-pointer shrink-0 flex items-center gap-1.5 ${
              activeTab === "smig" ? "border-[var(--accent-primary)] font-semibold" : "border-transparent opacity-75"
            }`}
            style={{
              color: activeTab === "smig" ? "var(--accent-primary)" : "var(--text-primary)",
            }}
          >
            <DollarSign className="w-3.5 h-3.5" />
            <span>{tr("SMIG / SMAG 2026")}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("cash_duty")}
            className={`px-3 py-2 rounded-t-lg text-xs font-medium border-b-2 transition-colors cursor-pointer shrink-0 flex items-center gap-1.5 ${
              activeTab === "cash_duty" ? "border-[var(--accent-primary)] font-semibold" : "border-transparent opacity-75"
            }`}
            style={{
              color: activeTab === "cash_duty" ? "var(--accent-primary)" : "var(--text-primary)",
            }}
          >
            <Scale className="w-3.5 h-3.5" />
            <span>{tr("Surtaxe 2% Espèces")}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("severance")}
            className={`px-3 py-2 rounded-t-lg text-xs font-medium border-b-2 transition-colors cursor-pointer shrink-0 flex items-center gap-1.5 ${
              activeTab === "severance" ? "border-[var(--accent-primary)] font-semibold" : "border-transparent opacity-75"
            }`}
            style={{
              color: activeTab === "severance" ? "var(--accent-primary)" : "var(--text-primary)",
            }}
          >
            <Briefcase className="w-3.5 h-3.5" />
            <span>{tr("Licenciement & Préavis")}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("deadlines")}
            className={`px-3 py-2 rounded-t-lg text-xs font-medium border-b-2 transition-colors cursor-pointer shrink-0 flex items-center gap-1.5 ${
              activeTab === "deadlines" ? "border-[var(--accent-primary)] font-semibold" : "border-transparent opacity-75"
            }`}
            style={{
              color: activeTab === "deadlines" ? "var(--accent-primary)" : "var(--text-primary)",
            }}
          >
            <Calendar className="w-3.5 h-3.5" />
            <span>{tr("Délais CPC (Loi 58.25)")}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("inheritance")}
            className={`px-3 py-2 rounded-t-lg text-xs font-medium border-b-2 transition-colors cursor-pointer shrink-0 flex items-center gap-1.5 ${
              activeTab === "inheritance" ? "border-[var(--accent-primary)] font-semibold" : "border-transparent opacity-75"
            }`}
            style={{
              color: activeTab === "inheritance" ? "var(--accent-primary)" : "var(--text-primary)",
            }}
          >
            <Users className="w-3.5 h-3.5" />
            <span>{tr("Succession (Moudawana)")}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("arrears")}
            className={`px-3 py-2 rounded-t-lg text-xs font-medium border-b-2 transition-colors cursor-pointer shrink-0 flex items-center gap-1.5 ${
              activeTab === "arrears" ? "border-[var(--accent-primary)] font-semibold" : "border-transparent opacity-75"
            }`}
            style={{ color: activeTab === "arrears" ? "var(--accent-primary)" : "var(--text-primary)" }}
          >
            <span>{tr("Salaire impayé (rappel)")}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("salary")}
            className={`px-3 py-2 rounded-t-lg text-xs font-medium border-b-2 transition-colors cursor-pointer shrink-0 flex items-center gap-1.5 ${
              activeTab === "salary" ? "border-[var(--accent-primary)] font-semibold" : "border-transparent opacity-75"
            }`}
            style={{ color: activeTab === "salary" ? "var(--accent-primary)" : "var(--text-primary)" }}
          >
            <span>{tr("Salaire 2026–2031")}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("limitation")}
            className={`px-3 py-2 rounded-t-lg text-xs font-medium border-b-2 transition-colors cursor-pointer shrink-0 flex items-center gap-1.5 ${
              activeTab === "limitation" ? "border-[var(--accent-primary)] font-semibold" : "border-transparent opacity-75"
            }`}
            style={{ color: activeTab === "limitation" ? "var(--accent-primary)" : "var(--text-primary)" }}
          >
            <span>{tr("Prescription")}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("tax")}
            className={`px-3 py-2 rounded-t-lg text-xs font-medium border-b-2 transition-colors cursor-pointer shrink-0 flex items-center gap-1.5 ${
              activeTab === "tax" ? "border-[var(--accent-primary)] font-semibold" : "border-transparent opacity-75"
            }`}
            style={{ color: activeTab === "tax" ? "var(--accent-primary)" : "var(--text-primary)" }}
          >
            <span>{tr("Impôts (barèmes)")}</span>
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* TAB 1: SMIG / SMAG 2026 */}
          {activeTab === "smig" && (
            <div className="space-y-4">
              <div
                className="p-3.5 rounded-xl border flex items-start gap-2.5 text-xs"
                style={{
                  backgroundColor: "var(--bg-canvas)",
                  borderColor: "var(--border-subtle)",
                }}
              >
                <Info className="w-4 h-4 shrink-0 mt-0.5" style={{ color: "var(--accent-primary)" }} />
                <div>
                  <div className="font-semibold" style={{ color: "var(--text-heading)" }}>
                    {smigResult.legalDecree}
                  </div>
                  <p className="mt-0.5 opacity-85" style={{ color: "var(--text-muted)" }}>
                    {tr("Dès le 1er Janvier 2026, le SMIG horaire s'élève à")} <strong>{tr("17,92 MAD/h")}</strong> {tr("(contre 17,10 MAD en 2025). Le SMAG agricole passe à")} <strong>{tr("97,44 MAD/jour")}</strong> {tr("au 1er Avril 2026 (contre 93 MAD en 2025).")}
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Secteur d'activité")}
                  </label>
                  <select
                    value={wageSector}
                    onChange={(e) => setWageSector(e.target.value as "smig" | "smag")}
                    className="w-full px-3 py-2 rounded-lg border text-xs bg-transparent"
                    style={{ borderColor: "var(--border-strong)" }}
                  >
                    <option value="smig">{tr("Industrie / Commerce / Services (SMIG)")}</option>
                    <option value="smag">{tr("Agriculture / Forêt (SMAG)")}</option>
                  </select>
                </div>

                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Date d'exigibilité")}
                  </label>
                  <input
                    type="date"
                    value={wageDate}
                    onChange={(e) => setWageDate(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border text-xs bg-transparent"
                    style={{ borderColor: "var(--border-strong)" }}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Taux horaire convenu (MAD)")}
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={hourlyWage}
                    onChange={(e) => setHourlyWage(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg border text-xs bg-transparent"
                    style={{ borderColor: "var(--border-strong)" }}
                  />
                </div>
              </div>

              {/* Result Card */}
              <div
                className="p-4 rounded-xl border space-y-3"
                style={{
                  backgroundColor: "var(--bg-card)",
                  borderColor: smigResult.complies ? "var(--border-strong)" : "var(--accent-primary)",
                }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Résultat de conformité salariale")}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider ${
                      smigResult.complies ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"
                    }`}
                  >
                    {smigResult.complies ? tr("Conforme au SMIG") : tr("Inférieur au SMIG légal")}
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 font-code">
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Taux Légal (")}{wageDate.slice(0, 4)})</div>
                    <div className="text-sm font-bold text-[var(--text-heading)]">{smigResult.rate} {tr("MAD/h")}</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Minimum Mensuel (191h)")}</div>
                    <div className="text-sm font-bold text-[var(--text-heading)]">{smigResult.standardMonthly} {tr("MAD")}</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Salaire Constaté")}</div>
                    <div className="text-sm font-bold text-[var(--text-heading)]">{smigResult.actualMonthly} {tr("MAD")}</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Écart / Déficit")}</div>
                    <div className={`text-sm font-bold ${smigResult.deficit > 0 ? "text-red-700" : "text-emerald-700"}`}>
                      {smigResult.deficit > 0 ? tr("-{0} MAD", [smigResult.deficit]) : tr("0 MAD")}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: 2% CASH SURCHARGE */}
          {activeTab === "cash_duty" && (
            <div className="space-y-4">
              <div
                className="p-3.5 rounded-xl border flex items-start gap-2.5 text-xs"
                style={{
                  backgroundColor: "var(--bg-canvas)",
                  borderColor: "var(--border-subtle)",
                }}
              >
                <Info className="w-4 h-4 shrink-0 mt-0.5" style={{ color: "var(--accent-primary)" }} />
                <div>
                  <div className="font-semibold" style={{ color: "var(--text-heading)" }}>
                    {tr("Loi de Finances 50-25 / CGI Art. 133")}
                  </div>
                  <p className="mt-0.5 opacity-85" style={{ color: "var(--text-muted)" }}>
                    {tr("À compter du")} <strong>{tr("1er Juillet 2026")}</strong>{tr(", toute quote-part payée en espèces lors d'une transaction immobilière est assujettie à une")} <strong>{tr("surtaxe de 2%")}</strong> {tr("en plus des droits d'enregistrement ordinaires (4%). Les paiements par virement ou chèque bancaire en sont exemptés.")}
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Prix de vente total (MAD)")}
                  </label>
                  <input
                    type="number"
                    value={propertyPrice}
                    onChange={(e) => setPropertyPrice(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg border text-xs bg-transparent"
                    style={{ borderColor: "var(--border-strong)" }}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Quote-part en espèces (MAD)")}
                  </label>
                  <input
                    type="number"
                    value={cashAmount}
                    onChange={(e) => setCashAmount(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg border text-xs bg-transparent"
                    style={{ borderColor: "var(--border-strong)" }}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Date de signature de l'acte")}
                  </label>
                  <input
                    type="date"
                    value={dutyDate}
                    onChange={(e) => setDutyDate(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border text-xs bg-transparent"
                    style={{ borderColor: "var(--border-strong)" }}
                  />
                </div>
              </div>

              {/* Result Card */}
              <div
                className="p-4 rounded-xl border space-y-3 font-code"
                style={{
                  backgroundColor: "var(--bg-card)",
                  borderColor: "var(--border-strong)",
                }}
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Décomposition fiscale des droits")}
                  </span>
                  <span className="text-[11px] px-2 py-0.5 rounded bg-[var(--bg-surface)] font-bold text-[var(--accent-primary)]">
                    {cashDutyResult.isAfterJuly2026 ? tr("Régime 2026 (Surtaxe 2% Active)") : tr("Régime Antérieur (Pas de 2%)")}
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-1">
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Droits ordinaires (4%)")}</div>
                    <div className="text-sm font-bold text-[var(--text-heading)]">
                      {cashDutyResult.baseDuty.toLocaleString()} {tr("MAD")}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Surtaxe 2% Espèces")}</div>
                    <div className="text-sm font-bold text-red-700">
                      +{cashDutyResult.cashSurcharge.toLocaleString()} {tr("MAD")}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Total Droits d'Enregistrement")}</div>
                    <div className="text-sm font-bold text-[var(--accent-primary)]">
                      {cashDutyResult.totalDuty.toLocaleString()} {tr("MAD")}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: SEVERANCE & NOTICE */}
          {activeTab === "severance" && (
            <div className="space-y-4">
              <div
                className="p-3.5 rounded-xl border flex items-start gap-2.5 text-xs"
                style={{
                  backgroundColor: "var(--bg-canvas)",
                  borderColor: "var(--border-subtle)",
                }}
              >
                <Info className="w-4 h-4 shrink-0 mt-0.5" style={{ color: "var(--accent-primary)" }} />
                <div>
                  <div className="font-semibold" style={{ color: "var(--text-heading)" }}>
                    {tr("Code du Travail marocain (Loi 65-99 - Art. 51 à 53)")}
                  </div>
                  <p className="mt-0.5 opacity-85" style={{ color: "var(--text-muted)" }}>
                    {tr("L'indemnité légale de licenciement se calcule par tranche horaire de salaire (96h pour 1-5 ans, 144h pour 6-10 ans, 192h pour 11-15 ans, 240h au-delà), cumulée avec le préavis légal garanti.")}
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Ancienneté révolue (années)")}
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="45"
                    value={seniorityYears}
                    onChange={(e) => setSeniorityYears(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg border text-xs bg-transparent"
                    style={{ borderColor: "var(--border-strong)" }}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Salaire brut mensuel (MAD)")}
                  </label>
                  <input
                    type="number"
                    value={monthlySalary}
                    onChange={(e) => setMonthlySalary(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg border text-xs bg-transparent"
                    style={{ borderColor: "var(--border-strong)" }}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Statut professionnel")}
                  </label>
                  <select
                    value={employeeCategory}
                    onChange={(e) => setEmployeeCategory(e.target.value as "non_cadre" | "cadre")}
                    className="w-full px-3 py-2 rounded-lg border text-xs bg-transparent"
                    style={{ borderColor: "var(--border-strong)" }}
                  >
                    <option value="non_cadre">{tr("Employé / Ouvrier (Non Cadre)")}</option>
                    <option value="cadre">{tr("Cadre / Responsable de Département")}</option>
                  </select>
                </div>
              </div>

              {/* Result Card */}
              <div
                className="p-4 rounded-xl border space-y-3 font-code"
                style={{
                  backgroundColor: "var(--bg-card)",
                  borderColor: "var(--border-strong)",
                }}
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Décompte des indemnités légales")}
                  </span>
                  <span className="text-[11px] text-[var(--text-muted)]">
                    {tr("Base horaire :")} {severanceResult.hourlyBase} {tr("MAD/h")}
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-1">
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Licenciement (")}{severanceResult.totalHours}h)</div>
                    <div className="text-sm font-bold text-[var(--text-heading)]">
                      {severanceResult.severanceIndemnity.toLocaleString()} {tr("MAD")}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Préavis (")}{severanceResult.noticeMonths} {tr("mois)")}</div>
                    <div className="text-sm font-bold text-[var(--text-heading)]">
                      {severanceResult.noticeIndemnity.toLocaleString()} {tr("MAD")}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Total Indemnités Garanties")}</div>
                    <div className="text-sm font-bold text-[var(--accent-primary)]">
                      {severanceResult.totalLegalCompensation.toLocaleString()} {tr("MAD")}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: PROCEDURAL DEADLINES */}
          {activeTab === "deadlines" && (
            <div className="space-y-4">
              <div
                className="p-3.5 rounded-xl border flex items-start gap-2.5 text-xs"
                style={{
                  backgroundColor: "var(--bg-canvas)",
                  borderColor: "var(--border-subtle)",
                }}
              >
                <Info className="w-4 h-4 shrink-0 mt-0.5" style={{ color: "var(--accent-primary)" }} />
                <div>
                  <div className="font-semibold" style={{ color: "var(--text-heading)" }}>
                    {tr("Seuil d'Appel CPC : 1974 vs Loi 58.25 (2026)")}
                  </div>
                  <p className="mt-0.5 opacity-85" style={{ color: "var(--text-muted)" }}>
                    {tr("Avec la nouvelle Loi 58.25 en vigueur le")} <strong>{tr("24 Août 2026")}</strong>{tr(", le seuil des jugements rendus en premier et dernier ressort (sans appel possible) passe de")} <strong>{tr("5.000 MAD à 10.000 MAD")}</strong>.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Montant de la demande (MAD)")}
                  </label>
                  <input
                    type="number"
                    value={claimAmount}
                    onChange={(e) => setClaimAmount(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg border text-xs bg-transparent"
                    style={{ borderColor: "var(--border-strong)" }}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Date de notification du jugement")}
                  </label>
                  <input
                    type="date"
                    value={notificationDate}
                    onChange={(e) => setNotificationDate(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg border text-xs bg-transparent"
                    style={{ borderColor: "var(--border-strong)" }}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Type de jugement")}
                  </label>
                  <select
                    value={procedureType}
                    onChange={(e) => setProcedureType(e.target.value as "standard" | "refere")}
                    className="w-full px-3 py-2 rounded-lg border text-xs bg-transparent"
                    style={{ borderColor: "var(--border-strong)" }}
                  >
                    <option value="standard">{tr("Jugement au fond (30 jours)")}</option>
                    <option value="refere">{tr("Ordonnance de référé (15 jours)")}</option>
                  </select>
                </div>
              </div>

              {/* Result Card */}
              <div
                className="p-4 rounded-xl border space-y-3 font-code"
                style={{
                  backgroundColor: "var(--bg-card)",
                  borderColor: deadlineResult.canAppeal ? "var(--border-strong)" : "var(--accent-primary)",
                }}
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Recevabilité de la voie d'appel")}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider ${
                      deadlineResult.canAppeal ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {deadlineResult.canAppeal ? tr("Appel recevable") : tr("Inappelable (Dernier Ressort)")}
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-1">
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Régime Procédural")}</div>
                    <div className="text-xs font-bold text-[var(--text-heading)]">{deadlineResult.governingLaw}</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Délai d'Appel Légal")}</div>
                    <div className="text-xs font-bold text-[var(--text-heading)]">{deadlineResult.appealDays} {tr("jours francs")}</div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Date d'Expiration")}</div>
                    <div className="text-xs font-bold text-[var(--accent-primary)]">
                      {deadlineResult.canAppeal ? deadlineResult.expiryDateStr : tr("Pas de recours ordinaire")}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 5: INHERITANCE (MOUDAWANA) */}
          {activeTab === "inheritance" && (
            <div className="space-y-4">
              <div
                className="p-3.5 rounded-xl border flex items-start gap-2.5 text-xs"
                style={{
                  backgroundColor: "var(--bg-canvas)",
                  borderColor: "var(--border-subtle)",
                }}
              >
                <Info className="w-4 h-4 shrink-0 mt-0.5" style={{ color: "var(--accent-primary)" }} />
                <div>
                  <div className="font-semibold" style={{ color: "var(--text-heading)" }}>
                    {tr("Moudawana (Loi 70.03 - Livre VI des Successions)")}
                  </div>
                  <p className="mt-0.5 opacity-85" style={{ color: "var(--text-muted)" }}>
                    {tr("Calcul symbolique déterministe conforme aux règles coraniques des quotités fixes (Fard) et du reliquat résiduaire (Asaba). Note : Réforme de la Moudawana en cours d'examen législatif.")}
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Conjoint survivant")}
                  </label>
                  <select
                    value={spouseType}
                    onChange={(e) => setSpouseType(e.target.value as "none" | "husband" | "wife")}
                    className="w-full px-3 py-2 rounded-lg border text-xs bg-transparent"
                    style={{ borderColor: "var(--border-strong)" }}
                  >
                    <option value="wife">{tr("Épouse (Veuve)")}</option>
                    <option value="husband">{tr("Époux (Veuf)")}</option>
                    <option value="none">{tr("Aucun conjoint")}</option>
                  </select>
                </div>

                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Nombre de fils")}
                  </label>
                  <input
                    type="number"
                    min="0"
                    value={numSons}
                    onChange={(e) => setNumSons(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg border text-xs bg-transparent"
                    style={{ borderColor: "var(--border-strong)" }}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Nombre de filles")}
                  </label>
                  <input
                    type="number"
                    min="0"
                    value={numDaughters}
                    onChange={(e) => setNumDaughters(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg border text-xs bg-transparent"
                    style={{ borderColor: "var(--border-strong)" }}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Actif net successoral (MAD)")}
                  </label>
                  <input
                    type="number"
                    value={totalEstate}
                    onChange={(e) => setTotalEstate(Number(e.target.value))}
                    className="w-full px-3 py-2 rounded-lg border text-xs bg-transparent"
                    style={{ borderColor: "var(--border-strong)" }}
                  />
                </div>
              </div>

              {/* Result Card */}
              <div
                className="p-4 rounded-xl border space-y-3 font-code"
                style={{
                  backgroundColor: "var(--bg-card)",
                  borderColor: "var(--border-strong)",
                }}
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                    {tr("Répartition des parts successorales")}
                  </span>
                  <span className="text-[11px] font-bold text-[var(--accent-primary)]">
                    {tr("Actif :")} {totalEstate.toLocaleString()} {tr("MAD")}
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Conjoint (")}{inheritanceResult.spouseLabel})</div>
                    <div className="text-xs font-bold text-[var(--text-heading)]">
                      {inheritanceResult.spouseAmount.toLocaleString()} {tr("MAD")}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Mère (")}{inheritanceResult.motherShare})</div>
                    <div className="text-xs font-bold text-[var(--text-heading)]">
                      {inheritanceResult.motherAmount.toLocaleString()} {tr("MAD")}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Part unitaire par Fils")}</div>
                    <div className="text-xs font-bold text-[var(--accent-primary)]">
                      {inheritanceResult.sonEachAmount.toLocaleString()} {tr("MAD")}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[var(--text-muted)]">{tr("Part unitaire par Fille")}</div>
                    <div className="text-xs font-bold text-[var(--accent-primary)]">
                      {inheritanceResult.daughterEachAmount.toLocaleString()} {tr("MAD")}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === "arrears" && <WageArrearsTab isOpen={isOpen} active asOfDate={currentAsOfDate} onText={setExtraText} />}
          {activeTab === "salary" && <SalaryProjectionTab isOpen={isOpen} active asOfDate={currentAsOfDate} onText={setExtraText} />}
          {activeTab === "limitation" && <LimitationTab isOpen={isOpen} active asOfDate={currentAsOfDate} onText={setExtraText} />}
          {activeTab === "tax" && <TaxTab isOpen={isOpen} active asOfDate={currentAsOfDate} onText={setExtraText} />}
        </div>

        {/* Backend calculation trace */}
        {!EXTRA_TABS.includes(activeTab) && (
        <div className="px-5 py-2 border-t text-[11px] shrink-0" style={{ borderColor: "var(--border-subtle)", color: "var(--text-muted)" }}>
          {activeB.loading && <span>{tr("Calcul via le serveur local…")}</span>}
          {!activeB.loading && activeB.error && (
            <span>{explainError(activeB.error)} {tr("Estimation locale affichée.")}</span>
          )}
          {!activeB.loading && activeB.data && (
            <details>
              <summary className="cursor-pointer">
                {tr("Calcul certifié par le serveur :")} {activeB.data.verification === "unverified" ? tr("non vérifié contre un exemple officiel") : activeB.data.verification}
              </summary>
              <div className="mt-1 space-y-0.5">
                <div>{tr("Formule :")} {activeB.data.formula}</div>
                {activeB.data.steps.map((st, i) => <div key={i}>• {st}</div>)}
                <div>{tr("Base légale :")} {activeB.data.legal_basis.join("; ")}</div>
                {activeB.data.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
                {(activeB.data.articles || []).length > 0 && (
                  <div className="mt-2 space-y-1.5">
                    <div className="font-semibold" style={{ color: "var(--text-heading)" }}>{tr("La loi derrière ce calcul (citée du pack) :")}</div>
                    {(activeB.data.articles || []).map((a) => (
                      <div key={a.provision_id} className="p-2 rounded-lg border" style={{ backgroundColor: "var(--bg-card)", borderColor: "var(--border-subtle)" }}>
                        <div className="font-medium" style={{ color: "var(--text-heading)" }}>{a.law_short || a.law}, {tr("Art.")} {a.number}{a.why ? ` — ${a.why}` : ""}</div>
                        <div dir="rtl" className="mt-0.5">{a.text}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </details>
          )}
        </div>
        )}

        {/* Footer Actions */}
        <div
          className="flex items-center justify-between px-5 py-3.5 border-t shrink-0"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <button
            type="button"
            onClick={() => handleCopyWorkedMath(getActiveWorkedText())}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium hover:opacity-85 cursor-pointer"
            style={{
              backgroundColor: "var(--bg-canvas)",
              borderColor: "var(--border-subtle)",
              color: "var(--text-heading)",
            }}
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copied ? tr("Calcul copié !") : tr("Copier le détail du calcul")}</span>
          </button>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3.5 py-1.5 rounded-lg border text-xs font-medium hover:opacity-85 cursor-pointer"
              style={{
                backgroundColor: "var(--bg-surface)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-muted)",
              }}
            >
              {tr("Fermer")}
            </button>

            <button
              type="button"
              onClick={() => {
                onAttachCalculationToPrompt(getActiveWorkedText());
                onClose();
              }}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium hover:opacity-90 cursor-pointer shadow-xs"
              style={{
                backgroundColor: "var(--accent-primary)",
                color: "var(--accent-primary-fg)",
              }}
            >
              <span>{tr("Insérer dans la question")}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
