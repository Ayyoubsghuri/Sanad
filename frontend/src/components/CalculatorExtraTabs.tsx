import React, { useEffect, useMemo, useState } from "react";
import { tr } from "../i18n";
import { AlertTriangle, Info } from "lucide-react";
import { useBackendCalc, type BackendCalc } from "../api/useBackendCalc";
import { useBackendGet } from "../api/useBackendList";

const fmt = (n: number | undefined | null, d = 2) =>
  typeof n === "number" ? n.toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d }) : "-";
const label = "text-[11px] font-semibold uppercase tracking-wider";
const inputCls = "w-full px-3 py-2 rounded-lg border text-xs bg-transparent";
const border = { borderColor: "var(--border-strong)" } as const;

export const noPackHint = () =>
  tr("Le serveur local n'a pas de pack de lois. Lancez : legalrag-build fixture --out fixture.db, puis définissez LEGALRAG_LAWPACK_PATH=fixture.db et LEGALRAG_ALLOW_UNSIGNED_PACK=true avant de démarrer legalrag.");

export function explainError(err: string | null): string | null {
  if (!err) return null;
  return /no law pack|pack_unavailable|503/i.test(err) ? noPackHint() : err;
}

/** Collapsible trace: formula, steps, legal basis, warnings, verification level (all from the backend). */
export const TracePanel: React.FC<{ b: BackendCalc }> = ({ b }) => (
  <div className="text-[11px] space-y-1" style={{ color: "var(--text-muted)" }}>
    {b.loading && <div>{tr("Calcul via le serveur local…")}</div>}
    {!b.loading && b.error && (
      <div className="flex items-start gap-1.5" style={{ color: "var(--accent-warm)" }}>
        <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
        <span>{explainError(b.error)}</span>
      </div>
    )}
    {!b.loading && b.data && (
      <details>
        <summary className="cursor-pointer">
          {tr("Calcul du serveur :")} {b.data.verification === "unverified" ? tr("non vérifié contre un exemple officiel") : b.data.verification}
        </summary>
        <div className="mt-1 space-y-0.5">
          <div>{tr("Formule :")} {b.data.formula}</div>
          {b.data.steps.map((st, i) => <div key={i}>• {st}</div>)}
          <div>{tr("Base légale :")} {b.data.legal_basis.join("; ")}</div>
          {b.data.table_rows.length > 0 && (
            <div>
              {tr("Lignes de barème utilisées :")}{" "}
              {b.data.table_rows.map((r) => tr("{0} {1} (dès {2})", [String((r as { key?: string }).key ?? ""), String((r as { value?: unknown }).value ?? ""), String((r as { valid_from?: string }).valid_from ?? "")])).join(" ; ")}
            </div>
          )}
          {b.data.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
          {(b.data.articles || []).length > 0 && (
            <div className="mt-2 space-y-1.5">
              <div className="font-semibold" style={{ color: "var(--text-heading)" }}>{tr("La loi derrière ce calcul (citée du pack) :")}</div>
              {(b.data.articles || []).map((a) => (
                <div key={a.provision_id} className="p-2 rounded-lg border" style={{ backgroundColor: "var(--bg-card)", borderColor: "var(--border-subtle)" }}>
                  <div className="font-medium" style={{ color: "var(--text-heading)" }}>{a.law_short || a.law}, {tr("Art.")} {a.number}</div>
                  <div dir="rtl" className="mt-0.5 text-[12px] leading-relaxed" style={{ color: "var(--text-primary)" }}>{a.text}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </details>
    )}
  </div>
);

const Banner: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="p-3.5 rounded-xl border flex items-start gap-2.5 text-xs" style={{ backgroundColor: "var(--bg-canvas)", borderColor: "var(--border-subtle)" }}>
    <Info className="w-4 h-4 shrink-0 mt-0.5" style={{ color: "var(--accent-primary)" }} />
    <div>
      <div className="font-semibold" style={{ color: "var(--text-heading)" }}>{title}</div>
      <p className="mt-0.5 opacity-85" style={{ color: "var(--text-muted)" }}>{children}</p>
    </div>
  </div>
);

// ============================================================================================================ salary 2026-2031
interface YearRow {
  year: number;
  basis: "decree" | "carried_forward" | "scenario" | "no_rate" | "local";
  rate?: number;
  rate_unit?: string;
  minimum_monthly?: number;
  contract_monthly?: number;
  gap_monthly?: number;
  compliant?: boolean;
  shortfall_annual?: number;
  severance_prorata?: number;
  severance_full_year?: number;
  severance_note?: string;
  note?: string;
}
const basisLabel = (b: string): string =>
  ({
    decree: tr("Décret en vigueur"),
    carried_forward: tr("Maintenu (pas de décret)"),
    scenario: tr("Scénario"),
    local: tr("Estimation locale"),
    no_rate: tr("Pas de taux"),
  } as Record<string, string>)[b] ?? b;

/** Used only when the backend is unreachable: 2026 rates carried forward, clearly labelled as a local estimate. */
function localProjection(o: { startYear: number; endYear: number; sector: string; pay: number; hours: number; days: number; raise: number; growth: number }): YearRow[] {
  const out: YearRow[] = [];
  for (let y = o.startYear; y <= o.endYear; y++) {
    const base = o.sector === "non_agricultural" ? 17.92 : y === 2026 ? (3 * 93 + 9 * 97.44) / 12 : 97.44;
    const rate = base * (1 + o.growth / 100) ** Math.max(0, y - 2026);
    const min = rate * (o.sector === "non_agricultural" ? o.hours : o.days);
    const contract = o.pay * (1 + o.raise / 100) ** (y - o.startYear);
    out.push({
      year: y, basis: "local", rate, rate_unit: o.sector === "non_agricultural" ? "MAD/heure" : "MAD/jour",
      minimum_monthly: Math.round(min * 100) / 100, contract_monthly: Math.round(contract * 100) / 100,
      gap_monthly: Math.round((contract - min) * 100) / 100, compliant: contract >= min,
      shortfall_annual: Math.round(Math.max(0, min - contract) * 12 * 100) / 100,
    });
  }
  return out;
}

export const SalaryProjectionTab: React.FC<{ isOpen: boolean; active: boolean; asOfDate: string; onText: (t: string) => void }> = ({ isOpen, active, asOfDate, onText }) => {
  const [sector, setSector] = useState<"non_agricultural" | "agricultural">("non_agricultural");
  const [pay, setPay] = useState(3500);
  const [hours, setHours] = useState(191);
  const [days, setDays] = useState(26);
  const [startYear, setStartYear] = useState(2026);
  const [endYear, setEndYear] = useState(2031);
  const [raise, setRaise] = useState(0);
  const [growth, setGrowth] = useState(0);
  const [hired, setHired] = useState("");
  const years = [2026, 2027, 2028, 2029, 2030, 2031];

  const inputs = useMemo(
    () => ({
      start_year: startYear,
      end_year: Math.max(startYear, endYear),
      sector,
      monthly_pay: pay,
      hours_per_month: hours,
      days_per_month: days,
      annual_raise_pct: raise,
      smig_growth_pct: growth,
      ...(hired ? { employment_start_date: hired } : {}),
    }),
    [startYear, endYear, sector, pay, hours, days, raise, growth, hired]
  );
  const calc = useBackendCalc("salary_projection", inputs, isOpen && active);
  const server = calc.data?.result as { years?: YearRow[]; first_non_compliant_year?: number | null; latest_decree_year?: number } | undefined;
  const rows: YearRow[] = server?.years ?? localProjection({ startYear, endYear: Math.max(startYear, endYear), sector, pay, hours, days, raise, growth });
  const firstBad = server ? server.first_non_compliant_year : rows.find((r) => r.compliant === false)?.year ?? null;
  const isLocal = !server;
  const showSev = !!hired && rows.some((r) => r.severance_prorata !== undefined);

  const text = useMemo(() => {
    const head = `[SALAIRE ET SALAIRE MINIMUM LÉGAL ${startYear}-${Math.max(startYear, endYear)} - ${sector === "non_agricultural" ? "SMIG" : "SMAG"}]\nSalaire mensuel convenu en ${startYear} : ${fmt(pay)} MAD | hausse annuelle ${raise}% | scénario SMIG ${growth}%/an après le dernier décret${isLocal ? "\n(estimation locale: serveur indisponible)" : ""}`;
    const lines = rows.map((r) =>
      r.basis === "no_rate"
        ? `${r.year} : ${r.note ?? "pas de taux"}`
        : `${r.year} [${basisLabel(r.basis)}] minimum ${fmt(r.minimum_monthly)} | convenu ${fmt(r.contract_monthly)} | écart ${fmt(r.gap_monthly)} MAD/mois ${r.compliant ? "(conforme)" : "(NON CONFORME)"}${r.severance_prorata !== undefined ? ` | indemnité de licenciement au 31/12 : ${fmt(r.severance_prorata)} (prorata) à ${fmt(r.severance_full_year)} (année pleine)` : ""}`
    );
    const tail = firstBad ? `Premier écart sous le minimum légal : ${firstBad}.` : "Aucun écart sous le minimum légal sur la période.";
    const note = calc.data?.warnings?.[0] ?? "Après le dernier décret connu, le minimum est supposé inchangé : ce n'est pas une prévision du taux légal.";
    return [head, ...lines, tail, note].join("\n");
  }, [rows, startYear, endYear, sector, pay, raise, growth, firstBad, isLocal, calc.data]);
  useEffect(() => { if (active) onText(text); }, [text, active, onText]);

  return (
    <div className="space-y-4">
      <Banner title={tr("Salaire minimum légal et salaire convenu, {0} à {1}", [startYear, Math.max(startYear, endYear)])}>
        {tr("Le taux légal vient des décrets datés du pack de lois (SMIG 2026 : 17,92 MAD/h depuis le 1er janvier 2026). Après le dernier décret, aucune hausse n'est connue : le minimum est")} <strong>{tr("maintenu")}</strong>{tr(", sauf si vous saisissez un scénario. Ce n'est pas une prévision.")}
      </Banner>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="space-y-1.5 col-span-2">
          <label className={label} style={{ color: "var(--text-muted)" }}>{tr("Secteur")}</label>
          <select value={sector} onChange={(e) => setSector(e.target.value as typeof sector)} className={inputCls} style={border}>
            <option value="non_agricultural">{tr("Industrie / Commerce / Services (SMIG horaire)")}</option>
            <option value="agricultural">{tr("Agriculture (SMAG journalier)")}</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <label className={label} style={{ color: "var(--text-muted)" }}>{tr("Salaire mensuel (MAD)")}</label>
          <input type="number" min={0} value={pay} onChange={(e) => setPay(Number(e.target.value))} className={inputCls} style={border} />
        </div>
        <div className="space-y-1.5">
          <label className={label} style={{ color: "var(--text-muted)" }}>{sector === "non_agricultural" ? tr("Heures / mois") : tr("Jours / mois")}</label>
          {sector === "non_agricultural" ? (
            <input type="number" min={1} value={hours} onChange={(e) => setHours(Number(e.target.value))} className={inputCls} style={border} />
          ) : (
            <input type="number" min={1} value={days} onChange={(e) => setDays(Number(e.target.value))} className={inputCls} style={border} />
          )}
        </div>
        <div className="space-y-1.5">
          <label className={label} style={{ color: "var(--text-muted)" }}>{tr("De")}</label>
          <select value={startYear} onChange={(e) => setStartYear(Number(e.target.value))} className={inputCls} style={border}>
            {years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div className="space-y-1.5">
          <label className={label} style={{ color: "var(--text-muted)" }}>À</label>
          <select value={endYear} onChange={(e) => setEndYear(Number(e.target.value))} className={inputCls} style={border}>
            {years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div className="space-y-1.5">
          <label className={label} style={{ color: "var(--text-muted)" }}>{tr("Hausse annuelle du salaire (%)")}</label>
          <input type="number" step="0.1" value={raise} onChange={(e) => setRaise(Number(e.target.value))} className={inputCls} style={border} />
        </div>
        <div className="space-y-1.5">
          <label className={label} style={{ color: "var(--text-muted)" }}>{tr("Scénario : hausse annuelle du SMIG (%)")}</label>
          <input type="number" step="0.1" min={0} value={growth} onChange={(e) => setGrowth(Math.max(0, Number(e.target.value)))} className={inputCls} style={border} />
        </div>
        <div className="space-y-1.5 col-span-2 sm:col-span-4">
          <label className={label} style={{ color: "var(--text-muted)" }}>{tr("Date d'embauche (optionnel : ajoute l'indemnité de licenciement au 31 décembre de chaque année)")}</label>
          <input type="date" value={hired} onChange={(e) => setHired(e.target.value)} className={inputCls} style={border} />
        </div>
      </div>

      <div className="p-3.5 rounded-xl border text-xs font-code" style={{ backgroundColor: "var(--bg-card)", borderColor: firstBad ? "#EF4444" : "var(--border-strong)" }}>
        <div className="font-semibold" style={{ color: firstBad ? "#EF4444" : "#10B981" }}>
          {firstBad ? tr("Salaire inférieur au minimum légal à partir de {0}", [firstBad]) : tr("Conforme au minimum légal sur toute la période")}
          {isLocal && <span className="ml-2 font-normal" style={{ color: "var(--text-muted)" }}>{tr("(estimation locale)")}</span>}
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "var(--border-subtle)" }}>
        <table className="w-full text-[11px] font-code">
          <thead>
            <tr style={{ color: "var(--text-muted)", backgroundColor: "var(--bg-canvas)" }}>
              <th className="text-left p-2">{tr("Année")}</th>
              <th className="text-left p-2">{tr("Base du taux")}</th>
              <th className="text-right p-2">{tr("Taux légal")}</th>
              <th className="text-right p-2">{tr("Minimum / mois")}</th>
              <th className="text-right p-2">{tr("Salaire convenu")}</th>
              <th className="text-right p-2">{tr("Écart / mois")}</th>
              {showSev && <th className="text-right p-2">{tr("Licenciement 31/12")}</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.year} className="border-t" style={{ borderColor: "var(--border-subtle)", color: "var(--text-primary)" }}>
                <td className="p-2 font-semibold">{r.year}</td>
                {r.basis === "no_rate" ? (
                  <td className="p-2" colSpan={showSev ? 6 : 5} style={{ color: "var(--text-muted)" }}>{r.note}</td>
                ) : (
                  <>
                    <td className="p-2" style={{ color: r.basis === "scenario" ? "var(--accent-warm)" : "var(--text-muted)" }}>{basisLabel(r.basis)}</td>
                    <td className="p-2 text-right">{fmt(r.rate, 3)} {r.rate_unit?.replace("MAD/", "")}</td>
                    <td className="p-2 text-right">{fmt(r.minimum_monthly)}</td>
                    <td className="p-2 text-right">{fmt(r.contract_monthly)}</td>
                    <td className="p-2 text-right font-semibold" style={{ color: r.compliant ? "#10B981" : "#EF4444" }}>{fmt(r.gap_monthly)}</td>
                    {showSev && (
                      <td className="p-2 text-right">
                        {r.severance_prorata !== undefined ? `${fmt(r.severance_prorata, 0)} – ${fmt(r.severance_full_year, 0)}` : r.severance_note ?? "-"}
                      </td>
                    )}
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!isLocal && calc.data && (
        <div className="text-[11px]" style={{ color: "var(--text-muted)" }}>
          {tr("Dernier taux dans le pack :")} {server?.latest_decree_year}{tr(". Les années suivantes sont maintenues (ou suivent votre scénario). Hors primes d'ancienneté, 13e mois, heures supplémentaires, cotisations et impôt.")}
        </div>
      )}
      <TracePanel b={calc} />
    </div>
  );
};

// ============================================================================================================ limitation
interface DeadlineRule { kind: string; case_type: string; trigger: string; amount: number; unit: string; regime?: string; valid_from?: string | null; valid_to?: string | null; provision_id?: string | null }

export const LimitationTab: React.FC<{ isOpen: boolean; active: boolean; asOfDate: string; onText: (t: string) => void }> = ({ isOpen, active, asOfDate, onText }) => {
  const rules = useBackendGet<DeadlineRule[]>("/v1/deadline-rules", isOpen && active);
  const types = useMemo(() => Array.from(new Set((rules.data ?? []).filter((r) => r.kind === "limitation").map((r) => r.case_type))), [rules.data]);
  const [claimType, setClaimType] = useState("");
  const [start, setStart] = useState(asOfDate);
  useEffect(() => { if (!claimType && types[0]) setClaimType(types[0]); }, [types, claimType]);
  const calc = useBackendCalc("limitation_period", claimType ? { claim_type: claimType, start_date: start } : null, isOpen && active);
  const r = calc.data?.result as { expiry?: string; period?: string; article?: string } | undefined;
  useEffect(() => {
    if (active && r?.expiry) onText(`[PRESCRIPTION - ${claimType}]\nPoint de départ : ${start}\nDélai : ${r.period}\nExpiration : ${r.expiry}\nBase : ${calc.data?.legal_basis.join("; ")}\n${(calc.data?.warnings ?? []).join("\n")}`);
  }, [r, active, claimType, start, calc.data, onText]);

  return (
    <div className="space-y-4">
      <Banner title={tr("Délais de prescription")}>
        {tr("Date d'expiration d'une action selon les règles de prescription du pack de lois. Les causes d'interruption et de suspension ne sont pas modélisées : un professionnel doit confirmer.")}
      </Banner>
      {rules.error && <TracePanel b={{ data: null, error: rules.error, loading: false }} />}
      {!rules.error && rules.data && types.length === 0 && (
        <div className="text-xs" style={{ color: "var(--text-muted)" }}>{tr("Aucune règle de prescription dans le pack de lois actuel.")}</div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <label className={label} style={{ color: "var(--text-muted)" }}>{tr("Type d'action")}</label>
          <select value={claimType} onChange={(e) => setClaimType(e.target.value)} className={inputCls} style={border} disabled={types.length === 0}>
            {types.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className="space-y-1.5">
          <label className={label} style={{ color: "var(--text-muted)" }}>{tr("Point de départ du délai")}</label>
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={inputCls} style={border} />
        </div>
      </div>
      {r?.expiry && (
        <div className="p-4 rounded-xl border space-y-1 font-code text-xs" style={{ backgroundColor: "var(--bg-card)", borderColor: "var(--border-strong)" }}>
          <div>{tr("Délai :")} <strong>{r.period}</strong></div>
          <div>{tr("Expire le :")} <strong style={{ color: "var(--accent-primary)" }}>{r.expiry}</strong></div>
          {r.article && <div style={{ color: "var(--text-muted)" }}>{tr("Article :")} {r.article}</div>}
        </div>
      )}
      <TracePanel b={calc} />
    </div>
  );
};


// ============================================================================================================ unpaid minimum wage over time
interface ArrearsPeriod { from: string; to: string; months: number; rate: number; monthly_pay: number; minimum: number; pay: number; shortfall: number; decree: string }
interface ArrearsResult { total_shortfall: number; months_checked: number; months_below_minimum: number; periods: ArrearsPeriod[]; months_not_computed: string[]; shortfall_older_than_two_years?: number; shortfall_within_two_years?: number }

export const WageArrearsTab: React.FC<{ isOpen: boolean; active: boolean; asOfDate: string; onText: (t: string) => void }> = ({ isOpen, active, asOfDate, onText }) => {
  const [sector, setSector] = useState<"non_agricultural" | "agricultural">("non_agricultural");
  const [start, setStart] = useState("2025-01-01");
  const [end, setEnd] = useState(asOfDate);
  const [pay, setPay] = useState(2800);
  const [hours, setHours] = useState(191);
  const [days, setDays] = useState(26);
  const [changes, setChanges] = useState<{ from_date: string; monthly_pay: number }[]>([]);
  const [contractEnd, setContractEnd] = useState("");

  const inputs = useMemo(
    () => (start && end && end >= start && pay >= 0
      ? { start_date: start, end_date: end, sector, monthly_pay: pay, hours_per_month: hours, days_per_month: days,
          pay_changes: changes.filter((c) => c.from_date && c.monthly_pay >= 0), ...(contractEnd ? { contract_end_date: contractEnd } : {}) }
      : null),
    [start, end, sector, pay, hours, days, changes, contractEnd]
  );
  const calc = useBackendCalc("wage_arrears", inputs, isOpen && active);
  const r = calc.data?.result as unknown as ArrearsResult | undefined;
  useEffect(() => {
    if (!active || !r) return;
    const lines = r.periods.map((p) => `${p.from} → ${p.to} : ${p.months} mois, minimum légal ${fmt(p.rate)} x ${sector === "non_agricultural" ? hours + " h" : days + " j"} = ${fmt(p.minimum / p.months)} / mois, salaire reçu ${fmt(p.monthly_pay)} → écart ${fmt(p.shortfall)} MAD (${p.decree})`);
    onText([`[RAPPEL DE SALAIRE MINIMUM ${start} → ${end}]`, ...lines, `Total de l'écart sous le minimum légal : ${fmt(r.total_shortfall)} MAD sur ${r.months_below_minimum} mois.`,
      r.months_not_computed.length ? `Mois non calculés (taux absent du pack) : ${r.months_not_computed.join(", ")}.` : "",
      r.shortfall_older_than_two_years ? `Dont plus de deux ans avant la fin du contrat (prescription possible, art. 395) : ${fmt(r.shortfall_older_than_two_years)} MAD.` : ""].filter(Boolean).join("\n"));
  }, [r, active, start, end, sector, hours, days, onText]);

  return (
    <div className="space-y-4">
      <Banner title={tr("Salaire minimum impayé sur une période")}>
        {tr("Le minimum légal change selon les décrets. Indiquez ce que vous avez réellement reçu : l'outil compare") }<strong> {tr("mois par mois")} </strong>{tr("avec le taux en vigueur à chaque date, additionne l'écart et signale les mois de plus de deux ans avant la fin du contrat.")}
      </Banner>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="space-y-1.5 col-span-2">
          <label className={label} style={{ color: "var(--text-muted)" }}>{tr("Secteur")}</label>
          <select value={sector} onChange={(e) => setSector(e.target.value as typeof sector)} className={inputCls} style={border}>
            <option value="non_agricultural">{tr("Industrie / Commerce / Services (SMIG horaire)")}</option>
            <option value="agricultural">{tr("Agriculture (SMAG journalier)")}</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <label className={label} style={{ color: "var(--text-muted)" }}>{tr("Du")}</label>
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={inputCls} style={border} />
        </div>
        <div className="space-y-1.5">
          <label className={label} style={{ color: "var(--text-muted)" }}>{tr("Au")}</label>
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className={inputCls} style={border} />
        </div>
        <div className="space-y-1.5">
          <label className={label} style={{ color: "var(--text-muted)" }}>{tr("Salaire reçu par mois (MAD)")}</label>
          <input type="number" min={0} value={pay} onChange={(e) => setPay(Number(e.target.value))} className={inputCls} style={border} />
        </div>
        <div className="space-y-1.5">
          <label className={label} style={{ color: "var(--text-muted)" }}>{sector === "non_agricultural" ? tr("Heures / mois") : tr("Jours / mois")}</label>
          {sector === "non_agricultural"
            ? <input type="number" min={1} value={hours} onChange={(e) => setHours(Number(e.target.value))} className={inputCls} style={border} />
            : <input type="number" min={1} value={days} onChange={(e) => setDays(Number(e.target.value))} className={inputCls} style={border} />}
        </div>
        <div className="space-y-1.5 col-span-2">
          <label className={label} style={{ color: "var(--text-muted)" }}>{tr("Fin du contrat (facultatif)")}</label>
          <input type="date" value={contractEnd} onChange={(e) => setContractEnd(e.target.value)} className={inputCls} style={border} />
        </div>
      </div>
      <div className="space-y-2">
        {changes.map((c, i) => (
          <div key={i} className="flex gap-2 items-center text-xs">
            <span style={{ color: "var(--text-muted)" }}>{tr("À partir du")}</span>
            <input type="date" value={c.from_date} onChange={(e) => setChanges(changes.map((x, j) => (j === i ? { ...x, from_date: e.target.value } : x)))} className={inputCls + " !w-auto"} style={border} />
            <span style={{ color: "var(--text-muted)" }}>{tr("salaire reçu")}</span>
            <input type="number" min={0} value={c.monthly_pay} onChange={(e) => setChanges(changes.map((x, j) => (j === i ? { ...x, monthly_pay: Number(e.target.value) } : x)))} className={inputCls + " !w-28"} style={border} />
            <button type="button" onClick={() => setChanges(changes.filter((_, j) => j !== i))} className="cursor-pointer px-2" style={{ color: "var(--text-muted)" }}>✕</button>
          </div>
        ))}
        <button type="button" onClick={() => setChanges([...changes, { from_date: start, monthly_pay: pay }])} className="text-xs underline cursor-pointer" style={{ color: "var(--accent-primary)" }}>
          {tr("+ Mon salaire a changé en cours de route")}
        </button>
      </div>

      {r && (
        <div className="rounded-xl border p-4 space-y-3" style={{ borderColor: "var(--border-strong)", backgroundColor: "var(--bg-card)" }}>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <div className={label} style={{ color: "var(--text-muted)" }}>{tr("Écart total sous le minimum légal")}</div>
              <div className="text-2xl font-bold" style={{ color: r.total_shortfall > 0 ? "var(--accent-danger, #c0392b)" : "var(--text-heading)" }}>{fmt(r.total_shortfall)} MAD</div>
            </div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>
              {r.months_below_minimum} {tr("mois sous le minimum sur")} {r.months_checked} {tr("calculés")}
            </div>
          </div>
          {r.shortfall_older_than_two_years !== undefined && (
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-2.5 rounded-lg border" style={border}><div style={{ color: "var(--text-muted)" }}>{tr("Moins de 2 ans avant la fin du contrat")}</div><b>{fmt(r.shortfall_within_two_years)} MAD</b></div>
              <div className="p-2.5 rounded-lg border" style={border}><div style={{ color: "var(--text-muted)" }}>{tr("Plus de 2 ans (prescription possible, art. 395)")}</div><b>{fmt(r.shortfall_older_than_two_years)} MAD</b></div>
            </div>
          )}
          <table className="w-full text-[11px]">
            <thead><tr style={{ color: "var(--text-muted)" }} className="text-start"><th className="text-start font-medium py-1">{tr("Période")}</th><th className="text-end font-medium">{tr("Taux légal")}</th><th className="text-end font-medium">{tr("Reçu / mois")}</th><th className="text-end font-medium">{tr("Écart")}</th></tr></thead>
            <tbody>
              {r.periods.map((p, i) => (
                <tr key={i} className="border-t" style={{ borderColor: "var(--border-subtle)" }}>
                  <td className="py-1.5">{p.from} → {p.to} <span style={{ color: "var(--text-muted)" }}>({p.months} {tr("mois")})</span><div style={{ color: "var(--text-muted)" }}>{p.decree}</div></td>
                  <td className="text-end">{fmt(p.rate)}</td><td className="text-end">{fmt(p.monthly_pay)}</td>
                  <td className="text-end font-semibold" style={{ color: p.shortfall > 0 ? "var(--accent-danger, #c0392b)" : "inherit" }}>{fmt(p.shortfall)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {r.months_not_computed.length > 0 && (
            <div className="text-[11px] flex gap-1.5" style={{ color: "var(--accent-warm)" }}><AlertTriangle className="w-3.5 h-3.5 shrink-0" />{tr("{0} mois non calculés ({1} → {2}) : le pack ne contient pas encore les décrets d'avant.", [r.months_not_computed.length, r.months_not_computed[0], r.months_not_computed[r.months_not_computed.length - 1]])}</div>
          )}
        </div>
      )}
      <TracePanel b={calc} />
    </div>
  );
};

// ============================================================================================================ tax / rates
interface RateTable { key: string; kind: "rate" | "progressive"; rows: { value: number | null; unit: string | null; valid_from: string; valid_to: string | null; source_decree?: string | null; note?: string | null }[] }

export const TaxTab: React.FC<{ isOpen: boolean; active: boolean; asOfDate: string; onText: (t: string) => void }> = ({ isOpen, active, asOfDate, onText }) => {
  const rates = useBackendGet<RateTable[]>("/v1/rates", isOpen && active);
  const tables = useMemo(
    () => (rates.data ?? []).filter((t) => t.key !== "REG_EXTRA_CASH_PCT" && (t.kind === "progressive" || t.rows.some((r) => r.unit === "percent"))),
    [rates.data]
  );
  const [key, setKey] = useState("");
  const [date, setDate] = useState(asOfDate);
  const [amount, setAmount] = useState(100000);
  const [mode, setMode] = useState<"tax_on_base" | "extract_from_gross">("tax_on_base");
  useEffect(() => { if (!key && tables[0]) setKey(tables[0].key); }, [tables, key]);
  const table = tables.find((t) => t.key === key);
  const calc = useBackendCalc(
    "tax_computation",
    table ? { date, kind: table.kind, key: table.key, amount, ...(table.kind === "rate" ? { mode } : {}) } : null,
    isOpen && active
  );
  const res = calc.data?.result as { tax?: number; rate_pct?: number } | undefined;
  useEffect(() => {
    if (active && res?.tax !== undefined) onText(`[CALCUL D'IMPÔT - ${key}]\nDate : ${date} | Montant : ${fmt(amount)} MAD\n${res.rate_pct !== undefined ? `Taux : ${res.rate_pct}%\n` : ""}Impôt : ${fmt(res.tax)} MAD\nBase légale : ${calc.data?.legal_basis.join("; ")}\n${(calc.data?.steps ?? []).join("\n")}`);
  }, [res, active, key, date, amount, calc.data, onText]);

  return (
    <div className="space-y-4">
      <Banner title={tr("Impôts et taxes : barèmes datés du pack")}>
        {tr("Taux ou barème progressif choisi selon la")} <strong>{tr("date")}</strong> {tr("(année de la loi de finances). Seuls les barèmes réellement présents dans le pack de lois sont proposés : aucun taux n'est inventé.")}
      </Banner>
      {rates.error && <TracePanel b={{ data: null, error: rates.error, loading: false }} />}
      {!rates.error && rates.data && tables.length === 0 && (
        <div className="text-xs p-3 rounded-xl border" style={{ color: "var(--text-muted)", borderColor: "var(--border-subtle)" }}>
          {tr("Aucun barème d'impôt dans le pack de lois actuel. Ajoutez des tables de taux (TVA, IR…) avec legalrag-build à partir de sources vérifiées.")}
        </div>
      )}
      {tables.length > 0 && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <label className={label} style={{ color: "var(--text-muted)" }}>{tr("Barème")}</label>
              <select value={key} onChange={(e) => setKey(e.target.value)} className={inputCls} style={border}>
                {tables.map((t) => <option key={t.key} value={t.key}>{t.key} ({t.kind === "progressive" ? "progressif" : "taux"})</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <label className={label} style={{ color: "var(--text-muted)" }}>{tr("Date")}</label>
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={inputCls} style={border} />
            </div>
            <div className="space-y-1.5">
              <label className={label} style={{ color: "var(--text-muted)" }}>{tr("Montant (MAD)")}</label>
              <input type="number" min={0} value={amount} onChange={(e) => setAmount(Number(e.target.value))} className={inputCls} style={border} />
            </div>
            {table?.kind === "rate" && (
              <div className="space-y-1.5 sm:col-span-3">
                <label className={label} style={{ color: "var(--text-muted)" }}>{tr("Le montant est")}</label>
                <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)} className={inputCls} style={border}>
                  <option value="tax_on_base">{tr("Hors taxe (calculer la taxe en plus)")}</option>
                  <option value="extract_from_gross">{tr("Toutes taxes comprises (extraire la taxe)")}</option>
                </select>
              </div>
            )}
          </div>
          {res?.tax !== undefined && (
            <div className="p-4 rounded-xl border space-y-1 font-code text-xs" style={{ backgroundColor: "var(--bg-card)", borderColor: "var(--border-strong)" }}>
              {res.rate_pct !== undefined && <div>{tr("Taux applicable :")} <strong>{res.rate_pct}%</strong></div>}
              <div>{tr("Impôt / taxe :")} <strong style={{ color: "var(--accent-primary)" }}>{fmt(res.tax)} {tr("MAD")}</strong></div>
            </div>
          )}
          {table && (
            <details className="text-[11px]" style={{ color: "var(--text-muted)" }}>
              <summary className="cursor-pointer">{tr("Lignes de ce barème dans le pack")}</summary>
              {table.rows.map((r, i) => (
                <div key={i}>• {r.value ?? tr("barème")} {r.unit ?? ""} {tr("du")} {r.valid_from} {r.valid_to ? tr("au {0}", [r.valid_to]) : tr("(en vigueur)")} {r.source_decree ? `· ${r.source_decree}` : ""}</div>
              ))}
            </details>
          )}
        </>
      )}
      <TracePanel b={calc} />
    </div>
  );
};
