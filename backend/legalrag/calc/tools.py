"""The calculators. Rates and rules come from dated rows in the law pack; nothing numeric is hard-coded here
except arithmetic. Worked examples (see EXAMPLES) decide each tool's `verified` label."""
from __future__ import annotations

from datetime import date, timedelta
from fractions import Fraction
from typing import Any, Literal

from dateutil.relativedelta import relativedelta
from pydantic import BaseModel, Field

from ..store.lawpack import LawPack
from .base import CalcError, CalcResult, money


def _rate(pack: LawPack, key: str, on: date) -> dict:
    row = pack.rate_at(key, on)
    if row:
        return row
    rows = pack.rate_rows(key)
    if not rows:
        raise CalcError("abstain", f"no '{key}' rate table in the law pack")
    raise CalcError("abstain", f"no '{key}' rate on {on.isoformat()} (table covers {rows[0]['valid_from']} onwards)" if on < date.fromisoformat(rows[0]["valid_from"])
                    else f"no '{key}' rate on {on.isoformat()}")


def _row(r: dict) -> dict:
    return {k: r.get(k) for k in ("key", "value", "unit", "valid_from", "valid_to", "source_decree")}


# =============================================================== minimum wage
class MinimumWageIn(BaseModel):
    date: date
    sector: Literal["non_agricultural", "agricultural"] = "non_agricultural"
    hours_worked: float | None = Field(None, ge=0)
    days_worked: float | None = Field(None, ge=0)
    pay: float = Field(..., ge=0)


def minimum_wage(pack: LawPack, i: MinimumWageIn) -> CalcResult:
    if i.sector == "non_agricultural":
        if i.hours_worked is None:
            raise CalcError("needs_input", "hours_worked is required for the SMIG check", ["hours_worked"])
        r, units, key = _rate(pack, "SMIG_HOURLY", i.date), i.hours_worked, "hours"
    else:
        if i.days_worked is None:
            raise CalcError("needs_input", "days_worked is required for the SMAG check", ["days_worked"])
        r, units, key = _rate(pack, "SMAG_DAILY", i.date), i.days_worked, "days"
    due = money(r["value"] * units)
    short = money(max(0.0, due - i.pay))
    return CalcResult(
        "minimum_wage", i.model_dump(mode="json"),
        {"rate": r["value"], "minimum_due": due, "pay": i.pay, "shortfall": short, "compliant": short == 0},
        f"minimum_due = rate x {key}_worked ; shortfall = max(0, minimum_due - pay)",
        [r.get("source_decree") or "minimum wage decree"], [_row(r)],
        [f"rate on {i.date.isoformat()} = {r['value']} {r['unit']}", f"minimum_due = {r['value']} x {units} = {due}"],
        [], False, i.date.isoformat(),
    )


# =============================================================== 2% cash surcharge
class CashSurchargeIn(BaseModel):
    date: date
    transfer_type: Literal["real_estate", "business"]
    price: float = Field(..., gt=0)
    cash_portion: float = Field(..., ge=0, description="part of the price paid by unrecognised means (e.g. cash)")
    of_which_bank_cash_deposit: float = Field(0, ge=0, description="cash deposited at a bank: counts as a recognised payment method")


def registration_cash_surcharge(pack: LawPack, i: CashSurchargeIn) -> CalcResult:
    if i.cash_portion > i.price or i.of_which_bank_cash_deposit > i.cash_portion:
        raise CalcError("needs_input", "inconsistent amounts: cash_portion cannot exceed price, nor the bank deposit exceed cash_portion")
    rows = pack.rate_rows("REG_EXTRA_CASH_PCT")
    if not rows:
        raise CalcError("abstain", "no REG_EXTRA_CASH_PCT rate table in the law pack")
    start = date.fromisoformat(rows[0]["valid_from"])
    base = money(i.cash_portion - i.of_which_bank_cash_deposit)
    warnings = ["Only the extra 2% surcharge is computed. The base registration duty rate is not in this law pack: check the CGI for the date and transfer type."]
    if i.date < start:
        return CalcResult("registration_cash_surcharge", i.model_dump(mode="json"), {"surcharge": 0.0, "taxable_cash": base}, "surcharge = pct x (cash_portion - bank_cash_deposit)",
                          ["Finance Law 50-25 (CGI art. 133, added paragraph)"], [_row(rows[0])],
                          [f"the surcharge is not in force on {i.date.isoformat()} (starts {start.isoformat()})"], warnings, False, i.date.isoformat())
    r = _rate(pack, "REG_EXTRA_CASH_PCT", i.date)
    s = money(base * r["value"] / 100)
    return CalcResult(
        "registration_cash_surcharge", i.model_dump(mode="json"), {"surcharge": s, "taxable_cash": base, "pct": r["value"]},
        "surcharge = pct/100 x (cash_portion - bank_cash_deposit)", ["Finance Law 50-25 (CGI art. 133, added paragraph)"], [_row(r)],
        [f"taxable cash = {i.cash_portion} - {i.of_which_bank_cash_deposit} = {base}", f"surcharge = {r['value']}% x {base} = {s}"], warnings, False, i.date.isoformat(),
    )


# =============================================================== severance
class SeveranceIn(BaseModel):
    start_date: date
    end_date: date
    hourly_wage: float | None = Field(None, gt=0)
    monthly_wage: float | None = Field(None, gt=0)
    monthly_hours: float | None = Field(None, gt=0, description="required with monthly_wage; you choose the divisor, it is not guessed")
    serious_misconduct: bool = False


def _years_bands(pack: LawPack, on: date) -> list[tuple[int, int | None, dict]]:
    keys = [("SEVERANCE_HOURS_Y1_5", 1, 5), ("SEVERANCE_HOURS_Y6_10", 6, 10), ("SEVERANCE_HOURS_Y11_15", 11, 15), ("SEVERANCE_HOURS_Y16_PLUS", 16, None)]
    return [(a, b, _rate(pack, k, on)) for k, a, b in keys]


def severance(pack: LawPack, i: SeveranceIn) -> CalcResult:
    if i.end_date < i.start_date:
        raise CalcError("needs_input", "end_date is before start_date")
    if i.hourly_wage is None and not (i.monthly_wage and i.monthly_hours):
        raise CalcError("needs_input", "give hourly_wage, or monthly_wage together with monthly_hours", ["hourly_wage"])
    hourly = i.hourly_wage or i.monthly_wage / i.monthly_hours
    from .basis import severance_from_law

    law = severance_from_law(pack, i.end_date)  # the hours and the six months as the Labour Code articles in force say them
    warnings = ["Law 65-99 severance parameters come from the law pack and are labelled unverified until they match an official worked example."]
    try:
        bands = _years_bands(pack, i.end_date)
        min_row = _rate(pack, "SEVERANCE_MIN_MONTHS", i.end_date)
        min_months = min_row["value"]
        if law and [r["value"] for _, _, r in bands] != law["hours"]:
            warnings.append(f"the rate table ({[r['value'] for _, _, r in bands]} hours) differs from article {law['articles']['amount']} of the Labour Code "
                            f"({law['hours']} hours): check the pack")
    except CalcError:
        if not law or law["min_months"] is None:
            raise
        src = f"Labour Code art. {law['articles']['amount']}"
        bands = [(a, b, {"key": f"article {law['articles']['amount']}", "value": float(h), "unit": "hours", "valid_from": None, "valid_to": None, "source_decree": src})
                 for (a, b), h in zip(((1, 5), (6, 10), (11, 15), (16, None)), law["hours"])]
        min_months = law["min_months"]
        min_row = {"key": f"article {law['articles'].get('right')}", "value": float(min_months), "unit": "months", "valid_from": None, "valid_to": None,
                   "source_decree": f"Labour Code art. {law['articles'].get('right')}"}
        warnings.append("no severance rate table in the pack: the hours and the minimum seniority were read from the Labour Code articles")
    delta = relativedelta(i.end_date, i.start_date)
    total_months = delta.years * 12 + delta.months
    if i.serious_misconduct:
        return CalcResult("severance", i.model_dump(mode="json"), {"severance": 0.0}, "no severance when dismissal is for serious misconduct", ["Law 65-99"], [], ["serious misconduct declared by the user: no calculation"], warnings, False, i.end_date.isoformat())
    if total_months < min_months:
        return CalcResult("severance", i.model_dump(mode="json"), {"severance": 0.0, "seniority_months": total_months}, "requires minimum seniority", ["Law 65-99"], [_row(min_row)],
                          [f"seniority {total_months} months < minimum {min_months:g} months"], warnings, False, i.end_date.isoformat())
    full_years, rem_days = delta.years, (i.end_date - (i.start_date + relativedelta(years=delta.years))).days
    frac = Fraction(min(rem_days, 365), 365)  # remaining fraction of the current year

    def hours_for_year(n: int) -> float:
        for a, b, r in bands:
            if n >= a and (b is None or n <= b):
                return r["value"]
        return 0.0

    base = sum(hours_for_year(n) for n in range(1, full_years + 1))
    partial_year_hours = hours_for_year(full_years + 1) if rem_days > 0 else 0.0
    prorata = base + float(frac) * partial_year_hours
    full = base + partial_year_hours
    opts = {"prorata": money(prorata * hourly), "full_year": money(full * hourly)}
    return CalcResult(
        "severance", i.model_dump(mode="json"),
        {"hourly_wage": money(hourly), "hours_prorata": round(prorata, 2), "hours_full_year": full, "severance_if_fraction_prorata": opts["prorata"], "severance_if_fraction_counted_as_full_year": opts["full_year"]},
        "severance = hourly_wage x sum over seniority years of the hours set for that year's band",
        ["Law 65-99 (Labour Code), severance provisions"], [_row(r) for _, _, r in bands],
        [f"seniority {full_years} years + {rem_days} days", f"hourly wage {money(hourly)}", "how a fraction of a year is treated is not decided here: both readings are shown"],
        warnings, False, i.end_date.isoformat(),
    )


# =============================================================== deadlines / limitation
class DeadlineIn(BaseModel):
    case_type: str = "civil"
    decision_date: date
    notification_date: date | None = None
    claim_amount: float | None = Field(None, ge=0)
    today: date | None = None


def _roll(pack: LawPack, d: date) -> tuple[date, list[str]]:
    hol = pack.holidays()
    notes: list[str] = []
    out = d
    while out.weekday() >= 5 or out.isoformat() in hol:
        why = "weekend" if out.weekday() >= 5 else ", ".join(h["name"] for h in hol[out.isoformat()])
        notes.append(f"{out.isoformat()} is a non-working day ({why})")
        out += timedelta(days=1)
    return out, notes


def _add(d: date, amount: int, unit: str) -> date:
    return d + (timedelta(days=amount) if unit == "days" else relativedelta(months=amount) if unit == "months" else relativedelta(years=amount))


HOLIDAY_WARNING = "The holiday calendar holds fixed civil holidays and whatever religious dates the pack lists; moon-dependent dates may be missing. Verify the final day."


def procedural_deadline(pack: LawPack, i: DeadlineIn) -> CalcResult:
    limit = pack.rate_at("SMALL_CLAIM_LIMIT", i.decision_date)
    if limit and i.claim_amount is not None and i.claim_amount <= limit["value"]:
        return CalcResult(
            "procedural_deadline", i.model_dump(mode="json"), {"appealable": False}, "claims up to the limit are decided at first and last instance: no appeal deadline",
            ["Law 58.25 (small-claims rule)"], [_row(limit)], [f"claim {i.claim_amount} <= {limit['value']}"], ["Verify the rule against the BO text."], False, i.decision_date.isoformat())
    rules = [r for r in pack.deadline_rules("appeal", i.case_type)
             if (not r["valid_from"] or r["valid_from"] <= i.decision_date.isoformat()) and (not r["valid_to"] or r["valid_to"] > i.decision_date.isoformat())]
    if not rules:
        raise CalcError("abstain", f"no appeal rule for case_type '{i.case_type}' applies to a decision dated {i.decision_date.isoformat()} in this law pack")
    if len(rules) > 1:
        raise CalcError("abstain", "more than one rule matches this decision date; resolve the transitional rule by reading it")
    r = rules[0]
    trig = {"notification": i.notification_date, "decision": i.decision_date}.get(r["trigger"])
    if trig is None:
        raise CalcError("needs_input", f"this rule runs from the {r['trigger']} date", ["notification_date"])
    nominal = _add(trig, r["amount"], r["unit"])
    adjusted, notes = _roll(pack, nominal)
    warnings = [HOLIDAY_WARNING]
    today = i.today or date.today()
    if adjusted < today:
        warnings.append("the deadline has already passed")
    elif (adjusted - today).days <= 7:
        warnings.append(f"the deadline is {(adjusted - today).days} day(s) away: consult a legal professional now")
    return CalcResult(
        "procedural_deadline", i.model_dump(mode="json"), {"nominal_deadline": nominal.isoformat(), "deadline": adjusted.isoformat(), "regime": r["regime"], "period": f"{r['amount']} {r['unit']}"},
        "deadline = trigger date + period; moved to the next working day if it falls on a non-working day", [r.get("provision_id") or "procedural law"],
        [{k: r[k] for k in ("regime", "trigger", "amount", "unit", "valid_from", "valid_to", "provision_id")}],
        [f"trigger ({r['trigger']}) = {trig.isoformat()}", f"+ {r['amount']} {r['unit']} = {nominal.isoformat()}", *notes], warnings, False, i.decision_date.isoformat())


class LimitationIn(BaseModel):
    claim_type: str
    start_date: date
    today: date | None = None


def limitation_period(pack: LawPack, i: LimitationIn) -> CalcResult:
    rules = [r for r in pack.deadline_rules("limitation", i.claim_type)
             if (not r["valid_from"] or r["valid_from"] <= i.start_date.isoformat()) and (not r["valid_to"] or r["valid_to"] > i.start_date.isoformat())]
    if not rules:
        raise CalcError("abstain", f"no limitation rule for claim_type '{i.claim_type}' in this law pack")
    r = rules[0]
    expiry = _add(i.start_date, r["amount"], r["unit"])
    today = i.today or date.today()
    warnings = ["Interruption and suspension of limitation periods are not modelled."]
    left = (expiry - today).days
    if left < 0:
        warnings.append("the period appears to have expired")
    elif left <= 90:
        warnings.append(f"expires in {left} day(s)")
    return CalcResult("limitation_period", i.model_dump(mode="json"), {"expiry": expiry.isoformat(), "period": f"{r['amount']} {r['unit']}", "article": r.get("provision_id")},
                      "expiry = start date + period", [r.get("provision_id") or "limitation rule"], [{k: r[k] for k in ("amount", "unit", "provision_id")}],
                      [f"{i.start_date.isoformat()} + {r['amount']} {r['unit']} = {expiry.isoformat()}"], warnings, False, i.start_date.isoformat())


# =============================================================== tax
class TaxIn(BaseModel):
    date: date
    kind: Literal["rate", "progressive"]
    key: str = Field(..., description="rate_table key, e.g. a VAT rate key or an income-tax bracket table key")
    amount: float = Field(..., ge=0)
    mode: Literal["tax_on_base", "extract_from_gross"] = "tax_on_base"


def tax_computation(pack: LawPack, i: TaxIn) -> CalcResult:
    r = _rate(pack, i.key, i.date)  # picks the row of the right Finance-Law year: a 2025 question never uses 2026 rates
    if i.kind == "rate":
        pct = r["value"]
        if pct is None:
            raise CalcError("abstain", f"'{i.key}' has no flat rate")
        tax = money(i.amount * pct / 100) if i.mode == "tax_on_base" else money(i.amount - i.amount / (1 + pct / 100))
        return CalcResult("tax_computation", i.model_dump(mode="json"), {"rate_pct": pct, "tax": tax}, "tax = base x rate/100 (or gross - gross/(1+rate/100))",
                          [r.get("source_decree") or "CGI edition for the Finance Law year"], [_row(r)], [f"rate on {i.date.isoformat()} = {pct}%", f"tax = {tax}"], [], False, i.date.isoformat())
    brackets = (r.get("extra") or {}).get("brackets")
    if not brackets:
        raise CalcError("abstain", f"'{i.key}' has no bracket table")
    tax, steps = 0.0, []
    for lo, hi, rt in brackets:
        top = i.amount if hi is None else min(i.amount, hi)
        if top > lo:
            part = (top - lo) * rt
            tax += part
            steps.append(f"{lo}-{hi if hi is not None else '+'} at {rt * 100:g}% -> {money(part)}")
    return CalcResult("tax_computation", i.model_dump(mode="json"), {"tax": money(tax)}, "sum over brackets of (amount in bracket x bracket rate)",
                      [r.get("source_decree") or "CGI edition for the Finance Law year"], [_row(r)], steps, [], False, i.date.isoformat())


# =============================================================== inheritance (restricted scope, fails closed)
class InheritanceIn(BaseModel):
    estate: float | None = Field(None, ge=0)
    husband: bool = False
    wives: int = Field(0, ge=0)
    sons: int = Field(0, ge=0)
    daughters: int = Field(0, ge=0)
    father: bool = False
    mother: bool = False
    other_heirs_present: bool = Field(False, description="grandparents, siblings, etc.: not supported, the tool refuses")


def inheritance_shares(pack: LawPack, i: InheritanceIn) -> CalcResult:
    if i.other_heirs_present:
        raise CalcError("abstain", "heirs beyond spouse, children and parents are not supported by this tool")
    if i.husband and i.wives:
        raise CalcError("needs_input", "husband and wives cannot both survive the same deceased")
    if not any([i.husband, i.wives, i.sons, i.daughters, i.father, i.mother]):
        raise CalcError("needs_input", "no heirs given")
    kids = i.sons + i.daughters
    fixed: dict[str, Fraction] = {}
    if i.husband:
        fixed["husband"] = Fraction(1, 4) if kids else Fraction(1, 2)
    if i.wives:
        fixed["wives (shared equally)"] = Fraction(1, 8) if kids else Fraction(1, 4)
    if i.mother:
        if not kids and i.father and (i.husband or i.wives):
            raise CalcError("abstain", "the mother's share with father and spouse and no children is a special case that this tool does not compute")
        fixed["mother"] = Fraction(1, 6) if kids else Fraction(1, 3)
    if i.father:
        fixed["father"] = Fraction(1, 6) if kids else Fraction(0)
    if i.daughters and not i.sons:
        fixed["daughters (shared equally)"] = Fraction(1, 2) if i.daughters == 1 else Fraction(2, 3)
    total_fixed = sum(fixed.values(), Fraction(0))
    if total_fixed > 1:
        raise CalcError("abstain", "fixed shares exceed the estate (reduction needed): not supported by this tool")
    rest = Fraction(1) - total_fixed
    residuary: list[tuple[str, int]] = []
    if i.sons:
        residuary = [("sons", 2 * i.sons), ("daughters", i.daughters)]
    elif i.father:
        residuary = [("father", 1)]
    if rest and not residuary:
        raise CalcError("abstain", "a residue remains with no residuary heir (redistribution rules not supported)")
    shares = dict(fixed)
    if residuary and rest:
        units = sum(u for _, u in residuary)
        for name, u in residuary:
            if u:
                shares[name] = shares.get(name, Fraction(0)) + rest * Fraction(u, units)
    shares = {k: v for k, v in shares.items() if v}
    out = {k: f"{v.numerator}/{v.denominator}" for k, v in shares.items()}
    if i.estate is not None:
        out.update({f"{k}_amount": money(float(v) * i.estate) for k, v in shares.items()})
    return CalcResult("inheritance_shares", i.model_dump(mode="json"), out, "fixed shares first (Family Code succession rules), residue to residuary heirs (sons 2 : daughters 1)",
                      ["Family Code (2004) succession rules"], [], [f"{k}: {v.numerator}/{v.denominator}" for k, v in shares.items()],
                      ["Restricted scope: spouse, children, parents only. Re-check when the Family Code reform passes."], False)



# =============================================================== salary projection (minimum wage per year, optional severance)
class SalaryProjectionIn(BaseModel):
    start_year: int = Field(2026, ge=2000, le=2100)
    end_year: int = Field(2031, ge=2000, le=2100)
    sector: Literal["non_agricultural", "agricultural"] = "non_agricultural"
    monthly_pay: float = Field(..., ge=0, description="contractual monthly pay (MAD) in start_year")
    hours_per_month: float = Field(191, gt=0, description="SMIG basis (non-agricultural) and the severance divisor")
    days_per_month: float = Field(26, gt=0, description="SMAG basis (agricultural)")
    annual_raise_pct: float = Field(0, ge=-50, le=100, description="yearly change of the contractual pay")
    smig_growth_pct: float = Field(0, ge=0, le=50, description="SCENARIO: yearly rise of the legal minimum in years after the latest decree in the pack (0 = unchanged)")
    employment_start_date: date | None = Field(None, description="adds the severance owed if the contract ended on 31 December of each year")


def salary_projection(pack: LawPack, i: SalaryProjectionIn) -> CalcResult:
    if i.end_year < i.start_year:
        raise CalcError("needs_input", "end_year is before start_year")
    if i.end_year - i.start_year > 15:
        raise CalcError("needs_input", "at most 16 years can be projected at once")
    key, units, unit_label = (("SMIG_HOURLY", i.hours_per_month, "hours") if i.sector == "non_agricultural" else ("SMAG_DAILY", i.days_per_month, "days"))
    rows = pack.rate_rows(key)
    if not rows:
        raise CalcError("abstain", f"no '{key}' rate table in the law pack")
    latest = rows[-1]
    latest_year = date.fromisoformat(latest["valid_from"]).year
    first_from = date.fromisoformat(rows[0]["valid_from"])
    g = i.smig_growth_pct / 100
    years: list[dict] = []
    used_rows: dict[str, dict] = {}
    first_bad: int | None = None
    steps: list[str] = []
    for y in range(i.start_year, i.end_year + 1):
        if date(y, 12, 31) < first_from:
            years.append({"year": y, "basis": "no_rate", "note": f"no '{key}' rate before {first_from.isoformat()}"})
            continue
        if y <= latest_year:
            monthly, basis, prev = [], "decree", None
            for m in range(1, 13):
                r = pack.rate_at(key, date(y, m, 1)) or prev
                if r is None:
                    continue  # before the table starts (partial first year)
                prev = r
                monthly.append(r["value"])
                used_rows[f"{r['valid_from']}"] = _row(r)
            rate = sum(monthly) / len(monthly)
        else:
            basis = "scenario" if g else "carried_forward"
            rate = latest["value"] * (1 + g) ** (y - latest_year)
            used_rows[latest["valid_from"]] = _row(latest)
        minimum = money(rate * units)
        contract = money(i.monthly_pay * (1 + i.annual_raise_pct / 100) ** (y - i.start_year))
        gap = money(contract - minimum)
        ok = gap >= 0
        if not ok and first_bad is None:
            first_bad = y
        entry = {"year": y, "basis": basis, "rate": round(rate, 4), "rate_unit": "MAD/hour" if unit_label == "hours" else "MAD/day",
                 "minimum_monthly": minimum, "contract_monthly": contract, "gap_monthly": gap, "compliant": ok,
                 "shortfall_annual": money(max(0.0, -gap) * 12)}
        if i.employment_start_date and i.employment_start_date <= date(y, 12, 31):
            try:
                sv = severance(pack, SeveranceIn(start_date=i.employment_start_date, end_date=date(y, 12, 31), monthly_wage=max(contract, 0.01), monthly_hours=i.hours_per_month))
                entry["severance_prorata"] = sv.result.get("severance_if_fraction_prorata", sv.result.get("severance"))
                entry["severance_full_year"] = sv.result.get("severance_if_fraction_counted_as_full_year", sv.result.get("severance"))
            except CalcError as e:
                entry["severance_note"] = e.message
        years.append(entry)
        steps.append(f"{y}: {basis} rate {entry['rate']} x {units:g} {unit_label} = {minimum}; contract {contract}; gap {gap}")
    legal = sorted({r.get("source_decree") for r in used_rows.values() if r.get("source_decree")}) or ["minimum wage decree"]
    warnings = [
        f"Years after {latest_year} (latest rate in the pack, from {latest['valid_from']}) assume the legal minimum "
        + (f"rises {i.smig_growth_pct:g}% a year (your scenario)." if g else "is unchanged: no decree exists yet for those years, so this is NOT a forecast of the legal rate."),
        "Only the legal minimum and, if asked, severance are computed. Seniority bonuses, 13th month, overtime, social contributions and income tax are not included.",
    ]
    return CalcResult(
        "salary_projection", i.model_dump(mode="json"),
        {"years": years, "first_non_compliant_year": first_bad, "latest_decree_year": latest_year},
        "per year: minimum = average monthly legal rate x units (hours or days); contract = pay x (1 + raise)^(year - start_year); gap = contract - minimum",
        legal, list(used_rows.values()), steps, warnings, False, f"{i.start_year}-{i.end_year}",
    )



# =============================================================== wage arrears (unpaid minimum wage over a period)
class PayChange(BaseModel):
    from_date: date
    monthly_pay: float = Field(..., ge=0)


class WageArrearsIn(BaseModel):
    start_date: date = Field(..., description="first day worked (or the first day to check)")
    end_date: date = Field(..., description="last day worked (or the last day to check)")
    sector: Literal["non_agricultural", "agricultural"] = "non_agricultural"
    monthly_pay: float = Field(..., ge=0, description="the monthly pay actually received from start_date")
    pay_changes: list[PayChange] = Field(default_factory=list, description="later changes of the pay actually received")
    hours_per_month: float = Field(191, gt=0, description="hours worked per month (SMIG basis, non-agricultural)")
    days_per_month: float = Field(26, gt=0, description="days worked per month (SMAG basis, agricultural)")
    contract_end_date: date | None = Field(None, description="when the contract ended: months older than two years before it are flagged (Labour Code art. 395)")


def _month_days(y: int, m: int) -> int:
    return ((date(y + (m == 12), m % 12 + 1, 1)) - date(y, m, 1)).days


def wage_arrears(pack: LawPack, i: WageArrearsIn) -> CalcResult:
    if i.end_date < i.start_date:
        raise CalcError("needs_input", "end_date is before start_date")
    if (i.end_date - i.start_date).days > 366 * 12:
        raise CalcError("needs_input", "at most 12 years can be checked at once")
    key, units, unit_label = (("SMIG_HOURLY", i.hours_per_month, "hours") if i.sector == "non_agricultural" else ("SMAG_DAILY", i.days_per_month, "days"))
    rows = pack.rate_rows(key)
    if not rows:
        raise CalcError("abstain", f"no '{key}' rate table in the law pack")
    changes = sorted([(i.start_date, i.monthly_pay)] + [(c.from_date, c.monthly_pay) for c in i.pay_changes if c.from_date > i.start_date])

    def pay_on(d: date) -> float:
        cur = changes[0][1]
        for fd, mp in changes:
            if fd <= d:
                cur = mp
        return cur

    months: list[dict] = []
    y, m = i.start_date.year, i.start_date.month
    while (y, m) <= (i.end_date.year, i.end_date.month):
        dim = _month_days(y, m)
        a, b = max(i.start_date, date(y, m, 1)), min(i.end_date, date(y, m, dim))
        days = (b - a).days + 1
        f = days / dim
        # the rate in force on each day of the month, weighted by days (a decree can start in the middle of a month)
        wsum, covered, decs = 0.0, 0, []
        for dd in range(days):
            r = pack.rate_at(key, a + timedelta(days=dd))
            if r:
                wsum += r["value"]
                covered += 1
                if r.get("source_decree") and r["source_decree"] not in decs:
                    decs.append(r["source_decree"])
        entry: dict[str, Any] = {"month": f"{y}-{m:02d}", "days": days, "of_days": dim}
        if covered < days:
            entry.update(rate=None, note=f"no '{key}' rate in the pack before {rows[0]['valid_from']}: not computed")
        else:
            rate = wsum / days
            minimum, pay = money(rate * units * f), money(pay_on(a) * f)
            entry.update(rate=round(rate, 4), minimum=minimum, pay=pay, shortfall=money(max(0.0, minimum - pay)), decree=", ".join(decs))
        months.append(entry)
        m += 1
        if m == 13:
            y, m = y + 1, 1
    done = [e for e in months if e.get("rate") is not None]
    unc = [e["month"] for e in months if e.get("rate") is None]
    periods: list[dict] = []
    for e in done:  # consecutive months with the same rate and pay become one row
        k = (e["rate"], round(e["pay"] / (e["days"] / e["of_days"]), 2))
        if periods and periods[-1]["_k"] == k and e["days"] == e["of_days"] and periods[-1]["_full"]:
            p = periods[-1]
            p["to"], p["months"], p["minimum"], p["pay"], p["shortfall"] = e["month"], p["months"] + 1, money(p["minimum"] + e["minimum"]), money(p["pay"] + e["pay"]), money(p["shortfall"] + e["shortfall"])
        else:
            periods.append({"_k": k, "_full": e["days"] == e["of_days"], "from": e["month"], "to": e["month"], "months": 1, "rate": e["rate"], "monthly_pay": k[1],
                            "minimum": e["minimum"], "pay": e["pay"], "shortfall": e["shortfall"], "decree": e["decree"]})
    for p in periods:
        p.pop("_k"), p.pop("_full")
    total = money(sum(e["shortfall"] for e in done))
    result: dict[str, Any] = {"total_shortfall": total, "months_checked": len(done), "months_below_minimum": sum(1 for e in done if e["shortfall"] > 0),
                              "periods": periods, "months_not_computed": unc}
    warnings = ["The legal minimum is compared with the pay received for the same days; overtime, bonuses and payments in kind are not added to the pay: include them in monthly_pay if they count (art. 357).",
                "A shortfall is not a judgment: a claim can also be limited by prescription, and by what the contract or a collective agreement gives."]
    if unc:
        warnings.append(f"{len(unc)} month(s) ({unc[0]} to {unc[-1]}) are not computed: the pack holds the minimum wage only from {rows[0]['valid_from']}. Add the earlier decrees to the pack to cover them.")
    steps = [f"{p['from']} → {p['to']}: {p['months']} month(s), legal rate {p['rate']} x {units:g} {unit_label}, pay {p['monthly_pay']} → shortfall {p['shortfall']}" for p in periods]
    if i.contract_end_date:
        cut = i.contract_end_date - relativedelta(years=2)
        old = [e for e in done if date.fromisoformat(e["month"] + "-01") < cut]
        result["shortfall_older_than_two_years"] = money(sum(e["shortfall"] for e in old))
        result["shortfall_within_two_years"] = money(total - result["shortfall_older_than_two_years"])
        warnings.append(f"Months before {cut.isoformat()} are more than two years before the end of the contract: they may be time-barred (Labour Code art. 395, shown below). A lawyer decides.")
    used = {r["valid_from"]: _row(r) for r in rows}
    return CalcResult("wage_arrears", i.model_dump(mode="json"), result,
                      "per month: shortfall = max(0, legal rate x units x share of the month worked - pay received for the same share); the rate is the decree rate in force on each day",
                      sorted({r["source_decree"] for r in rows if r.get("source_decree")}) or ["minimum wage decree"], list(used.values()), steps, warnings, False,
                      f"{i.start_date.isoformat()}..{i.end_date.isoformat()}")


# ------------------------------------------------------------------------------------------------ registry
TOOLS: dict[str, tuple[Any, type[BaseModel], str]] = {
    "minimum_wage": (minimum_wage, MinimumWageIn, "SMIG / SMAG compliance check from the dated rate table"),
    "registration_cash_surcharge": (registration_cash_surcharge, CashSurchargeIn, "Extra 2% duty on the cash portion of real-estate and business transfers"),
    "severance": (severance, SeveranceIn, "Severance under Law 65-99 (both readings of a fraction of a year are shown)"),
    "procedural_deadline": (procedural_deadline, DeadlineIn, "Appeal deadline with the transitional rule by decision date"),
    "limitation_period": (limitation_period, LimitationIn, "Expiry date of a limitation period"),
    "tax_computation": (tax_computation, TaxIn, "Rate-based or bracket-based tax using the rate row of the right date"),
    "inheritance_shares": (inheritance_shares, InheritanceIn, "Fixed-share inheritance for spouse, children and parents (restricted scope)"),
    "wage_arrears": (wage_arrears, WageArrearsIn, "Unpaid minimum wage over a period: month by month against the decree rate in force, with the two-year limit flagged"),
    "salary_projection": (salary_projection, SalaryProjectionIn, "Year-by-year legal minimum wage vs contractual pay (2026-2031 and beyond), optional severance per year"),
}

# Worked examples. `official=True` means taken from an official source; only tools whose examples are ALL
# official and pass are labelled verified. Examples run in CI and at start-up.
EXAMPLES: dict[str, list[dict]] = {
    "registration_cash_surcharge": [
        {"inputs": {"date": "2026-07-15", "transfer_type": "real_estate", "price": 500000, "cash_portion": 100000},
         "expect": {"surcharge": 2000.0}, "official": True,
         "source": "Blueprint: the 2% applies to the cash fraction only; 100,000 MAD paid in cash adds 2,000 MAD (DGI letter reported by Ecoactu)"},
        {"inputs": {"date": "2026-07-15", "transfer_type": "real_estate", "price": 500000, "cash_portion": 100000, "of_which_bank_cash_deposit": 100000},
         "expect": {"surcharge": 0.0}, "official": True, "source": "Blueprint: a bank cash deposit counts as a recognised payment method"},
    ],
    "minimum_wage": [
        {"inputs": {"date": "2026-02-01", "sector": "non_agricultural", "hours_worked": 191, "pay": 3000}, "expect": {"minimum_due": 3422.72},
         "official": False, "source": "arithmetic check of the 17.92 MAD/h rate (not an official worked example)"},
    ],
    "wage_arrears": [
        {"inputs": {"start_date": "2026-01-01", "end_date": "2026-03-31", "monthly_pay": 3000, "hours_per_month": 191}, "expect": {"total_shortfall": 1268.16},
         "official": False, "source": "arithmetic check: 3 x (17.92 x 191 - 3000)"},
    ],
    "inheritance_shares": [
        {"inputs": {"wives": 1, "sons": 1, "daughters": 1}, "expect": {"wives (shared equally)": "1/8", "sons": "7/12", "daughters": "7/24"},
         "official": False, "source": "hand-derived from the fixed-share rules (not an official worked example)"},
    ],
}
