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
        ("Blended Going-in Cap", blend_goingin, "pct2", f"{blend_trailing*100:.2f}% on actuals", None, "JLL Yr-0 NOI ÷ price"),
        ("Blended Exit Cap", blend_exit, "pct2", None, None, "5-yr hold"),
        ("Wtd Occupancy", wtd_occ, "pct", None, wtd_occ >= 0.93, "physical, rent roll"),
        ("Total T12 NOI", tot_noi, "m", f"UW ${tot_noi_yr0/1e6:,.1f}M", None, "seller trailing-12"),
    ])

    # ── Asset data tape ──
    dash.section("Asset-Level Data Tape",
                 "Act Cap = trailing-12 NOI ÷ ask · JLL Cap = underwritten Year-0 (in-place) NOI ÷ price · "
                 "New T/O = rent-weighted new-lease trade-out vs prior lease (Yardi LTO, T90)")
    cols = [("Units", "num"), ("Built", "year"), ("Ask", "m"), ("$/Unit", "usd"), ("Occ", "pct"),
            ("In-Place /mo", "usd"), ("New T/O", "pct"), ("T12 NOI", "m"), ("Act Cap", "pct2"),
            ("In-Place Cap", "pct2"), ("Yr-1 Cap", "pct2"), ("Exit Cap", "pct2"), ("Lev IRR", "pct"), ("EM", "ratio")]
    rows = []
    for x in DEALS:
        j, op, lto, occ = x["jll"], x["op"], x["lto"], x["occ"]
        rows.append((SHORT[x["key"]], [
            occ["units"], _year(j.get("year_built")), j["price"], j["price_unit"], occ["phys_occ"],
            x["rents"]["avg_inplace_rent"], lto.get("new_tradeout_pct"), op["noi_t12"],
            x["derived"]["trailing_cap"], j["cap_yr0"], j["cap_yr1"], j["exit_cap"], j["irr_lev"], j["em_lev"],
        ], "num", None))
    rows.append(("PORTFOLIO", [tot_units, None, tot_price, tot_price / tot_units, wtd_occ, None, None,
                               tot_noi, blend_trailing, blend_goingin, None, blend_exit, None, None], "num", None))
    dash.compare_table("", cols, rows, heat=False)

    # ── Underwriting & returns vs in-place ──
    dash.section("Underwriting vs. In-Place / Trailing  (per asset)")
    cols2 = [("Trailing Cap", "pct2"), ("JLL In-Place Cap", "pct2"), ("NOI UW vs Trl", "pct"),
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
        j, op, lto, occ, m = x["jll"], x["op"], x["lto"], x["occ"], x["mix"]
        recs.append({
            "Asset": SHORT[x["key"]], "Units": occ["units"], "Phys Occ": round(occ["phys_occ"], 4),
            "Leased Occ": round(occ["leased_occ"], 4), "In-Place Rent": round(x["rents"]["avg_inplace_rent"]),
            "In-Place PSF": round(x["rents"]["avg_inplace_psf"], 2),
            "Blended T/O": _r(lto.get("tradeout_lease_pct")), "New-Lease T/O": _r(lto.get("new_tradeout_pct")),
            "Renewal T/O": _r(lto.get("renewal_tradeout_pct")),
            "HD T90 Ask": round(m["hd_t90_ask"]), "HD T90 Eff": round(m["hd_t90_eff"]),
            "HD Ask YoY": _r(m.get("hd_yoy_ask")), "T12 Conc % EGR": round(x["derived"]["conc_pct_egr"], 4),
            "30+ Delinq % GPR": round(x["derived"]["delinq_pct"], 4),
        })
    return pd.DataFrame(recs)


def noibridge_df():
    """Per-asset NOI bridge: T12 actual vs JLL Year-0 (in-place) for each line, with
    the tax reassessment and the implied caps at the asking price."""
    recs = []
    for x in DEALS:
        op, L, j, der = x["op"], x["jll_pnl"]["lines"], x["jll"], x["derived"]
        e = op["expense_t12"]
        tx = x["jll_pnl"]["tax"]
        recs.append({
            "Asset": SHORT[x["key"]],
            "GPR (T12)": round(op["rentinc_t12"]), "GPR (JLL Yr0)": round(L["gsr"]["yr0"]),
            "EGR (T12)": round(op["egr_t12"]), "EGR (JLL Yr0)": round(L["egr"]["yr0"]),
            "Opex (T12)": round(op["opex_t12"]), "Opex (JLL Yr0)": round(L["opex"]["yr0"]),
            "RE Taxes (T12 actual)": round(tx["actual_taxes"]), "RE Taxes (JLL UW)": round(tx["uw_taxes_yr0"]),
            "Tax Adjustment": round(tx["adjustment"]),
            "Current Assessment": round(tx["current_assessment"]), "Purchase Basis": round(tx["purchase_price_basis"]),
            "NOI (T12)": round(op["noi_t12"]), "NOI (T3 ann)": round(op["noi_t3_ann"]), "NOI (JLL Yr0)": round(j["noi_yr0"]),
            "Trailing Cap": _r(der["trailing_cap"]), "In-Place Cap (JLL)": _r(der["inplace_cap"]),
            "NOI UW vs Trailing": _r(der["jll_noi_vs_trailing"]),
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
