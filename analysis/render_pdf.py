"""Milestone-branded, table-driven PDF — ONE page per asset.
Page 1 = portfolio data tape + NOI/tax/loss bridge. Then one page per deal that flows
top-to-bottom: NOI & cap-rate bridge (left) + market-rent & economic-loss trend (right) +
resident demographics, with a full-width unit-mix table beneath.

Market rent is HelloData EXECUTED only (seller asking ignored): T12 market = HD365 executed
(mix-weighted), T3 market = HD90 executed. Trade-outs shown gross (face) AND effective.
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


def usd(v):   return f"${v:,.0f}" if v else "—"
def usdM(v):  return f"${v/1e6:,.2f}M" if v else "—"
def k0(v):    return f"{v/1000:,.0f}" if v else ("0" if v == 0 else "—")
def k0s(v):   return f"({abs(v)/1000:,.0f})" if (v or 0) < 0 else (f"{(v or 0)/1000:,.0f}")
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
    lo, caps, walk, mtm, mix, lto = d["losses"], d["caps"], d["walk"], d["mtm"], d["mix"], d["lto"]
    rents, demo, ag = d["rents"], d["demo"], d["agpr"]
    tax_noi = walk["tax"]
    pg = header("Morgan Recap  ·  Asset One-Pager  ·  " + d["label"], d["label"], meta_sub(d), page_no)

    l2l = mtm["loss_to_lease_t12"]
    over = (l2l or 0) < 0
    pg.insight([
        ("In-place rent ", False), (usd(mtm["in_place"]), True),
        ((" is ABOVE executed market" if over else " sits below executed market"), False),
        (" (HelloData T12 ", False), (usd(mtm["mkt_t12_eff"]), True),
        (" / T3 ", False), (usd(mtm["mkt_t3_eff"]), True),
        (f", mkt {spct(mtm['mkt_direction'],1)}). New-lease trade-outs ", False),
        (spct(lto.get("new_tradeout_pct"), 1) + " gross / " + spct(lto.get("new_tradeout_eff_pct"), 1) + " eff", True),
        (". Actual cap ", False), (pct(der["trailing_cap"], 2), True),
        (" vs JLL UW ", False), (pct(der["inplace_cap"], 2), True),
        ((", taxes " + ("+" if tax_noi >= 0 else "−") + usd(abs(tax_noi)) + " to NOI."), True),
    ], size=10.5)

    band_top, band_bot = pg._y, pg._bottom
    # top band (≈58%): bridge (left) + market/loss trend (right), each full-height
    pg._bottom = band_top - 0.58 * (band_top - band_bot)
    mid = pg._bottom
    pg.grid(1, 5, hgap=0.028, vgap=0.0)

    # ── LEFT (cols 0-1, both rows): NOI & cap-rate bridge ──
    def t3(s): return sum(s[-3:]) * 4
    agpr12, agpr3, agprj = op["rentinc_t12"] + sum(op["ltl"]), t3(op["rentinc"]) + t3(op["ltl"]), L["gsr"]["yr0"] + L["ltl"]["yr0"]
    vbn12 = sum(op["vacancy"]) + sum(op["bad_debt"]) + sum(op["nonrev"])
    vbn3 = t3(op["vacancy"]) + t3(op["bad_debt"]) + t3(op["nonrev"])
    vbnj = L["vacancy"]["yr0"] + L["collection"]["yr0"] + L["model"]["yr0"]
    nri12, nri3, nrij = agpr12 + vbn12 + sum(op["concessions"]), agpr3 + vbn3 + t3(op["concessions"]), L["nri"]["yr0"]
    oth12, oth3, othj = op["egr_t12"] - nri12, op["egr_t3_ann"] - nri3, L["egr"]["yr0"] - nrij
    e = op["expense_t12"]
    rm12 = e.get("Contract Svc", 0) + e.get("R&M Int/Ext", 0) + e.get("Turnover", 0)
    rmj = L["contract"]["yr0"] + L["maintenance"]["yr0"] + L["turnover"]["yr0"]
    adm12 = e.get("Mgmt Fee", 0) + e.get("Marketing", 0) + e.get("G&A", 0)
    admj = L["mgmt"]["yr0"] + L["advertising"]["yr0"] + L["ga"]["yr0"] + L["franchise"]["yr0"]
    shown12 = e.get("Real Estate Taxes", 0) + e.get("Insurance", 0) + e.get("Payroll", 0) + e.get("Payroll Burden", 0) + rm12 + e.get("Util W/S", 0) + e.get("Util Common", 0) + adm12
    shownj = L["taxes"]["yr0"] + L["insurance"]["yr0"] + L["salaries"]["yr0"] + rmj + L["utilities"]["yr0"] + admj
    rows = [
        ("Gross Potential Rent", k0s(op["rentinc_t12"]), k0s(t3(op["rentinc"])), k0s(L["gsr"]["yr0"])),
        ("Loss-to-Lease / Gain", k0s(sum(op["ltl"])), k0s(t3(op["ltl"])), k0s(L["ltl"]["yr0"])),
        ("Adjusted GPR (AGPR)", k0s(agpr12), k0s(agpr3), k0s(agprj)),
        ("Vacancy, Bad Debt & NonRev", k0s(vbn12), k0s(vbn3), k0s(vbnj)),
        ("Concessions", k0s(sum(op["concessions"])), k0s(t3(op["concessions"])), k0s(L["conc"]["yr0"])),
        ("Net Rental Income", k0s(nri12), k0s(nri3), k0s(nrij)),
        ("Other Income & Reimb", k0s(oth12), k0s(oth3), k0s(othj)),
        ("Effective Gross Revenue", k0s(op["egr_t12"]), k0s(op["egr_t3_ann"]), k0s(L["egr"]["yr0"])),
        ("Real Estate Taxes", k0(e.get("Real Estate Taxes", 0)), "", k0(L["taxes"]["yr0"])),
        ("Insurance", k0(e.get("Insurance", 0)), "", k0(L["insurance"]["yr0"])),
        ("Payroll & Burden", k0(e.get("Payroll", 0) + e.get("Payroll Burden", 0)), "", k0(L["salaries"]["yr0"])),
        ("Repairs, Contract & Turn", k0(rm12), "", k0(rmj)),
        ("Utilities", k0(e.get("Util W/S", 0) + e.get("Util Common", 0)), "", k0(L["utilities"]["yr0"])),
        ("Mgmt & Admin", k0(adm12), "", k0(admj)),
        ("Other expense", k0(op["opex_t12"] - shown12), "", k0(L["opex"]["yr0"] - shownj)),
        ("Operating Expenses", k0(op["opex_t12"]), "", k0(L["opex"]["yr0"])),
        ("Net Operating Income", k0(op["noi_t12"]), k0(op["noi_t3_ann"]), k0(jll["noi_yr0"])),
    ]
    hl = [2, 5, 7, 8, 15, 16]
    capnote = (f"Caps ÷ ask: Actual T12 {pct(caps['actual_t12']['cap'],2)} · T3 {pct(caps['actual_t3']['cap'],2)} · JLL UW Yr-0 "
               f"{pct(caps['jll_uw_yr0']['cap'],2)} · Yr-1 {pct(caps['jll_yr1']['cap'],2)} · exit {pct(caps['exit']['cap'],2)}.  "
               f"Walk actual→UW ($000): {k0(walk['actual_noi'])} +rev {k0s(walk['rev'])} ±tax {k0s(walk['tax'])} ±opex {k0s(walk['opex_ex_tax'])} = {k0(walk['uw_noi'])}.")
    pg.table(0, 0, 1, 2, headers=["NOI Bridge ($000/yr)", "T12 Act", "T3 Ann", "JLL UW"],
             rows_data=rows, title="NOI & Cap-Rate Bridge", highlight=hl, heat=False, note=capnote)

    # ── RIGHT TOP (cols 2-4): market rent (HD executed) & economic-loss trend ──
    mrows = [
        ["Executed market rent (HD eff)", usd(mtm["mkt_t12_eff"]), usd(mtm["mkt_t3_eff"]), "—"],
        ["In-place vs market (loss-to-lease)", spct(mtm["loss_to_lease_t12"], 1), spct(mtm["loss_to_lease_t3"], 1), "—"],
        ["Vacancy (% AGPR)", pct(lo["vacancy"]["t12"], 1), pct(lo["vacancy"]["t3"], 1), pct(lo["jll"]["vacancy"], 1)],
        ["Concessions (% AGPR)", pct(lo["concessions"]["t12"], 1), pct(lo["concessions"]["t3"], 1), pct(lo["jll"]["concessions"], 1)],
        ["Bad Debt (% AGPR)", pct(lo["bad_debt"]["t12"], 1), pct(lo["bad_debt"]["t3"], 1), pct(lo["jll"]["bad_debt"], 1)],
        ["Loss-to-Lease (% GPR)", pct(lo["ltl"]["t12"], 1), pct(lo["ltl"]["t3"], 1), pct(lo["jll"]["ltl"], 1)],
        ["Economic Occupancy", pct(lo["econ_occ"]["t12"], 1), pct(lo["econ_occ"]["t3"], 1), pct(1 - lo["jll"]["vacancy"], 1)],
        ["NOI (annualized)", usdM(op["noi_t12"]), usdM(op["noi_t3_ann"]), usdM(jll["noi_yr0"])],
    ]
    pg.table(0, 2, 1, 3, headers=["Market Rent & Economic-Loss Trend", "T12", "T3", "JLL UW"],
             rows_data=mrows, title="Market Rent (HelloData Executed) & Loss Trend", highlight=[0, 1], heat=False,
             note="Market = HelloData executed, mix-wtd: T12=HD365, T3=HD90 (seller asking ignored). Loss-to-lease = "
                  "market ÷ in-place − 1 (neg = over-rented). Losses as % of AGPR; T3 vs T12 = momentum.")

    # ── BOTTOM band (≈42%): unit mix (left ~70%) + demographics (right ~30%) ──
    pg._y = mid - 0.050
    pg._bottom = band_bot
    pg.grid(1, 10, hgap=0.028, vgap=0.0)
    umix = []
    for b in mix["by_bed"]:
        ll = (b["hd365_eff"] / b["in_place"] - 1) if (b["in_place"] and b["hd365_eff"]) else None
        umix.append([BEDNAME[b["bed"]], f"{b['units']}", pct(b["occ"] / b["units"], 0) if b["units"] else "—",
                     f"{b['avg_sf']:.0f}", usd(b["in_place"]), usd(b["hd365_eff"]), usd(b["hd90_eff"]), spct(ll, 1),
                     (f"{b['lto_new_n']} ({spct(b['lto_new_to'],0)}/{spct(b.get('lto_new_to_eff'),0)})" if b["lto_new_n"] else "—"),
                     (f"{b['lto_ren_n']} ({spct(b['lto_ren_to'],0)})" if b["lto_ren_n"] else "—"),
                     spct(b["lto_to"], 1)])
    tu = sum(b["units"] for b in mix["by_bed"]); to = sum(b["occ"] for b in mix["by_bed"])
    umix.append(["Total / Wtd", f"{tu}", pct(to / tu, 0) if tu else "—", "",
                 usd(rents["avg_inplace_rent"]), usd(mtm["mkt_t12_eff"]), usd(mtm["mkt_t3_eff"]), spct(mtm["loss_to_lease_t12"], 1),
                 f"{lto.get('new_n',0)} ({spct(lto.get('new_tradeout_pct'),0)}/{spct(lto.get('new_tradeout_eff_pct'),0)})",
                 f"{lto.get('renewal_n',0)} ({spct(lto.get('renewal_tradeout_pct'),0)})", spct(lto.get("tradeout_lease_pct"), 1)])
    pg.table(0, 0, 1, 7, headers=["Bed", "Units", "Occ", "Avg SF", "In-Place", "Mkt T12", "Mkt T3", "vs Mkt",
                                  "New (gross/eff)", "Renewal (T/O)", "Blend T/O"],
             rows_data=umix, title="Unit Mix — In-Place vs HelloData Executed Market, Lease Trade-Outs",
             highlight=[len(umix) - 1], heat=False,
             note=f"In-place = avg occupied lease rent (ties to T1 AGPR: RR {usdM(ag['rr_agpr_mo']*12)} vs T12 {usdM(ag['t1_agpr_mo']*12)}, "
                  f"{spct(ag['var_pct'],1)}). Mkt T12 = HD365 exec eff, Mkt T3 = HD90 exec eff (mix-wtd). vs Mkt = market ÷ in-place − 1 "
                  f"(neg = over-rented). New shown gross/effective; renewal & blend gross.")

    # ── demographics (bottom-right ~30%) ──
    bands = demo["income_dist"]; btot = sum(bands.values()) or 1
    distline = " · ".join(f"{k} {v/btot*100:.0f}%" for k, v in bands.items())
    drows = [
        ["Median HH income", usd(demo["hh_income_median"])],
        ["Mean HH income", usd(demo["hh_income_mean"])],
        ["% earning $100K+", pct(demo["pct_over_100k"], 0)],
        ["Median personal income", usd(demo["personal_income_median"])],
        ["Rent-to-income", pct(der["rent_to_income"], 0)],
        ["Median age / hh size", f"{demo['age_median']:.0f} / {demo['hh_size_median']:.1f}"],
        ["30+ day delinquency", pct(der["delinq_pct"], 1)],
    ]
    pg.table(0, 7, 1, 3, headers=["Resident Demographics", "Value"], rows_data=drows,
             title="Resident Demographics & Credit", heat=False, note=f"Income: {distline}.")

    return pg.save_into(pdf, png_path=os.path.join(OUT, f"asset_{d['key']}.png"), final=True)


# ════════════════════════════════════════════════════════════════════════════
# PORTFOLIO PAGE
# ════════════════════════════════════════════════════════════════════════════
def shortname(x):
    return {"city_centre": "City Centre+Res", "golden_glades": "Golden Glades",
            "pearl_washington": "Pearl Washington", "pearl_21eleven": "Pearl 21 Eleven"}[x["key"]]


def portfolio_page(pdf, deals, page_no):
    tot_units = sum(x["occ"]["units"] for x in deals)
    tot_price = sum(x["jll"]["price"] for x in deals)
    tot_noi = sum(x["op"]["noi_t12"] for x in deals)
    tot_noi_yr0 = sum(x["jll"]["noi_yr0"] for x in deals)
    tot_noi_exit = sum(x["jll"]["noi_exit"] for x in deals)
    tot_exit = sum(x["jll"]["exit_price"] for x in deals)
    tot_tax_noi = sum(x["walk"]["tax"] for x in deals)
    tot_redIQ_tax = sum(x["op"]["expense_t12"].get("Real Estate Taxes", 0) for x in deals)
    tot_uw_tax = sum(x["jll_pnl"]["tax"]["uw_taxes_yr0"] for x in deals)
    blend_inplace = tot_noi_yr0 / tot_price
    blend_trailing = tot_noi / tot_price
    blend_exit = tot_noi_exit / tot_exit
    wtd_occ = sum(x["occ"]["phys_occ"] * x["occ"]["units"] for x in deals) / tot_units

    pg = header("Morgan Recap  ·  Portfolio Recapitalization (JLL)", "Portfolio Data Tape",
                f"4 deals / 5 properties   ·   {tot_units:,} units   ·   3 Houston + 1 Miami   ·   {ASOF}", page_no)
    pg.insight([
        ("The portfolio totals ", False), (f"{tot_units:,} units", True), (" at a ", False),
        (usdM(tot_price) + " ask", True), (" — actual trailing-12 cap ", False), (pct(blend_trailing, 2), True),
        (", JLL UW Year-0 ", False), (pct(blend_inplace, 2), True), (", exit ", False), (pct(blend_exit, 2), True),
        (". New-lease trade-outs negative at 3 of 4; in-place is ABOVE executed market at PW & Golden Glades; "
         "two deals carry assumable ", False), ("3.9–4.3% debt", True), (".", False),
    ], size=11)
    pg.kpis([
        ("Total Units", f"{tot_units:,}", None, None, None, "5 properties / 4 deals"),
        ("Total Ask", usdM(tot_price), None, None, None, f"{usd(tot_price/tot_units)}/unit"),
        ("Actual Cap (T12)", pct(blend_trailing, 2), None, None, None, "seller trailing-12 NOI"),
        ("JLL UW Cap (Yr-0)", pct(blend_inplace, 2), None, None, None, f"exit {pct(blend_exit,2)}"),
        ("Wtd Occupancy", pct(wtd_occ, 1), None, None, wtd_occ >= 0.93, "physical, rent roll"),
        ("Tax Reassess (NOI)", ("+" if tot_tax_noi >= 0 else "−") + usdM(abs(tot_tax_noi)), None, None, tot_tax_noi >= 0,
         f"{spct(tot_tax_noi/tot_noi,0)} of NOI · taxes {spct((tot_uw_tax-tot_redIQ_tax)/tot_redIQ_tax,0)}"),
    ], height=0.10)

    pg.grid(2, 1, vgap=0.07)
    rows = []
    for x in deals:
        j, opx, lto, occ, m = x["jll"], x["op"], x["lto"], x["occ"], x["mtm"]
        rows.append([shortname(x), f"{occ['units']:,}", str(j.get("year_built")), usdM(j["price"]),
                     f"${j['price_unit']/1000:,.0f}K", pct(occ["phys_occ"], 1), usd(x["rents"]["avg_inplace_rent"]),
                     usd(m["mkt_t12_eff"]), spct(m["loss_to_lease_t12"], 1),
                     spct(lto.get("new_tradeout_pct"), 1) + "/" + spct(lto.get("new_tradeout_eff_pct"), 1),
                     usdM(opx["noi_t12"]), pct(x["derived"]["trailing_cap"], 2), pct(x["derived"]["inplace_cap"], 2),
                     pct(j["exit_cap"], 2), pct(j["irr_lev"], 1)])
    rows.append(["PORTFOLIO", f"{tot_units:,}", "—", usdM(tot_price), f"${tot_price/tot_units/1000:,.0f}K",
                 pct(wtd_occ, 1), "—", "—", "—", "—", usdM(tot_noi), pct(blend_trailing, 2),
                 pct(blend_inplace, 2), pct(blend_exit, 2), "—"])
    pg.table(0, 0, 1, 1,
             headers=["Asset", "Units", "Built", "Ask", "$/Unit", "Occ", "In-Place", "Mkt T12", "vs Mkt",
                      "New T/O g/e", "T12 NOI", "Act Cap", "JLL UW Cap", "Exit", "Lev IRR"],
             rows_data=rows, title="Asset-Level Data Tape", highlight=[len(rows) - 1], heat=False,
             note="In-Place = avg occupied lease rent; Mkt T12 = HelloData executed effective, trailing-365d, mix-weighted "
                  "(per-property join); vs Mkt = market ÷ in-place − 1 (neg = over-rented); Act Cap = trailing-12 NOI ÷ ask; "
                  "JLL UW Cap = JLL underwritten Year-0 NOI ÷ price; New T/O shown gross/effective.")
    brows = []
    for x in deals:
        opx, j, der, lo = x["op"], x["jll"], x["derived"], x["losses"]
        ract = opx["expense_t12"].get("Real Estate Taxes", 0); ruw = x["jll_pnl"]["tax"]["uw_taxes_yr0"]
        brows.append([shortname(x), usdM(lo["agpr_t12"]), usdM(opx["egr_t12"]), usdM(opx["opex_t12"]), usdM(opx["noi_t12"]),
                      usdM(j["noi_yr0"]), spct(der["jll_noi_vs_trailing"], 0), usd(ract), usd(ruw),
                      spct((ruw - ract) / ract if ract else 0, 0), pct(lo["vacancy"]["t12"], 1),
                      pct(lo["concessions"]["t12"], 1), pct(lo["ltl"]["t12"], 1)])
    brows.append(["PORTFOLIO", usdM(sum(x["losses"]["agpr_t12"] for x in deals)), usdM(sum(x["op"]["egr_t12"] for x in deals)),
                  usdM(sum(x["op"]["opex_t12"] for x in deals)), usdM(tot_noi), usdM(tot_noi_yr0),
                  spct(tot_noi_yr0 / tot_noi - 1, 0), usd(tot_redIQ_tax), usd(tot_uw_tax),
                  spct((tot_uw_tax - tot_redIQ_tax) / tot_redIQ_tax, 0), "", "", ""])
    pg.table(1, 0, 1, 1,
             headers=["Asset", "AGPR", "T12 EGR", "T12 Opex", "T12 NOI", "JLL NOI", "NOI Δ",
                      "Tax Act", "Tax UW", "Tax Δ", "Vac %AGPR", "Conc %AGPR", "LtL %GPR"],
             rows_data=brows, title="NOI Bridge, Tax Reassessment & Economic Losses (T12)", highlight=[len(brows) - 1], heat=False,
             note="JLL NOI = underwritten Year-0 (in-place). Tax Act = seller trailing taxes (RedIQ); Tax UW reassessed to the "
                  "purchase price (FL steps up; TX/Houston can step down where over-assessed). Vac/Conc as % of AGPR; LtL as % of GPR.")
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
