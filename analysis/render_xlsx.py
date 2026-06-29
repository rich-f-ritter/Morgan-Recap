"""Render the editable, Milestone-branded Excel data tape:
a Dashboard sheet (KPI cards + asset tape + underwriting table + trend scorecard)
plus raw detail tabs (operating T12 monthly, rent & leasing, underwriting)."""
import os, json
import brand_setup  # noqa: F401
import pandas as pd
from openpyxl import Workbook
from brandkit import xl as XL

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = json.load(open(os.path.join(ROOT, "analysis", "data.json")))
DEALS = DATA["deals"]
OUT = os.path.join(ROOT, "output")
os.makedirs(OUT, exist_ok=True)

SHORT = {"city_centre": "City Centre + Residences", "golden_glades": "Caroline Golden Glades",
         "pearl_washington": "Pearl Washington", "pearl_21eleven": "Pearl 21 Eleven"}
MON = ["May'25", "Jun'25", "Jul'25", "Aug'25", "Sep'25", "Oct'25", "Nov'25", "Dec'25",
       "Jan'26", "Feb'26", "Mar'26", "Apr'26"]


def build():
    wb = Workbook()
    wb.remove(wb.active)
    dash = XL.Dash(wb, title="Portfolio Data Tape")

    tot_units = sum(x["occ"]["units"] for x in DEALS)
    tot_price = sum(x["jll"]["price"] for x in DEALS)
    tot_noi = sum(x["op"]["noi_t12"] for x in DEALS)
    tot_noi_yr0 = sum(x["jll"]["noi_yr0"] for x in DEALS)
    tot_exit = sum(x["jll"]["exit_price"] for x in DEALS)
    tot_noi_exit = sum(x["jll"]["noi_exit"] for x in DEALS)
    blend_goingin = tot_noi_yr0 / tot_price
    blend_trailing = tot_noi / tot_price
    blend_exit = tot_noi_exit / tot_exit
    wtd_occ = sum(x["occ"]["phys_occ"] * x["occ"]["units"] for x in DEALS) / tot_units

    dash.title_band("Morgan Recap  ·  Portfolio Recapitalization (JLL)",
                    "Morgan Recap — Portfolio Data Tape",
                    f"4 deals / 5 properties · {tot_units:,} units · 3 Houston + 1 Miami · "
                    f"data as of May–Jun 2026 (rent rolls/LTO May 2026; T12 May'25–Apr'26)")

    dash.kpi_cards([
        ("Total Units", tot_units, "num", None, None, "5 properties / 4 deals"),
        ("Total Ask", tot_price, "m", None, None, f"${tot_price/tot_units:,.0f}/unit blended"),
        ("Blended JLL UW Cap", blend_goingin, "pct2", f"{blend_trailing*100:.2f}% on actuals", None, "JLL UW Yr-0 NOI ÷ price"),
        ("Blended Exit Cap", blend_exit, "pct2", None, None, "5-yr hold"),
        ("Wtd Occupancy", wtd_occ, "pct", None, wtd_occ >= 0.93, "physical, rent roll"),
        ("Total T12 NOI", tot_noi, "m", f"UW ${tot_noi_yr0/1e6:,.1f}M", None, "seller trailing-12"),
    ])

    # ── Asset data tape ──
    dash.section("Asset-Level Data Tape",
                 "Act Cap = trailing-12 NOI ÷ ask · JLL UW Cap = JLL underwritten Year-0 (in-place) NOI ÷ price · "
                 "Contract /mo = T1 AGPR ÷ units · New T/O = rent-weighted new-lease trade-out vs prior lease (Yardi LTO, T90)")
    cols = [("Market", "text"), ("Units", "num"), ("Built", "year"), ("Ask", "m"), ("$/Unit", "usd"), ("Occ", "pct"),
            ("Contract /mo", "usd"), ("New T/O", "pct"), ("T12 NOI", "m"), ("Act Cap", "pct2"),
            ("JLL UW Cap", "pct2"), ("Yr-1 Cap", "pct2"), ("Exit Cap", "pct2"), ("JLL UW LIRR", "pct"), ("EM", "ratio")]
    rows = []
    for x in DEALS:
        j, op, lto, occ = x["jll"], x["op"], x["lto"], x["occ"]
        rows.append((SHORT[x["key"]], [
            _market(x), occ["units"], _year(j.get("year_built")), j["price"], j["price_unit"], occ["phys_occ"],
            x["agpr"]["t1_agpr_unit"], lto.get("new_tradeout_pct"), op["noi_t12"],
            x["derived"]["trailing_cap"], j["cap_yr0"], j["cap_yr1"], j["exit_cap"], j["irr_lev"], j["em_lev"],
        ], "num", None))
    rows.append(("PORTFOLIO", ["3 Houston · 1 Miami", tot_units, None, tot_price, tot_price / tot_units, wtd_occ, None, None,
                               tot_noi, blend_trailing, blend_goingin, None, blend_exit, None, None], "num", None))
    dash.compare_table("", cols, rows, heat=False)

    # ── Underwriting & returns vs in-place ──
    dash.section("Underwriting vs. In-Place / Trailing  (per asset)")
    cols2 = [("Trailing Cap", "pct2"), ("JLL UW Cap", "pct2"), ("NOI UW vs Trl", "pct"),
             ("Mkt Growth Y1", "pct"), ("New-Lease T/O", "pct"), ("LtL Assumed", "pct"),
             ("Conc Assumed", "pct"), ("T12 Conc", "pct"), ("Debt Rate", "pct2"), ("LTV", "pct")]
    rows2 = []
    for x in DEALS:
        j, der, lto = x["jll"], x["derived"], x["lto"]
        rows2.append((SHORT[x["key"]], [
            der["trailing_cap"], j["cap_yr0"], der["jll_noi_vs_trailing"], j["rent_growth"][0],
            lto.get("new_tradeout_pct"), j["ltl_assume"], j["conc_assume"], der["conc_pct_egr"],
            j["rate"], j["ltv"],
        ], "pct", _debt(j)))
    dash.compare_table("", cols2, rows2, heat=False)

    # ── Trend scorecard ──
    dash.section("Portfolio Trend Scorecard")
    dash.scorecard([
        ("Rents (new-lease)", "negative trade-outs at 3 of 4 assets (PW -15%, GG -12%, 21E -7%); City Centre +4%", "down"),
        ("Occupancy", f"weighted {wtd_occ*100:.1f}% physical; City Centre 97%, Golden Glades / PW ~93%", "flat"),
        ("Concessions", "escalating at Houston assets (PW to ~$16K/mo); Golden Glades lease-up at 6.6% of EGR", "down"),
        ("NOI vs underwriting", f"trailing ${tot_noi/1e6:.1f}M vs JLL Yr-0 ${tot_noi_yr0/1e6:.1f}M (+{ (tot_noi_yr0/tot_noi-1)*100:.0f}%)", "flat"),
        ("Pricing", f"blended {blend_goingin*100:.2f}% in-place cap to {blend_exit*100:.2f}% exit — full vs negative momentum", "down"),
        ("Resident credit", "median HH income $93K–$150K, rent-to-income 19–24%, delinquency <0.5% of GPR", "up"),
        ("Debt", "two assumable loans at 3.9–4.3% IO are the standout value in the recap", "up"),
    ])

    dash.footer("Yardi rent rolls, lease trade-out & delinquency (May 2026); RedIQ-standardized operating statements "
                "(T12 May 2025–Apr 2026); HelloData unit details (Jun 2026); resident demographics (May 2026); JLL models (Jun 2026).")

    # ── raw detail tabs ──
    XL.add_raw_tab(wb, "NOI Bridge (T12 vs JLL)", noibridge_df())
    XL.add_raw_tab(wb, "Cap Stack & NOI Walk", capstack_df())
    XL.add_raw_tab(wb, "Economic Losses (%AGPR)", losses_df())
    XL.add_raw_tab(wb, "Mark-to-Market", mtm_df())
    XL.add_raw_tab(wb, "Operating T12 (monthly)", operating_df())
    XL.add_raw_tab(wb, "Rent & Leasing", leasing_df())
    XL.add_raw_tab(wb, "Unit Mix (by plan)", unitmix_df())
    XL.add_raw_tab(wb, "Underwriting & Returns", underwriting_df())
    XL.add_raw_tab(wb, "Demographics", demo_df())

    path = os.path.join(OUT, "Morgan_Recap_Data_Tape.xlsx")
    wb.save(path)
    print("Wrote", path)


def _year(v):
    try:
        return int(str(v)[:4])
    except Exception:
        return None


def _debt(j):
    return f"{j['financing_type']} {j['rate']*100:.2f}% IO, {j['ltv']*100:.0f}% LTV"


def _market(x):
    j = x["jll"]
    state = "FL" if x["key"] == "golden_glades" else (j.get("state") or "")
    return f"{j.get('city')}, {state}"


def operating_df():
    recs = []
    for x in DEALS:
        op = x["op"]
        for i, m in enumerate(MON):
            recs.append({"Asset": SHORT[x["key"]], "Month": m, "EGR": round(op["egr"][i]),
                         "NOI": round(op["noi"][i]), "Concessions": round(op["concessions"][i]),
                         "Vacancy": round(op["vacancy"][i])})
    return pd.DataFrame(recs)


def leasing_df():
    recs = []
    for x in DEALS:
        j, op, lto, occ, m, mt = x["jll"], x["op"], x["lto"], x["occ"], x["mix"], x["mtm"]
        recs.append({
            "Asset": SHORT[x["key"]], "Units": occ["units"], "Phys Occ": round(occ["phys_occ"], 4),
            "Leased Occ": round(occ["leased_occ"], 4), "In-Place Rent": round(x["rents"]["avg_inplace_rent"]),
            "In-Place PSF": round(x["rents"]["avg_inplace_psf"], 2),
            "Blended T/O": _r(lto.get("tradeout_lease_pct")), "New-Lease T/O": _r(lto.get("new_tradeout_pct")),
            "Renewal T/O": _r(lto.get("renewal_tradeout_pct")),
            "HD T90 Ask": round(m["hd_t90_ask"]), "HD T90 Eff": round(m["hd_t90_eff"]),
            "HD365 leases (n)": mt["hd_t12_n"], "HD90 leases (n)": mt["hd_t3_n"],
            "HD Ask YoY": _r(m.get("hd_yoy_ask")), "T12 Conc % EGR": round(x["derived"]["conc_pct_egr"], 4),
            "30+ Delinq % GPR": round(x["derived"]["delinq_pct"], 4),
        })
    return pd.DataFrame(recs)


def noibridge_df():
    """Per-asset NOI bridge: T12 actual (RedIQ) vs JLL Year-0 (in-place) for each line,
    with AGPR, the tax reassessment (RedIQ actual-tax basis), and the implied caps."""
    recs = []
    for x in DEALS:
        op, L, j, der, lo = x["op"], x["jll_pnl"]["lines"], x["jll"], x["derived"], x["losses"]
        rtax = op["expense_t12"].get("Real Estate Taxes", 0)
        utax = x["jll_pnl"]["tax"]["uw_taxes_yr0"]
        recs.append({
            "Asset": SHORT[x["key"]],
            "GPR (T12)": round(op["rentinc_t12"]), "GPR (JLL Yr0)": round(L["gsr"]["yr0"]),
            "AGPR (T12)": round(lo["agpr_t12"]), "AGPR (JLL Yr0)": round(L["gsr"]["yr0"] + L["ltl"]["yr0"]),
            "EGR (T12)": round(op["egr_t12"]), "EGR (JLL Yr0)": round(L["egr"]["yr0"]),
            "Opex (T12)": round(op["opex_t12"]), "Opex (JLL Yr0)": round(L["opex"]["yr0"]),
            "RE Taxes (T12 actual)": round(rtax), "RE Taxes (JLL UW)": round(utax),
            "Tax Δ %": _r((utax - rtax) / rtax if rtax else 0), "Tax NOI Impact": round(x["walk"]["tax"]),
            "Current Assessment": round(x["jll_pnl"]["tax"]["current_assessment"]),
            "Purchase Basis": round(x["jll_pnl"]["tax"]["purchase_price_basis"]),
            "NOI (T12)": round(op["noi_t12"]), "NOI (T3 ann)": round(op["noi_t3_ann"]), "NOI (JLL Yr0)": round(j["noi_yr0"]),
            "Actual Cap (T12)": _r(der["trailing_cap"]), "JLL UW Cap (Yr0)": _r(der["inplace_cap"]),
            "NOI UW vs Trailing": _r(der["jll_noi_vs_trailing"]),
        })
    return pd.DataFrame(recs)


def losses_df():
    """Economic losses as a % of AGPR on a T12 / T6 / T3 trend, per asset, vs JLL Year-0."""
    recs = []
    for x in DEALS:
        lo = x["losses"]
        r = {"Asset": SHORT[x["key"]], "AGPR T12": round(lo["agpr_t12"]), "AGPR T3 ann": round(lo["agpr_t3"])}
        for metric in ("ltl", "vacancy", "bad_debt", "concessions"):
            lab = {"ltl": "Loss-to-Lease", "vacancy": "Vacancy", "bad_debt": "Bad Debt", "concessions": "Concessions"}[metric]
            r[f"{lab} T12"] = _r(lo[metric]["t12"]); r[f"{lab} T6"] = _r(lo[metric]["t6"])
            r[f"{lab} T3"] = _r(lo[metric]["t3"]); r[f"{lab} JLL"] = _r(lo["jll"][metric])
        r["Econ Occ T12"] = _r(lo["econ_occ"]["t12"]); r["Econ Occ T3"] = _r(lo["econ_occ"]["t3"])
        recs.append(r)
    return pd.DataFrame(recs)


def capstack_df():
    """Cap-rate stack and the NOI walk (actual trailing-12 -> JLL underwritten Year-0)."""
    recs = []
    for x in DEALS:
        c, w = x["caps"], x["walk"]
        recs.append({
            "Asset": SHORT[x["key"]],
            "Actual T12 NOI": round(c["actual_t12"]["noi"]), "Actual T12 Cap": _r(c["actual_t12"]["cap"]),
            "Actual T3 NOI": round(c["actual_t3"]["noi"]), "Actual T3 Cap": _r(c["actual_t3"]["cap"]),
            "Walk: +Revenue": round(w["rev"]), "Walk: ±Tax": round(w["tax"]), "Walk: ±Opex": round(w["opex_ex_tax"]),
            "JLL UW Yr0 NOI": round(c["jll_uw_yr0"]["noi"]), "JLL UW Yr0 Cap": _r(c["jll_uw_yr0"]["cap"]),
            "JLL Yr1 NOI": round(c["jll_yr1"]["noi"]), "JLL Yr1 Cap": _r(c["jll_yr1"]["cap"]),
            "Exit NOI": round(c["exit"]["noi"]), "Exit Cap": _r(c["exit"]["cap"]),
        })
    return pd.DataFrame(recs)


def mtm_df():
    """Mark-to-market: contract rent (T1 AGPR/unit) vs HelloData EXECUTED rents
    (T12=HD365, T3=HD90, mix-wtd, with executed-lease sample n) + forward signal."""
    recs = []
    for x in DEALS:
        m, lto = x["mtm"], x["lto"]
        recs.append({
            "Asset": SHORT[x["key"]], "Contract Rent (T1 AGPR/unit)": round(x["agpr"]["t1_agpr_unit"]),
            "Avg In-Place (occupied)": round(m["in_place"]),
            "Mkt T12 (HD365 eff)": round(m["mkt_t12_eff"]), "Mkt T3 (HD90 eff)": round(m["mkt_t3_eff"]),
            "Mkt T12 (HD365 ask)": round(m["mkt_t12_ask"]), "Mkt T3 (HD90 ask)": round(m["mkt_t3_ask"]),
            "HD365 leases (n)": m["hd_t12_n"], "HD90 leases (n)": m["hd_t3_n"],
            "Contract vs Mkt T12": _r(m["loss_to_lease_t12"]), "Contract vs Mkt T3": _r(m["loss_to_lease_t3"]),
            "Market Direction (T3 vs T12)": _r(m["mkt_direction"]),
            "HD Concession T12": _r(m["conc_t12"]), "HD Concession T3": _r(m["conc_t3"]),
            "New-Lease T/O (gross)": _r(lto.get("new_tradeout_pct")), "New-Lease T/O (eff)": _r(lto.get("new_tradeout_eff_pct")),
            "Renewal T/O (gross)": _r(lto.get("renewal_tradeout_pct")), "HD Asking YoY": _r(m["hd_yoy"]),
        })
    return pd.DataFrame(recs)


def unitmix_df():
    """Per-floor-plan unit mix across all deals: in-place, HD90/HD365 asking & effective,
    new vs renewal counts, last-5 new-lease average, HD asking YoY."""
    recs = []
    for x in DEALS:
        for m in x["mix"]["by_plan"]:
            recs.append({"Asset": SHORT[x["key"]], "Plan": m["plan"],
                         "Bed": m["bed"], "Bath": m["bath"], "Units": m["units"],
                         "Occ": m["occ"], "Vac": m["vac"], "Avg SF": m["avg_sf"],
                         "In-Place": m["in_place"], "HD90 Ask": m["hd90_ask"], "HD90 Eff": m["hd90_eff"],
                         "HD365 Ask": m["hd365_ask"], "HD365 Eff": m["hd365_eff"],
                         "New Leases": m["new_n"], "Renewals": m["renewal_n"],
                         "Last5 New Avg": m["last5_new_avg"], "HD Ask YoY": _r(m["hd_yoy_ask"])})
    return pd.DataFrame(recs)


def underwriting_df():
    recs = []
    for x in DEALS:
        j, op, der = x["jll"], x["op"], x["derived"]
        recs.append({
            "Asset": SHORT[x["key"]], "Year Built": j.get("year_built"), "Units": j["units"],
            "Price": round(j["price"]), "Price/Unit": round(j["price_unit"]), "Price/SF": round(j["price_sf"], 0),
            "CapEx": round(j["capex"]), "Total Cost": round(j["total_cost"]),
            "Trailing NOI (T12)": round(op["noi_t12"]), "JLL NOI Yr0": round(j["noi_yr0"]),
            "JLL NOI Yr1": round(j["noi_yr1"]), "Trailing Cap": _r(der["trailing_cap"]),
            "JLL Cap Yr0": _r(j["cap_yr0"]), "JLL Cap Yr1": _r(j["cap_yr1"]), "Exit Cap": _r(j["exit_cap"]),
            "Exit Price": round(j["exit_price"]), "Financing": j["financing_type"], "Loan Amt": round(j["loan_amount"]),
            "Rate": _r(j["rate"]), "LTV": _r(j["ltv"]), "Lev IRR": _r(j["irr_lev"]), "LP IRR": _r(j["irr_lp"]),
            "EM (lev)": round(j["em_lev"], 2), "Hold (mo)": int(j["hold_months"]),
            "Rent Growth Y1-3": "/".join(f"{g*100:.1f}%" for g in j["rent_growth"][:3]),
        })
    return pd.DataFrame(recs)


def demo_df():
    recs = []
    for x in DEALS:
        de = x["demo"]
        bands = de.get("income_dist", {})
        btot = sum(bands.values()) or 1
        recs.append({
            "Asset": SHORT[x["key"]], "Resident Median HH Income": round(de["hh_income_median"]),
            "Resident Mean HH Income": round(de["hh_income_mean"]),
            "% Earning $100K+": round(de.get("pct_over_100k", 0), 3),
            "Median Personal Income": round(de["personal_income_median"]),
            "Median HH Size": round(de.get("hh_size_median", 0), 1), "Median Age": round(de["age_median"], 0),
            "Rent-to-Income": round(x["derived"]["rent_to_income"], 3),
            "Inc <$50K": round(bands.get("<$50K", 0) / btot, 3),
            "Inc $50-75K": round(bands.get("$50–75K", 0) / btot, 3),
            "Inc $75-100K": round(bands.get("$75–100K", 0) / btot, 3),
            "Inc $100K+": round(bands.get("$100K+", 0) / btot, 3),
            "Resident Records": round(de.get("resident_total", 0)), "Prospect Leads": round(de.get("lead_count", 0)),
        })
    return pd.DataFrame(recs)


def _r(v, n=4):
    return round(v, n) if isinstance(v, (int, float)) else v


if __name__ == "__main__":
    build()
