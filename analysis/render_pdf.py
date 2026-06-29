"""Render the Milestone-branded, TABLE-DRIVEN PDF:
page 1 = portfolio data tape + NOI/cap bridge summary; pages 2-5 = per-deal one-pagers,
each built around (1) a full NOI & cap-rate bridge (Revenue T12/T3/JLL, Expenses T12/JLL,
tax-reassessment line, NOI, implied cap), (2) an in-place-vs-market unit-mix table tied to
T1 AGPR, and (3) a resident-demographics table."""
import os, json
import brand_setup  # noqa: F401
from brandkit import theme as T
from brandkit.page import Page
from brandkit import panels as P
from matplotlib.backends.backend_pdf import PdfPages

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = json.load(open(os.path.join(ROOT, "analysis", "data.json")))
DEALS = DATA["deals"]
OUT = os.path.join(ROOT, "output")
os.makedirs(OUT, exist_ok=True)
SRC = ("Yardi rent rolls, lease trade-out (LTO) & delinquency (May 2026); RedIQ-standardized "
       "operating statements (T12 May 2025–Apr 2026); HelloData executed rents (Jun 2026); "
       "resident demographics (May 2026); JLL underwriting models (Jun 2026).")
ASOF = "Data as of May–Jun 2026"
BEDNAME = {0: "Studio", 1: "1BR", 2: "2BR", 3: "3BR", 4: "4BR", 5: "5BR", None: "Other"}


def usd(v):   return f"${v:,.0f}" if v is not None else "—"
def usdk(v):  return f"${v/1000:,.0f}K" if v else "—"
def usdM(v):  return f"${v/1e6:,.1f}M" if v else "—"
def k0(v):    return f"{v/1000:,.0f}" if v else "0"        # $000s, no sign symbol
def k0s(v):   return f"({abs(v)/1000:,.0f})" if (v or 0) < 0 else f"{(v or 0)/1000:,.0f}"  # accounting
def pct(v, d=1): return f"{v*100:.{d}f}%" if v is not None else "—"
def spct(v, d=1): return f"{v*100:+.{d}f}%" if v is not None else "—"


# ════════════════════════════════════════════════════════════════════════════
# NOI & CAP-RATE BRIDGE  (the centerpiece)
# ════════════════════════════════════════════════════════════════════════════
def bridge_rows(d):
    op, L, der, jll = d["op"], d["jll_pnl"]["lines"], d["derived"], d["jll"]
    e = d["op"]["expense_t12"]
    def t12(s): return sum(s)
    def t3(s):  return sum(s[-3:]) * 4
    price = jll["price"]
    # ── revenue (T12 | T3-ann | JLL Yr0) ──
    gpr12, gpr3, gprj = op["rentinc_t12"], t3(op["rentinc"]), L["gsr"]["yr0"]
    ltl12, ltl3, ltlj = t12(op["ltl"]), t3(op["ltl"]), L["ltl"]["yr0"]
    vac12, vac3, vacj = t12(op["vacancy"]), t3(op["vacancy"]), L["vacancy"]["yr0"] + L["model"]["yr0"]
    con12, con3, conj = t12(op["concessions"]), t3(op["concessions"]), L["conc"]["yr0"]
    egr12, egr3, egrj = op["egr_t12"], op["egr_t3_ann"], L["egr"]["yr0"]
    oth12 = egr12 - gpr12 - ltl12 - vac12 - con12
    oth3 = egr3 - gpr3 - ltl3 - vac3 - con3
    othj = egrj - gprj - ltlj - vacj - conj
    rev = [
        ("Gross Potential Rent", k0s(gpr12), k0s(gpr3), k0s(gprj)),
        ("Loss-to-Lease / Gain", k0s(ltl12), k0s(ltl3), k0s(ltlj)),
        ("Vacancy & Non-Revenue", k0s(vac12), k0s(vac3), k0s(vacj)),
        ("Concessions", k0s(con12), k0s(con3), k0s(conj)),
        ("Other Income, Reimb & Adj", k0s(oth12), k0s(oth3), k0s(othj)),
        ("Effective Gross Revenue", k0s(egr12), k0s(egr3), k0s(egrj)),
    ]
    # ── expenses (T12 | — | JLL Yr0); T3 expenses intentionally omitted ──
    tax12, taxj = e.get("Real Estate Taxes", 0), L["taxes"]["yr0"]
    ins12, insj = e.get("Insurance", 0), L["insurance"]["yr0"]
    pay12, payj = e.get("Payroll", 0) + e.get("Payroll Burden", 0), L["salaries"]["yr0"]
    mgt12, mgtj = e.get("Mgmt Fee", 0), L["mgmt"]["yr0"]
    rm12 = e.get("Contract Svc", 0) + e.get("R&M Int/Ext", 0) + e.get("Turnover", 0)
    rmj = L["contract"]["yr0"] + L["maintenance"]["yr0"] + L["turnover"]["yr0"]
    ut12, utj = e.get("Util W/S", 0) + e.get("Util Common", 0), L["utilities"]["yr0"]
    ad12, adj = e.get("Marketing", 0) + e.get("G&A", 0), L["advertising"]["yr0"] + L["ga"]["yr0"]
    opex12, opexj = op["opex_t12"], L["opex"]["yr0"]
    oth_e12 = opex12 - (tax12 + ins12 + pay12 + mgt12 + rm12 + ut12 + ad12)
    oth_ej = opexj - (taxj + insj + payj + mgtj + rmj + utj + adj) + L["franchise"]["yr0"]
    exp = [
        ("Real Estate Taxes", k0(tax12), "", k0(taxj)),
        ("Insurance", k0(ins12), "", k0(insj)),
        ("Payroll & Burden", k0(pay12), "", k0(payj)),
        ("Repairs, Contract & Turn", k0(rm12), "", k0(rmj)),
        ("Utilities", k0(ut12), "", k0(utj)),
        ("Management Fee", k0(mgt12), "", k0(mgtj)),
        ("Marketing & G&A", k0(ad12), "", k0(adj)),
        ("Other / franchise", k0(oth_e12), "", k0(oth_ej)),
        ("Operating Expenses", k0(opex12), "", k0(opexj)),
    ]
    noi = [
        ("Net Operating Income", k0(op["noi_t12"]), k0(op["noi_t3_ann"]), k0(jll["noi_yr0"])),
        ("Implied cap @ ask", pct(der["trailing_cap"], 2), pct(der["forward_cap_t3"], 2), pct(der["inplace_cap"], 2)),
    ]
    rows = rev + exp + noi
    # highlight EGR(5), Opex(14), NOI(15), Cap(16) and Taxes(6)
    hl = [5, 6, 14, 15, 16]
    return rows, hl


# ════════════════════════════════════════════════════════════════════════════
# ASSET ONE-PAGER
# ════════════════════════════════════════════════════════════════════════════
def asset_page(pdf, d, page_no):
    j, op, lto, mix, occ = d["jll"], d["op"], d["lto"], d["mix"], d["occ"]
    rents, demo, der, ag = d["rents"], d["demo"], d["derived"], d["agpr"]
    tax = d["jll_pnl"]["tax"]
    city = j.get("city") or ""
    state = "FL" if d["key"] == "golden_glades" else (j.get("state") or "")
    sub = (f"{city}, {state}   ·   {occ['units']:,} units   ·   built {j.get('year_built')}"
           f"   ·   {j.get('product') or 'Multifamily'}   ·   {j.get('deal_type')}   ·   {ASOF}")
    pg = Page(kicker="Morgan Recap  ·  Asset One-Pager  ·  " + d["label"],
              title=d["label"], page_no=page_no, sources=SRC, slim=True)
    pg.fig.text(pg.LEFT, pg._y, sub, fontfamily=T.SANS, fontsize=10, fontstyle="italic",
                color=T.GRAY, va="top")
    pg._y -= 0.028

    newt = lto.get("new_tradeout_pct")
    direction = "softening" if (newt or 0) < -0.01 else ("firming" if (newt or 0) > 0.01 else "holding")
    pg.insight([
        ("In-place cap ", False), (pct(der["inplace_cap"], 2), True),
        (" (JLL Year-0 NOI ÷ price) vs ", False), (pct(der["trailing_cap"], 2) + " on trailing-12 actuals", True),
        (" — a ", False), (spct(der["jll_noi_vs_trailing"], 0) + " NOI lift", True),
        (", with reassessed taxes ", False),
        (("+" if tax["adjustment"] >= 0 else "−") + usd(abs(tax["adjustment"])), True),
        (". New-lease trade-outs ", False), (spct(newt, 1), True),
        ("; rents ", False), (direction, True),
        (" vs a ", False), (pct(j["rent_growth"][0], 0) + "–" + pct(j["rent_growth"][1], 0) + " growth plan", True),
        (".", False),
    ], size=11)

    debt = f"{('Assumption' if 'Assum' in str(j['financing_type']) else 'New')} {pct(j['rate'],2)} IO"
    pg.kpis([
        ("Units", f"{occ['units']:,}", None, None, None, f"{j.get('product') or ''} · {j.get('year_built')}"),
        ("Physical Occupancy", pct(occ["phys_occ"], 1), None, None, occ["phys_occ"] >= 0.93, f"economic {pct(occ['avail_occ'],1)}"),
        ("In-Place Rent /mo", usd(rents["avg_inplace_rent"]), None, None, None, f"${rents['avg_inplace_psf']:.2f}/SF · AGPR/unit {usd(ag['rr_agpr_unit'])}"),
        ("In-Place Cap", pct(der["inplace_cap"], 2), None, None, None, f"trailing {pct(der['trailing_cap'],2)} · exit {pct(j['exit_cap'],2)}"),
        ("Asking Price", usdM(j["price"]), None, None, None, f"{usd(j['price_unit'])}/unit · ${j['price_sf']:.0f}/SF"),
        ("Levered IRR / EM", f"{pct(j['irr_lev'],1)} / {j['em_lev']:.2f}x", None, None, None, f"debt {debt} · {pct(j['ltv'],0)} LTV"),
    ], height=0.112)

    band_top, band_bot = pg._y, pg._bottom
    pg.grid(2, 5, hgap=0.030, vgap=0.085)

    # ── LEFT (cols 0-1, full height): NOI & cap-rate bridge ──
    rows, hl = bridge_rows(d)
    bnote = (f"In-place cap = JLL Year-0 NOI (in-place rents, normalized expenses, reassessed taxes, before reserves) ÷ "
             f"${j['price']/1e6:.1f}M ask. Trailing = seller T12 actual NOI ÷ ask; T3 = trailing-3-mo annualized (revenue/NOI only). "
             f"Tax basis: current assessment {usdM(tax['current_assessment'])} → purchase {usdM(tax['purchase_price_basis'])}; "
             f"UW taxes {usdM(tax['uw_taxes_yr0'])} ({spct(tax['adjustment']/tax['actual_taxes'] if tax['actual_taxes'] else 0,0)} vs actual).")
    pg.table(0, 0, 2, 2, headers=["NOI Bridge ($000/yr)", "T12 Act", "T3 Ann", "JLL UW"],
             rows_data=rows, title="NOI & Cap-Rate Bridge", note=bnote, highlight=hl, heat=False)

    # ── RIGHT TOP (cols 2-4): in-place vs market unit mix ──
    umix = []
    for b in mix["by_bed"]:
        umix.append([
            BEDNAME[b["bed"]], f"{b['units']}", pct(b["occ"] / b["units"], 0) if b["units"] else "—",
            f"{b['avg_sf']:.0f}", usd(b["in_place"]), usd(b["hd90_ask"]), usd(b["hd365_ask"]),
            (f"{b['lto_new_n']} ({spct(b['lto_new_to'],0)})" if b["lto_new_n"] else "—"),
            f"{b['lto_ren_n']}", spct(b["lto_to"], 1),
        ])
    tot_u = sum(b["units"] for b in mix["by_bed"])
    tot_o = sum(b["occ"] for b in mix["by_bed"])
    umix.append(["Total / Wtd", f"{tot_u}", pct(tot_o / tot_u, 0) if tot_u else "—", "",
                 usd(rents["avg_inplace_rent"]), usd(mix["hd_t90_ask"]), usd(mix["hd_t365_ask"]),
                 f"{lto.get('new_n',0)} ({spct(lto.get('new_tradeout_pct'),0)})",
                 f"{lto.get('renewal_n',0)}", spct(lto.get("tradeout_lease_pct"), 1)])
    mnote = (f"In-place = avg occupied lease rent; ties to T1 AGPR — RR in-place AGPR {usdM(ag['rr_agpr_mo']*12)} vs "
             f"T12 AGPR {usdM(ag['t1_agpr_mo']*12)} ({spct(ag['var_pct'],1)}). HD90/HD365 = HelloData executed asking "
             f"(T90/T365), mix-weighted; HD effective T90 {usd(mix['hd_t90_eff'])}. T/O = LTO trade-out vs prior lease.")
    pg.table(0, 2, 1, 3, headers=["Bed", "Units", "Occ", "Avg SF", "In-Place", "HD90", "HD365", "New (T/O)", "Ren", "Blend T/O"],
             rows_data=umix, title="In-Place vs Market & Unit Mix", note=mnote, highlight=[len(umix) - 1], heat=False)

    # ── RIGHT BOTTOM (cols 2-4): resident demographics ──
    bands = demo["income_dist"]
    btot = sum(bands.values()) or 1
    distline = " · ".join(f"{k} {v/btot*100:.0f}%" for k, v in bands.items())
    drows = [
        ["Median household income", usd(demo["hh_income_median"]), f"{pct(demo['pct_over_100k'],0)} earn $100K+"],
        ["Median personal income", usd(demo["personal_income_median"]), f"mean HH {usd(demo['hh_income_mean'])}"],
        ["Rent-to-income (in-place)", pct(der["rent_to_income"], 0), "healthy < 30%" if der["rent_to_income"] < 0.30 else "elevated"],
        ["Median age / household size", f"{demo['age_median']:.0f} / {demo['hh_size_median']:.1f}", f"{demo['resident_total']:.0f} resident records"],
        ["30+ day delinquency", pct(der["delinq_pct"], 1), f"of GPR · net bal {usdk(d['delinq']['net_balance'])}"],
    ]
    dnote = f"Resident household-income distribution: {distline}.  Prospect pool (leads): {demo['lead_count']:.0f} records."
    pg.table(1, 2, 1, 3, headers=["Resident Demographics", "Value", "Context"],
             rows_data=drows, title="Resident Demographics & Credit", note=dnote, heat=False)

    probs = pg.save_into(pdf, png_path=os.path.join(OUT, f"asset_{d['key']}.png"), final=True)
    return probs


# ════════════════════════════════════════════════════════════════════════════
# PORTFOLIO SUMMARY / DATA TAPE
# ════════════════════════════════════════════════════════════════════════════
def shortname(x):
    return {"city_centre": "City Centre+Res", "golden_glades": "Golden Glades",
            "pearl_washington": "Pearl Washington", "pearl_21eleven": "Pearl 21 Eleven"}[x["key"]]


def portfolio_page(pdf, deals, page_no):
    tot_units = sum(x["occ"]["units"] for x in deals)
    tot_price = sum(x["jll"]["price"] for x in deals)
    tot_noi = sum(x["op"]["noi_t12"] for x in deals)
    tot_noi_yr0 = sum(x["jll"]["noi_yr0"] for x in deals)
    tot_exit = sum(x["jll"]["exit_price"] for x in deals)
    tot_noi_exit = sum(x["jll"]["noi_exit"] for x in deals)
    tot_taxadj = sum(x["jll_pnl"]["tax"]["adjustment"] for x in deals)
    blend_inplace = tot_noi_yr0 / tot_price
    blend_trailing = tot_noi / tot_price
    blend_exit = tot_noi_exit / tot_exit
    wtd_occ = sum(x["occ"]["phys_occ"] * x["occ"]["units"] for x in deals) / tot_units

    pg = Page(kicker="Morgan Recap  ·  Portfolio Recapitalization (JLL)",
              title="Portfolio Data Tape", page_no=page_no, sources=SRC, slim=True)
    pg.fig.text(pg.LEFT, pg._y, f"4 deals / 5 properties   ·   {tot_units:,} units   ·   3 Houston + 1 Miami   ·   {ASOF}",
                fontfamily=T.SANS, fontsize=10, fontstyle="italic", color=T.GRAY, va="top")
    pg._y -= 0.028
    pg.insight([
        ("The portfolio totals ", False), (f"{tot_units:,} units", True), (" at a ", False),
        (usdM(tot_price) + " ask", True), (" — a blended ", False), (pct(blend_inplace, 2) + " in-place cap", True),
        (" (", False), (pct(blend_trailing, 2) + " on trailing actuals", True), (") to a ", False),
        (pct(blend_exit, 2) + " exit", True), (". New-lease trade-outs are negative at three of four assets; "
         "two deals carry assumable ", False), ("3.9–4.3% debt", True), (".", False),
    ], size=11.5)
    pg.kpis([
        ("Total Units", f"{tot_units:,}", None, None, None, "5 properties / 4 deals"),
        ("Total Ask", usdM(tot_price), None, None, None, f"{usd(tot_price/tot_units)}/unit"),
        ("Blended In-Place Cap", pct(blend_inplace, 2), None, None, None, f"{pct(blend_trailing,2)} on actuals"),
        ("Blended Exit Cap", pct(blend_exit, 2), None, None, None, "5-yr hold"),
        ("Wtd Occupancy", pct(wtd_occ, 1), None, None, wtd_occ >= 0.93, "physical, rent roll"),
        ("T12 NOI / UW NOI", f"{usdM(tot_noi)} / {usdM(tot_noi_yr0)}", None, None, None, f"tax reassess {spct(tot_taxadj/abs(tot_noi),0) if tot_noi else ''} of NOI"),
    ], height=0.112)

    pg.grid(2, 1, vgap=0.085)
    # ── data tape (top) ──
    rows = []
    for x in deals:
        j, opx, lto, occ = x["jll"], x["op"], x["lto"], x["occ"]
        rows.append([
            shortname(x), f"{occ['units']:,}", str(j.get("year_built")), usdM(j["price"]),
            usdk(j["price_unit"]), pct(occ["phys_occ"], 1), usd(x["rents"]["avg_inplace_rent"]),
            usd(x["mix"]["hd_t90_ask"]), spct(lto.get("new_tradeout_pct"), 1), usdM(opx["noi_t12"]),
            pct(x["derived"]["trailing_cap"], 2), pct(x["derived"]["inplace_cap"], 2),
            pct(j["exit_cap"], 2), pct(j["irr_lev"], 1),
        ])
    rows.append(["PORTFOLIO", f"{tot_units:,}", "—", usdM(tot_price), usdk(tot_price / tot_units),
                 pct(wtd_occ, 1), "—", "—", "—", usdM(tot_noi), pct(blend_trailing, 2),
                 pct(blend_inplace, 2), pct(blend_exit, 2), "—"])
    pg.table(0, 0, 1, 1,
             headers=["Asset", "Units", "Built", "Ask", "$/Unit", "Occ", "In-Place", "HD90",
                      "New T/O", "T12 NOI", "Act Cap", "InPl Cap", "Exit", "Lev IRR"],
             rows_data=rows, title="Asset-Level Data Tape", highlight=[len(rows) - 1], heat=False,
             note="In-Place = avg occupied lease rent; HD90 = HelloData executed T90 asking (mix-wtd); "
                  "Act Cap = trailing-12 NOI ÷ ask; InPl Cap = JLL Year-0 (in-place) NOI ÷ price.")
    # ── NOI bridge & reassessment summary (bottom) ──
    brows = []
    for x in deals:
        opx, j, der, tx = x["op"], x["jll"], x["derived"], x["jll_pnl"]["tax"]
        brows.append([
            shortname(x), usdM(opx["egr_t12"]), usdM(opx["opex_t12"]), usdM(opx["noi_t12"]),
            usdM(j["noi_yr0"]), spct(der["jll_noi_vs_trailing"], 0),
            usd(tx["actual_taxes"]), usd(tx["uw_taxes_yr0"]), spct(tx["adjustment"] / tx["actual_taxes"] if tx["actual_taxes"] else 0, 0),
            f"{pct(j['rent_growth'][0],0)}/{pct(j['rent_growth'][1],0)}/{pct(j['rent_growth'][2],0)}",
            pct(j["ltl_assume"], 1), pct(j["conc_assume"], 1),
        ])
    brows.append(["PORTFOLIO", usdM(sum(x["op"]["egr_t12"] for x in deals)),
                  usdM(sum(x["op"]["opex_t12"] for x in deals)), usdM(tot_noi), usdM(tot_noi_yr0),
                  spct(tot_noi_yr0 / tot_noi - 1, 0), usd(sum(x["jll_pnl"]["tax"]["actual_taxes"] for x in deals)),
                  usd(sum(x["jll_pnl"]["tax"]["uw_taxes_yr0"] for x in deals)),
                  spct(tot_taxadj / sum(x["jll_pnl"]["tax"]["actual_taxes"] for x in deals), 0), "", "", ""])
    pg.table(1, 0, 1, 1,
             headers=["Asset", "T12 EGR", "T12 Opex", "T12 NOI", "JLL NOI", "NOI Δ",
                      "Tax Act", "Tax UW", "Tax Δ", "Rent Gr Y1-3", "LtL", "Conc"],
             rows_data=brows, title="NOI Bridge, Tax Reassessment & JLL Assumptions",
             highlight=[len(brows) - 1], heat=False,
             note="JLL NOI = underwritten Year-0 (in-place). Tax Act = seller trailing taxes; Tax UW = JLL taxes reassessed "
                  "to the purchase price (FL steps up, TX/Houston can step down where currently over-assessed). "
                  "LtL/Conc = JLL assumed loss-to-lease / concessions.")

    probs = pg.save_into(pdf, png_path=os.path.join(OUT, "portfolio_tape.png"), final=True)
    return probs


def main():
    path = os.path.join(OUT, "Morgan_Recap_Analysis.pdf")
    allprobs = {}
    with PdfPages(path) as pdf:
        allprobs["portfolio"] = portfolio_page(pdf, DEALS, 1)
        for i, d in enumerate(DEALS, start=2):
            allprobs[d["key"]] = asset_page(pdf, d, i)
    print("Wrote", path)
    for k, v in allprobs.items():
        print(f"  {'OK' if not v else 'LAYOUT PROBLEMS'} [{k}]" + ("" if not v else ":"))
        for p in (v or []):
            print("     -", p)


if __name__ == "__main__":
    main()
