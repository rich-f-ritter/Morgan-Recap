"""Milestone-branded, table-driven PDF — ONE page per asset + a portfolio page.

Conventions (consistent everywhere):
  • Dollars: $X.XXM (≥ $1M) / $XXXK (≥ $1K) / $X — accounting parens for P&L contras.
  • Per-unit: annual $ per unit, whole dollars ($X,XXX).
  • Rents: $/month, whole dollars. Percentages: caps 2-dp, others 1-dp.
  • "JLL UW" prefixes every JLL-underwritten figure (cap, NOI, tax, LIRR).
  • Market rent = HelloData EXECUTED only (T12 = HD365, T3 = HD90, mix-weighted), with the
    executed-lease sample count n shown. Trade-outs shown gross (face) and effective.
"""
import os, json
import brand_setup  # noqa: F401
from brandkit import theme as T
from brandkit.page import Page
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


def money(v, dec=2):
    if v is None or v == "":
        return "—"
    a = abs(v); s = "-" if v < 0 else ""
    if a >= 1e6:
        return f"{s}${a/1e6:,.{dec}f}M"
    if a >= 1e3:
        return f"{s}${a/1e3:,.0f}K"
    return f"{s}${a:,.0f}"


def acct(v, dec=2):
    """P&L money with accounting parentheses for negatives (negligible → $0)."""
    if v is None or v == "":
        return "—"
    if abs(v) < 500:
        return "$0"
    return f"({money(-v, dec)})" if v < 0 else money(v, dec)


def perU(v, units, dec=0):
    """Per-unit annual $ — accounting parens for negatives, so it matches acct() in the same row."""
    if not (v and units):
        return "—"
    pu = v / units
    if abs(pu) < 0.5:
        return "$0"
    return f"(${abs(pu):,.{dec}f})" if pu < 0 else f"${pu:,.{dec}f}"


def usd(v):   return f"${v:,.0f}" if v else "—"
def pct(v, d=1): return f"{v*100:.{d}f}%" if v is not None else "—"
def spct(v, d=1): return f"{v*100:+.{d}f}%" if v is not None else "—"


def header(kicker, title, subtitle, page_no):
    pg = Page(kicker=kicker, title=title, page_no=page_no, sources=SRC, slim=True)
    pg.fig.text(pg.LEFT, pg._y, subtitle, fontfamily=T.SANS, fontsize=10, fontstyle="italic",
                color=T.GRAY, va="top")
    pg._y -= 0.026
    return pg


def meta_sub(d):
    j = d["jll"]
    state = "FL" if d["key"] == "golden_glades" else (j.get("state") or "")
    return (f"{j.get('city')}, {state}   ·   {d['occ']['units']:,} units   ·   built {j.get('year_built')}"
            f"   ·   {j.get('product') or 'Multifamily'}   ·   {j.get('deal_type')}   ·   {ASOF}")


# ════════════════════════════════════════════════════════════════════════════
# ASSET ONE-PAGER
# ════════════════════════════════════════════════════════════════════════════
def asset_page(pdf, d, page_no):
    op, L, der, jll = d["op"], d["jll_pnl"]["lines"], d["derived"], d["jll"]
    losses, caps, walk, mtm, mix, lto = d["losses"], d["caps"], d["walk"], d["mtm"], d["mix"], d["lto"]
    rents, demo, ag = d["rents"], d["demo"], d["agpr"]
    U = d["occ"]["units"]
    tax_noi = walk["tax"]
    pg = header("Morgan Recap  ·  Asset One-Pager  ·  " + d["label"], d["label"], meta_sub(d), page_no)

    l2l = mtm["loss_to_lease_t12"]
    over = (l2l or 0) < 0
    pg.insight([
        ("Contract rent ", False), (usd(ag["t1_agpr_unit"]) + "/unit", True),
        ((" sits ABOVE executed market" if over else " sits below executed market"), False),
        (" (HelloData T12 ", False), (usd(mtm["mkt_t12_eff"]), True),
        (" / T3 ", False), (usd(mtm["mkt_t3_eff"]), True),
        (f", {spct(l2l,1)}). New-lease trade-outs ", False),
        (spct(lto.get("new_tradeout_pct"), 1) + " gross / " + spct(lto.get("new_tradeout_eff_pct"), 1) + " eff", True),
        (". Actual cap ", False), (pct(der["trailing_cap"], 2), True),
        (" vs JLL UW ", False), (pct(der["inplace_cap"], 2), True),
        ((", reassessed taxes " + ("+" if tax_noi >= 0 else "−") + money(abs(tax_noi)) + " to NOI."), True),
    ], size=10.5)

    band_top, band_bot = pg._y, pg._bottom
    pg._bottom = band_top - 0.58 * (band_top - band_bot)
    mid = pg._bottom
    pg.grid(1, 5, hgap=0.028, vgap=0.0)

    # ── LEFT: NOI & cap-rate bridge (T12 / T3 / JLL UW / per-unit) ──
    def t3(s): return sum(s[-3:]) * 4
    gpr = (op["rentinc_t12"], t3(op["rentinc"]), L["gsr"]["yr0"])
    ltl = (sum(op["ltl"]), t3(op["ltl"]), L["ltl"]["yr0"])
    agpr = (gpr[0] + ltl[0], gpr[1] + ltl[1], gpr[2] + ltl[2])
    vbn = (sum(op["vacancy"]) + sum(op["bad_debt"]) + sum(op["nonrev"]),
           t3(op["vacancy"]) + t3(op["bad_debt"]) + t3(op["nonrev"]),
           L["vacancy"]["yr0"] + L["collection"]["yr0"] + L["model"]["yr0"])
    conc = (sum(op["concessions"]), t3(op["concessions"]), L["conc"]["yr0"])
    nri = (agpr[0] + vbn[0] + conc[0], agpr[1] + vbn[1] + conc[1], L["nri"]["yr0"])
    egr = (op["egr_t12"], op["egr_t3_ann"], L["egr"]["yr0"])
    oth = (egr[0] - nri[0], egr[1] - nri[1], egr[2] - nri[2])
    e = op["expense_t12"]
    rm = e.get("Contract Svc", 0) + e.get("R&M Int/Ext", 0) + e.get("Turnover", 0)
    rmj = L["contract"]["yr0"] + L["maintenance"]["yr0"] + L["turnover"]["yr0"]
    pay = (e.get("Payroll", 0) + e.get("Payroll Burden", 0), L["salaries"]["yr0"])
    adm = (e.get("Mgmt Fee", 0) + e.get("Marketing", 0) + e.get("G&A", 0),
           L["mgmt"]["yr0"] + L["advertising"]["yr0"] + L["ga"]["yr0"] + L["franchise"]["yr0"])
    tax = (e.get("Real Estate Taxes", 0), L["taxes"]["yr0"])
    ins = (e.get("Insurance", 0), L["insurance"]["yr0"])
    ut = (e.get("Util W/S", 0) + e.get("Util Common", 0), L["utilities"]["yr0"])
    opex = (op["opex_t12"], L["opex"]["yr0"])
    shown12 = tax[0] + ins[0] + pay[0] + rm + ut[0] + adm[0]
    shownj = tax[1] + ins[1] + pay[1] + rmj + ut[1] + adm[1]
    noi = (op["noi_t12"], op["noi_t3_ann"], jll["noi_yr0"])
    # rows: (label, t12, t3-or-None, jll, is_pl_contra)
    R = [
        ("Gross Potential Rent", *gpr), ("Loss-to-Lease / Gain", *ltl), ("Adjusted GPR (AGPR)", *agpr),
        ("Vacancy, Bad Debt & NonRev", *vbn), ("Concessions", *conc), ("Net Rental Income", *nri),
        ("Other Income & Reimb", *oth), ("Effective Gross Revenue", *egr),
        ("Real Estate Taxes", tax[0], None, tax[1]), ("Insurance", ins[0], None, ins[1]),
        ("Payroll & Burden", pay[0], None, pay[1]), ("Repairs, Contract & Turn", rm, None, rmj),
        ("Utilities", ut[0], None, ut[1]), ("Mgmt & Admin", adm[0], None, adm[1]),
        ("Other expense", opex[0] - shown12, None, opex[1] - shownj),
        ("Operating Expenses", opex[0], None, opex[1]), ("Net Operating Income", *noi),
    ]
    rows = [[lab, acct(t12), (acct(t3v) if t3v is not None else ""), acct(jllv), perU(t12, U)] for (lab, t12, t3v, jllv) in R]
    hl = [2, 5, 7, 8, 15, 16]
    capnote = (f"Caps ÷ ask: Actual T12 {pct(caps['actual_t12']['cap'],2)} · T3 {pct(caps['actual_t3']['cap'],2)} · JLL UW Yr-0 "
               f"{pct(caps['jll_uw_yr0']['cap'],2)} · JLL Yr-1 {pct(caps['jll_yr1']['cap'],2)} · exit {pct(caps['exit']['cap'],2)}.  "
               f"NOI walk actual→JLL UW: {money(walk['actual_noi'])} {'+' if walk['rev']>=0 else '−'}rev {money(abs(walk['rev']))} "
               f"{'+' if walk['tax']>=0 else '−'}tax {money(abs(walk['tax']))} {'+' if walk['opex_ex_tax']>=0 else '−'}opex "
               f"{money(abs(walk['opex_ex_tax']))} = {money(walk['uw_noi'])}.")
    pg.table(0, 0, 1, 2, headers=["NOI Bridge ($/yr)", "T12 Act", "T3 Ann", "JLL UW", "/Unit"],
             rows_data=rows, title="NOI & Cap-Rate Bridge", highlight=hl, heat=False, note=capnote)

    # ── RIGHT: market rent (HD executed) & economic-loss trend ──
    lo = losses
    mrows = [
        ["Executed market rent (HD eff)", usd(mtm["mkt_t12_eff"]), usd(mtm["mkt_t3_eff"]), "—"],
        ["Executed leases (n)", str(mtm["hd_t12_n"]), str(mtm["hd_t3_n"]), "—"],
        ["Contract rent vs market", spct(mtm["loss_to_lease_t12"], 1), spct(mtm["loss_to_lease_t3"], 1), "—"],
        ["Vacancy (% AGPR)", pct(lo["vacancy"]["t12"], 1), pct(lo["vacancy"]["t3"], 1), pct(lo["jll"]["vacancy"], 1)],
        ["Concessions (% AGPR)", pct(lo["concessions"]["t12"], 1), pct(lo["concessions"]["t3"], 1), pct(lo["jll"]["concessions"], 1)],
        ["Bad Debt (% AGPR)", pct(lo["bad_debt"]["t12"], 1), pct(lo["bad_debt"]["t3"], 1), pct(lo["jll"]["bad_debt"], 1)],
        ["Loss-to-Lease (% GPR)", pct(lo["ltl"]["t12"], 1), pct(lo["ltl"]["t3"], 1), pct(lo["jll"]["ltl"], 1)],
        ["Economic Occupancy", pct(lo["econ_occ"]["t12"], 1), pct(lo["econ_occ"]["t3"], 1), pct(1 - lo["jll"]["vacancy"], 1)],
        ["NOI (annualized)", money(op["noi_t12"]), money(op["noi_t3_ann"]), money(jll["noi_yr0"])],
    ]
    pg.table(0, 2, 1, 3, headers=["Market Rent & Economic-Loss Trend", "T12", "T3", "JLL UW"],
             rows_data=mrows, title="Market Rent (HelloData Executed) & Loss Trend", highlight=[0, 2], heat=False,
             note="Market = HelloData executed, mix-wtd: T12 = HD365 (trailing-365d), T3 = HD90 (trailing-90d); n = executed leases "
                  "in the window (seller asking ignored). Contract-vs-market = market ÷ contract − 1 (neg = over-rented). "
                  "Losses % of AGPR; T3 vs T12 = momentum. JLL UW = model Year-0 assumption.")

    # ── BOTTOM: unit mix (left ~70%) + demographics (right ~30%) ──
    pg._y = mid - 0.050
    pg._bottom = band_bot
    pg.grid(1, 10, hgap=0.028, vgap=0.0)
    umix = []
    for b in mix["by_bed"]:
        ll = (b["hd365_eff"] / b["in_place"] - 1) if (b["in_place"] and b["hd365_eff"]) else None
        umix.append([BEDNAME[b["bed"]], f"{b['units']}", pct(b["occ"] / b["units"], 0) if b["units"] else "—",
                     usd(b["in_place"]), usd(b["hd365_eff"]), usd(b["hd90_eff"]), spct(ll, 1),
                     f"{b['hd365_n']}/{b['hd90_n']}",
                     (f"{b['lto_new_n']} ({spct(b['lto_new_to'],0)}/{spct(b.get('lto_new_to_eff'),0)})" if b["lto_new_n"] else "—"),
                     (f"{b['lto_ren_n']} ({spct(b['lto_ren_to'],0)})" if b["lto_ren_n"] else "—"),
                     spct(b["lto_to"], 1)])
    tu = sum(b["units"] for b in mix["by_bed"]); to = sum(b["occ"] for b in mix["by_bed"])
    umix.append(["Total / Wtd", f"{tu}", pct(to / tu, 0) if tu else "—",
                 usd(round(ag["t1_agpr_unit"])), usd(mtm["mkt_t12_eff"]), usd(mtm["mkt_t3_eff"]), spct(mtm["loss_to_lease_t12"], 1),
                 f"{mtm['hd_t12_n']}/{mtm['hd_t3_n']}",
                 f"{lto.get('new_n',0)} ({spct(lto.get('new_tradeout_pct'),0)}/{spct(lto.get('new_tradeout_eff_pct'),0)})",
                 f"{lto.get('renewal_n',0)} ({spct(lto.get('renewal_tradeout_pct'),0)})", spct(lto.get("tradeout_lease_pct"), 1)])
    pg.table(0, 0, 1, 7, headers=["Bed", "Units", "Occ", "In-Place", "Mkt T12", "Mkt T3", "vs Mkt", "HD n",
                                  "New (gross/eff)", "Renewal (T/O)", "Blend T/O"],
             rows_data=umix, title="Unit Mix — Contract Rent vs HelloData Executed Market, Lease Trade-Outs",
             highlight=[len(umix) - 1], heat=False,
             note=f"In-place = avg occupied contract rent (incl. amenity); Total row = T1 AGPR ÷ units = {usd(round(ag['t1_agpr_unit']))} "
                  f"(ties to financials: RR AGPR {money(ag['rr_agpr_mo']*12)} vs T12 {money(ag['t1_agpr_mo']*12)}, {spct(ag['var_pct'],1)}). "
                  f"Mkt = HD executed eff (T12=HD365, T3=HD90), mix-wtd; HD n = executed leases T365/T90. vs Mkt = market÷contract−1 "
                  f"(neg = over-rented). New trade-out gross/eff; renewal & blend gross.")

    # demographics (right ~30%)
    bands = demo["income_dist"]; btot = sum(bands.values()) or 1
    distline = " · ".join(f"{k} {v/btot*100:.0f}%" for k, v in bands.items())
    drows = [
        ["Median HH income", money(demo["hh_income_median"], 0) if demo["hh_income_median"] >= 1e6 else usd(demo["hh_income_median"])],
        ["Mean HH income", usd(demo["hh_income_mean"])],
        ["% earning $100K+", pct(demo["pct_over_100k"], 0)],
        ["Median personal income", usd(demo["personal_income_median"])],
        ["Rent-to-income", pct(der["rent_to_income"], 0)],
        ["Median age / hh size", f"{demo['age_median']:.0f} / {demo['hh_size_median']:.1f}"],
        ["30+ day delinquency", pct(der["delinq_pct"], 1)],
    ]
    pg.table(0, 7, 1, 3, headers=["Resident Demographics", "Value"], rows_data=drows,
             title="Resident Demographics & Credit", heat=False, note=f"HH-income distribution: {distline}.")
    return pg.save_into(pdf, png_path=os.path.join(OUT, f"asset_{d['key']}.png"), final=True)


# ════════════════════════════════════════════════════════════════════════════
# PORTFOLIO PAGE
# ════════════════════════════════════════════════════════════════════════════
def shortname(x):
    return {"city_centre": "City Centre+Res", "golden_glades": "Golden Glades",
            "pearl_washington": "Pearl Washington", "pearl_21eleven": "Pearl 21 Eleven"}[x["key"]]


def portfolio_page(pdf, deals, page_no):
    U = sum(x["occ"]["units"] for x in deals)
    price = sum(x["jll"]["price"] for x in deals)
    noi = sum(x["op"]["noi_t12"] for x in deals)
    noi_uw = sum(x["jll"]["noi_yr0"] for x in deals)
    noi_exit = sum(x["jll"]["noi_exit"] for x in deals)
    exitp = sum(x["jll"]["exit_price"] for x in deals)
    tax_noi = sum(x["walk"]["tax"] for x in deals)
    ract = sum(x["op"]["expense_t12"].get("Real Estate Taxes", 0) for x in deals)
    ruw = sum(x["jll_pnl"]["tax"]["uw_taxes_yr0"] for x in deals)
    cap_act = noi / price; cap_uw = noi_uw / price; cap_exit = noi_exit / exitp
    occ = sum(x["occ"]["phys_occ"] * x["occ"]["units"] for x in deals) / U

    pg = header("Morgan Recap  ·  Portfolio Recapitalization (JLL)", "Portfolio Data Tape",
                f"4 deals / 5 properties   ·   {U:,} units   ·   3 Houston + 1 Miami   ·   {ASOF}", page_no)
    pg.insight([
        ("The portfolio totals ", False), (f"{U:,} units", True), (" at a ", False),
        (money(price) + " ask", True), (" (", False), (perU(price, U) + "/unit", True),
        (") — actual trailing-12 cap ", False), (pct(cap_act, 2), True), (", JLL UW Year-0 ", False),
        (pct(cap_uw, 2), True), (", exit ", False), (pct(cap_exit, 2), True),
        (". Contract rent is ABOVE executed market at PW & Golden Glades; two deals carry assumable ", False),
        ("3.9–4.3% debt", True), (".", False),
    ], size=11)
    pg.kpis([
        ("Total Units", f"{U:,}", None, None, None, "5 properties / 4 deals"),
        ("Total Ask", money(price), None, None, None, f"{perU(price,U)}/unit"),
        ("Actual Cap (T12)", pct(cap_act, 2), None, None, None, "seller trailing-12 NOI"),
        ("JLL UW Cap (Yr-0)", pct(cap_uw, 2), None, None, None, f"exit {pct(cap_exit,2)}"),
        ("Wtd Occupancy", pct(occ, 1), None, None, occ >= 0.93, "physical, rent roll"),
        ("Tax Reassess (NOI)", ("+" if tax_noi >= 0 else "−") + money(abs(tax_noi)), None, None, tax_noi >= 0,
         f"{spct(tax_noi/noi,0)} of NOI · taxes {spct((ruw-ract)/ract,0)}"),
    ], height=0.10)

    pg.grid(2, 1, vgap=0.07)
    rows = []
    for x in deals:
        j, opx, lto, oc, m = x["jll"], x["op"], x["lto"], x["occ"], x["mtm"]
        rows.append([shortname(x), f"{oc['units']:,}", str(j.get("year_built")), money(j["price"]),
                     perU(j["price"], oc["units"]), pct(oc["phys_occ"], 1), usd(round(x["agpr"]["t1_agpr_unit"])),
                     usd(m["mkt_t12_eff"]), spct(m["loss_to_lease_t12"], 1),
                     spct(lto.get("new_tradeout_pct"), 1) + "/" + spct(lto.get("new_tradeout_eff_pct"), 1),
                     money(opx["noi_t12"]), pct(x["derived"]["trailing_cap"], 2), pct(x["derived"]["inplace_cap"], 2),
                     pct(j["exit_cap"], 2), pct(j["irr_lev"], 1)])
    rows.append(["PORTFOLIO", f"{U:,}", "—", money(price), perU(price, U), pct(occ, 1), "—", "—", "—", "—",
                 money(noi), pct(cap_act, 2), pct(cap_uw, 2), pct(cap_exit, 2), "—"])
    pg.table(0, 0, 1, 1,
             headers=["Asset", "Units", "Built", "Ask", "$/Unit", "Occ", "Contract/U", "Mkt T12", "vs Mkt",
                      "New T/O g/e", "T12 NOI", "Act Cap", "JLL UW Cap", "Exit", "JLL UW LIRR"],
             rows_data=rows, title="Asset-Level Data Tape", highlight=[len(rows) - 1], heat=False,
             note="Contract/U = T1 AGPR ÷ units (monthly, ties to the financials); Mkt T12 = HelloData executed effective, "
                  "trailing-365d, mix-wtd (per-property join); vs Mkt = market ÷ contract − 1 (neg = over-rented); "
                  "Act Cap = trailing-12 NOI ÷ ask; JLL UW Cap = JLL underwritten Year-0 NOI ÷ price; New T/O gross/effective; "
                  "JLL UW LIRR = JLL underwritten levered IRR (5-yr hold).")
    brows = []
    for x in deals:
        opx, j, der, lo, oc = x["op"], x["jll"], x["derived"], x["losses"], x["occ"]
        ra = opx["expense_t12"].get("Real Estate Taxes", 0); ru = x["jll_pnl"]["tax"]["uw_taxes_yr0"]
        brows.append([shortname(x), money(lo["agpr_t12"]), money(opx["egr_t12"]), money(opx["opex_t12"]), money(opx["noi_t12"]),
                      perU(opx["noi_t12"], oc["units"]), money(j["noi_yr0"]), spct(der["jll_noi_vs_trailing"], 0),
                      money(ra), money(ru), spct((ru - ra) / ra if ra else 0, 0), pct(lo["vacancy"]["t12"], 1),
                      pct(lo["concessions"]["t12"], 1), pct(lo["ltl"]["t12"], 1)])
    brows.append(["PORTFOLIO", money(sum(x["losses"]["agpr_t12"] for x in deals)), money(sum(x["op"]["egr_t12"] for x in deals)),
                  money(sum(x["op"]["opex_t12"] for x in deals)), money(noi), perU(noi, U), money(noi_uw),
                  spct(noi_uw / noi - 1, 0), money(ract), money(ruw), spct((ruw - ract) / ract, 0), "", "", ""])
    pg.table(1, 0, 1, 1,
             headers=["Asset", "AGPR", "T12 EGR", "T12 Opex", "T12 NOI", "NOI/U", "NOI (JLL UW)", "NOI Δ",
                      "Tax (Act)", "Tax (JLL UW)", "Tax Δ", "Vac %AGPR", "Conc %AGPR", "LtL %GPR"],
             rows_data=brows, title="NOI Bridge, Tax Reassessment & Economic Losses (T12 actual vs JLL UW)",
             highlight=[len(brows) - 1], heat=False,
             note="NOI (JLL UW) = JLL underwritten Year-0 (in-place). Tax (Act) = seller trailing taxes (RedIQ); Tax (JLL UW) = "
                  "reassessed to the purchase price (FL steps up; TX/Houston can step down where over-assessed). NOI/U = T12 NOI per "
                  "unit (annual). Vacancy/Concessions as % of AGPR; loss-to-lease as % of gross potential.")
    return pg.save_into(pdf, png_path=os.path.join(OUT, "portfolio_tape.png"), final=True)


def main():
    path = os.path.join(OUT, "Morgan_Recap_Analysis.pdf")
    allp = {}
    with PdfPages(path) as pdf:
        allp["portfolio"] = portfolio_page(pdf, DEALS, 1)
        for i, d in enumerate(DEALS, start=2):
            allp[d["key"]] = asset_page(pdf, d, i)
    print("Wrote", path)
    for k, v in allp.items():
        print(f"  {'OK' if not v else 'PROBLEMS'} [{k}]")
        for p in (v or []):
            print("     -", p)


if __name__ == "__main__":
    main()
