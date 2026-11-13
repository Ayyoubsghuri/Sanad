import pytest

from legalrag.calc.base import CalcError


def test_cash_surcharge_official_example(ctx):
    r = ctx.calcs.run("registration_cash_surcharge", {"date": "2026-07-15", "transfer_type": "real_estate", "price": 500000, "cash_portion": 100000})
    assert r.result["surcharge"] == 2000 and r.verified


def test_only_officially_exemplified_calculators_are_verified(ctx):
    v = {d["tool"]: d["verification"] for d in ctx.calcs.describe()}
    assert v["registration_cash_surcharge"] == "verified_against_official_examples"
    assert all(x == "unverified" for k, x in v.items() if k != "registration_cash_surcharge")


def test_unknown_tool_and_missing_input_fail_closed(ctx):
    with pytest.raises(CalcError):
        ctx.calcs.run("nope", {})
    with pytest.raises(CalcError) as e:
        ctx.calcs.run("minimum_wage", {"date": "2026-02-01", "pay": 3000})
    assert e.value.status == "needs_input"


def _proj(ctx, **kw):
    base = {"start_year": 2026, "end_year": 2031, "monthly_pay": 3500, "hours_per_month": 191}
    return ctx.calcs.run("salary_projection", {**base, **kw}).result["years"]


def test_salary_projection_uses_decree_then_carries_forward(ctx):
    ys = _proj(ctx)
    assert [y["year"] for y in ys] == list(range(2026, 2032))
    assert ys[0]["basis"] == "decree" and ys[0]["rate"] == 17.92 and ys[0]["minimum_monthly"] == 3422.72
    assert all(y["basis"] == "carried_forward" and y["rate"] == 17.92 for y in ys[1:])  # no decree after 2026: unchanged, labelled as such


def test_salary_projection_scenario_growth_and_raise(ctx):
    ys = _proj(ctx, smig_growth_pct=5, annual_raise_pct=2)
    assert ys[1]["basis"] == "scenario" and abs(ys[1]["rate"] - 17.92 * 1.05) < 1e-3
    assert abs(ys[5]["rate"] - 17.92 * 1.05 ** 5) < 1e-3
    r = ctx.calcs.run("salary_projection", {"start_year": 2026, "end_year": 2031, "monthly_pay": 3500, "smig_growth_pct": 5, "annual_raise_pct": 2})
    assert r.result["first_non_compliant_year"] is not None  # raise 2% < minimum +5%: eventually non-compliant
    assert r.warnings and "scenario" in r.warnings[0]


def test_salary_projection_agricultural_year_blends_the_april_change(ctx):
    y = _proj(ctx, sector="agricultural", days_per_month=26, monthly_pay=2500, start_year=2026, end_year=2026)[0]
    assert abs(y["rate"] - (3 * 93.0 + 9 * 97.44) / 12) < 1e-3  # SMAG changes on 2026-04-01


def test_salary_projection_severance_and_bad_input(ctx):
    y = _proj(ctx, employment_start_date="2019-01-01", start_year=2026, end_year=2027)
    assert y[0]["severance_prorata"] > 0 and y[1]["severance_prorata"] > y[0]["severance_prorata"]
    with pytest.raises(CalcError):
        ctx.calcs.run("salary_projection", {"start_year": 2031, "end_year": 2026, "monthly_pay": 1})


def test_wage_arrears_across_decrees_and_gaps(ctx):
    r = ctx.calcs.run("wage_arrears", {"start_date": "2024-11-01", "end_date": "2026-03-31", "monthly_pay": 3000, "hours_per_month": 191}).to_dict()
    res = r["result"]
    assert res["months_not_computed"] == ["2024-11", "2024-12"]  # the pack's table starts in 2025: those months are reported, not guessed
    # 2025: 17.10 x 191 = 3266.10 -> 266.10 x 12 ; 2026 Jan-Mar: 17.92 x 191 = 3422.72 -> 422.72 x 3
    assert abs(res["total_shortfall"] - (266.10 * 12 + 422.72 * 3)) < 0.05
    assert [p["rate"] for p in res["periods"]] == [17.1, 17.92] and res["periods"][0]["months"] == 12


def test_wage_arrears_mid_year_rate_change_pay_raise_and_limit(ctx):
    a = ctx.calcs.run("wage_arrears", {"start_date": "2026-03-01", "end_date": "2026-05-31", "sector": "agricultural", "monthly_pay": 2000, "days_per_month": 26,
                                       "pay_changes": [{"from_date": "2026-05-01", "monthly_pay": 2600}]}).to_dict()["result"]
    assert [p["rate"] for p in a["periods"]][:2] == [93.0, 97.44]  # SMAG rises on 1 April
    assert a["periods"][-1]["shortfall"] == max(0, round(97.44 * 26 - 2600, 2))
    b = ctx.calcs.run("wage_arrears", {"start_date": "2025-01-01", "end_date": "2025-12-31", "monthly_pay": 3000, "contract_end_date": "2026-06-30"}).to_dict()["result"]
    assert b["shortfall_older_than_two_years"] == 0 and b["shortfall_within_two_years"] == b["total_shortfall"]
    c = ctx.calcs.run("wage_arrears", {"start_date": "2025-01-01", "end_date": "2025-12-31", "monthly_pay": 3000, "contract_end_date": "2027-06-30"}).to_dict()["result"]
    assert c["shortfall_older_than_two_years"] > 0  # months before 2025-06-30 are more than two years before the end of the contract
