"""Milestone-branded, table-driven PDF. Page 1 = portfolio data tape + NOI/cap/tax bridge.
Then TWO pages per deal:
  A — Financials: NOI & cap-rate bridge (AGPR built out), the cap-rate STACK with explicit
      definitions + the NOI walk (actual -> JLL underwritten), and economic losses as a
      % of AGPR on a T12/T6/T3 trend.
  B — Rents & Residents: mark-to-market (in-place vs HelloData market/effective), the full
      unit mix (in-place / HD90 / HD365 / new & renewal counts / trade-outs by bed), and a
      resident-demographics table.
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


def usd(v):   return f"${v:,.0f}" if v is not None else "—"
def usdk(v):  return f"${v/1000:,.0f}K" if v else "—"
def usdM(v):  return f"${v/1e6:,.2f}M" if v else "—"
def k0(v):    return f"{v/1000:,.0f}" if v else ("0" if v == 0 else "—")
def k0s(v):   return f"({abs(v)/1000:,.0f})" if (v or 0) < 0 else (f"{(v or 0)/1000:,.0f}")
def pct(v, d=1): return f"{v*100:.{d}f}%" if v is not None else "—"
def spct(v, d=1): return f"{v*100:+.{d}f}%" if v is not None else "—"


def header(pg_kicker, title, subtitle, page_no, slim=True):
    pg = Page(kicker=pg_kicker, title=title, page_no=page_no, sources=SRC, slim=slim)
    pg.fig.text(pg.LEFT, pg._y, subtitle, fontfamily=T.SANS, fontsize=10, fontstyle="italic",
                color=T.GRAY, va="top")
    pg._y -= 0.028
    return pg


def meta_sub(d):
    j = d["jll"]
    state = "FL" if d["key"] == "golden_glades" else (j.get("state") or "")
    return (f"{j.get('city')}, {state}   ·   {d['occ']['units']:,} units   ·   built {j.get('year_built')}"
            f"   ·   {j.get('product') or 'Multifamily'}   ·   {j.get('deal_type')}   ·   {ASOF}")


# ════════════════════════════════════════════════════════════════════════════
# PAGE A — FINANCIALS
# ════════════════════════════════════════════════════════════════════════════
def asset_financials(pdf, d, page_no):
    op, L, der, jll = d["op"], d["jll_pnl"]["lines"], d["derived"], d["jll"]
    tax, caps, walk, losses = d["jll_pnl"]["tax"], d["caps"], d["walk"], d["losses"]
    e = op["expense_t12"]
    pg = header("Morgan Recap  ·  Asset Brief (1 of 2)  ·  Financials & Cap Rate  ·  " + d["label"],
                d["label"], meta_sub(d), page_no)
    tax_noi = d["walk"]["tax"]          # NOI impact of reassessment (RedIQ-actual basis): + = taxes fall
    pg.insight([
        ("Actual trailing-12 cap of ", False), (pct(der["trailing_cap"], 2), True),
        (" (seller NOI ÷ ask) vs JLL's underwritten ", False), (pct(der["inplace_cap"], 2) + " Year-0", True),
        (" — the gap is reassessed taxes (", False),
        (("+" if tax_noi >= 0 else "−") + usdk(abs(tax_noi)) + " to NOI", True),
        (") plus expense normalization. AGPR ", False),
        (("losing" if losses["ltl"]["t3"] > losses["ltl"]["t12"] else "holding"), False),
        (" vs market; loss-to-lease ", False), (pct(losses["ltl"]["t12"], 1), True), (".", False),
    ], size=11)
    pg.kpis([
        ("AGPR (T12)", usdM(losses["agpr_t12"]), None, None, None, "GPR + loss-to-lease"),
        ("EGR (T12)", usdM(op["egr_t12"]), None, None, None, f"T3 ann {usdM(op['egr_t3_ann'])}"),
        ("NOI (T12 actual)", usdM(op["noi_t12"]), None, None, None, f"T3 ann {usdM(op['noi_t3_ann'])}"),
        ("Actual Cap (T12)", pct(der["trailing_cap"], 2), None, None, None, f"T3 run-rate {pct(der['forward_cap_t3'],2)}"),
        ("JLL UW Cap (Yr-0)", pct(der["inplace_cap"], 2), None, None, None, f"Yr-1 {pct(jll['cap_yr1'],2)} · exit {pct(jll['exit_cap'],2)}"),
        ("Tax Reassess (NOI)", ("+" if tax_noi >= 0 else "−") + usdk(abs(tax_noi)), None, None, tax_noi >= 0,
         f"assess {usdM(tax['current_assessment'])}→{usdM(tax['purchase_price_basis'])}"),
    ], height=0.112)

    pg.grid(2, 5, hgap=0.030, vgap=0.085)

    # ── LEFT (cols 0-1, full height): NOI bridge with AGPR built out ──
    def t3(s): return sum(s[-3:]) * 4
    agpr12, agpr3, agprj = op["rentinc_t12"] + sum(op["ltl"]), t3(op["rentinc"]) + t3(op["ltl"]), L["gsr"]["yr0"] + L["ltl"]["yr0"]
    nri12 = agpr12 + sum(op["vacancy"]) + sum(op["bad_debt"]) + sum(op["concessions"]) + sum(op["nonrev"])
    nri3 = agpr3 + t3(op["vacancy"]) + t3(op["bad_debt"]) + t3(op["concessions"]) + t3(op["nonrev"])
    nrij = L["nri"]["yr0"]
    oth12, oth3, othj = op["egr_t12"] - nri12, op["egr_t3_ann"] - nri3, L["egr"]["yr0"] - nrij
    rev = [
        ("Gross Potential Rent", k0s(op["rentinc_t12"]), k0s(t3(op["rentinc"])), k0s(L["gsr"]["yr0"])),
        ("Loss-to-Lease / Gain", k0s(sum(op["ltl"])), k0s(t3(op["ltl"])), k0s(L["ltl"]["yr0"])),
        ("Adjusted GPR (AGPR)", k0s(agpr12), k0s(agpr3), k0s(agprj)),
        ("Vacancy", k0s(sum(op["vacancy"])), k0s(t3(op["vacancy"])), k0s(L["vacancy"]["yr0"])),
        ("Bad Debt / Collection", k0s(sum(op["bad_debt"])), k0s(t3(op["bad_debt"])), k0s(L["collection"]["yr0"])),
        ("Concessions", k0s(sum(op["concessions"])), k0s(t3(op["concessions"])), k0s(L["conc"]["yr0"])),
        ("Non-Revenue Units", k0s(sum(op["nonrev"])), k0s(t3(op["nonrev"])), k0s(L["model"]["yr0"])),
        ("Net Rental Income", k0s(nri12), k0s(nri3), k0s(nrij)),
        ("Other Income & Reimb", k0s(oth12), k0s(oth3), k0s(othj)),
        ("Effective Gross Revenue", k0s(op["egr_t12"]), k0s(op["egr_t3_ann"]), k0s(L["egr"]["yr0"])),
    ]
    rm12 = e.get("Contract Svc", 0) + e.get("R&M Int/Ext", 0) + e.get("Turnover", 0)
    rmj = L["contract"]["yr0"] + L["maintenance"]["yr0"] + L["turnover"]["yr0"]
    pay12, payj = e.get("Payroll", 0) + e.get("Payroll Burden", 0), L["salaries"]["yr0"]
    exp_lines = [
        ("Real Estate Taxes", e.get("Real Estate Taxes", 0), L["taxes"]["yr0"]),
        ("Insurance", e.get("Insurance", 0), L["insurance"]["yr0"]),
        ("Payroll & Burden", pay12, payj),
        ("Repairs, Contract & Turn", rm12, rmj),
        ("Utilities", e.get("Util W/S", 0) + e.get("Util Common", 0), L["utilities"]["yr0"]),
        ("Management Fee", e.get("Mgmt Fee", 0), L["mgmt"]["yr0"]),
        ("Marketing & G&A", e.get("Marketing", 0) + e.get("G&A", 0), L["advertising"]["yr0"] + L["ga"]["yr0"]),
    ]
    shown12 = sum(x[1] for x in exp_lines)
    shownj = sum(x[2] for x in exp_lines)
    exp = [(lbl, k0(v12), "", k0(vj)) for lbl, v12, vj in exp_lines]
    exp.append(("Other / franchise", k0(op["opex_t12"] - shown12), "", k0(L["opex"]["yr0"] - shownj + L["franchise"]["yr0"])))
    exp.append(("Operating Expenses", k0(op["opex_t12"]), "", k0(L["opex"]["yr0"])))
    noi = [("Net Operating Income", k0(op["noi_t12"]), k0(op["noi_t3_ann"]), k0(jll["noi_yr0"]))]
    rows = rev + exp + noi
    hl = [2, 7, 9, 10, len(rows) - 2, len(rows) - 1]   # AGPR, NRI, EGR, Taxes, Opex, NOI
    pg.table(0, 0, 2, 2, headers=["NOI Bridge ($000/yr)", "T12 Act", "T3 Ann", "JLL UW"],
             rows_data=rows, title="NOI & Cap-Rate Bridge", highlight=hl, heat=False,
             note="AGPR (Adjusted Gross Potential Rent) = Gross Potential Rent + Loss-to-Lease, off the financials. "
                  "EGR ties to the RedIQ standardized statement (RUBS grossed up: EGR & Opex both carry the reimbursement, "
                  "NOI unchanged). T3 = trailing-3-mo annualized (revenue/NOI only; expenses shown full-year).")

    # ── RIGHT TOP: cap-rate stack + NOI walk ──
    cap = caps
    crows = [
        ["Actual NOI — Trailing-12 (in-place)", usdM(cap["actual_t12"]["noi"]), pct(cap["actual_t12"]["cap"], 2)],
        ["Actual NOI — T3 annualized (run-rate)", usdM(cap["actual_t3"]["noi"]), pct(cap["actual_t3"]["cap"], 2)],
        ["  walk:  + revenue normalization", k0s(walk["rev"]) + "K", ""],
        ["  walk:  ± tax reassessment", k0s(walk["tax"]) + "K", ""],
        ["  walk:  ± expense normalization", k0s(walk["opex_ex_tax"]) + "K", ""],
        ["JLL underwritten NOI — Year-0", usdM(cap["jll_uw_yr0"]["noi"]), pct(cap["jll_uw_yr0"]["cap"], 2)],
        ["JLL underwritten NOI — Year-1", usdM(cap["jll_yr1"]["noi"]), pct(cap["jll_yr1"]["cap"], 2)],
        ["Exit NOI — Year-5 @ exit cap", usdM(cap["exit"]["noi"]), pct(cap["exit"]["cap"], 2)],
    ]
    pg.table(0, 2, 1, 3, headers=["Cap-Rate Stack & NOI Walk (÷ ask)", "NOI", "Cap"],
             rows_data=crows, title="Cap-Rate Definitions & Reconciliation", highlight=[0, 5], heat=False,
             note="Actual Trailing-12 = seller's standardized T12 NOI ÷ ask (the true in-place cap). "
                  "T3 = last-3-mo annualized. JLL Year-0 = the SAME in-place rent roll but with normalized expenses and "
                  "taxes reassessed to the purchase price — the walk above bridges the two. Year-1 = after one year of "
                  "growth/value-add; Exit = Year-5 residual ÷ exit price.")

    # ── RIGHT BOTTOM: economic losses (% of AGPR) trend ──
    lo = losses
    lrows = [
        ["Loss-to-Lease (% of GPR)", pct(lo["ltl"]["t12"], 1), pct(lo["ltl"]["t6"], 1), pct(lo["ltl"]["t3"], 1), pct(lo["jll"]["ltl"], 1)],
        ["Vacancy", pct(lo["vacancy"]["t12"], 1), pct(lo["vacancy"]["t6"], 1), pct(lo["vacancy"]["t3"], 1), pct(lo["jll"]["vacancy"], 1)],
        ["Bad Debt", pct(lo["bad_debt"]["t12"], 1), pct(lo["bad_debt"]["t6"], 1), pct(lo["bad_debt"]["t3"], 1), pct(lo["jll"]["bad_debt"], 1)],
        ["Concessions", pct(lo["concessions"]["t12"], 1), pct(lo["concessions"]["t6"], 1), pct(lo["concessions"]["t3"], 1), pct(lo["jll"]["concessions"], 1)],
        ["Economic Occupancy", pct(lo["econ_occ"]["t12"], 1), pct(lo["econ_occ"]["t6"], 1), pct(lo["econ_occ"]["t3"], 1), pct(1 - lo["jll"]["vacancy"], 1)],
    ]
    pg.table(1, 2, 1, 3, headers=["Economic Loss (% of AGPR)", "T12", "T6", "T3", "JLL UW"],
             rows_data=lrows, title="Economic Losses & Occupancy — Trend (% of AGPR)", heat=False,
             note="Losses as a share of AGPR on a trailing 12 / 6 / 3-month basis (loss-to-lease shown vs gross potential). "
                  "T3 above T12 = deteriorating; below = tightening. JLL = the model's Year-0 assumption.")

    probs = pg.save_into(pdf, png_path=os.path.join(OUT, f"asset_{d['key']}_A.png"), final=True)
    return probs


# ════════════════════════════════════════════════════════════════════════════
# PAGE B — RENTS & RESIDENTS
# ════════════════════════════════════════════════════════════════════════════
def asset_rents(pdf, d, page_no):
    mix, lto, rents, demo, der, ag, mtm = d["mix"], d["lto"], d["rents"], d["demo"], d["derived"], d["agpr"], d["mtm"]
    pg = header("Morgan Recap  ·  Asset Brief (2 of 2)  ·  Rents, Leasing & Residents  ·  " + d["label"],
                d["label"], meta_sub(d), page_no)
    ll = mtm["loss_to_lease_pct"]
    pg.insight([
        ("In-place rent ", False), (usd(mtm["in_place"]), True), (" vs HelloData market ", False),
        (usd(mtm["hd_market_t90"]) + " (T90)", True), (" — ", False),
        (("embedded loss-to-lease " if (ll or 0) > 0 else "rents above market "), False),
        (spct(ll, 1), True), (". New-lease trade-outs ", False), (spct(mtm["new_lease_to"], 1), True),
        (", HelloData asking ", False), (spct(mtm["hd_yoy"], 1) + " YoY", True),
        ("; resident median income ", False), (usd(demo["hh_income_median"]), True),
        (" (rent-to-income ", False), (pct(der["rent_to_income"], 0), True), (").", False),
    ], size=11)
    pg.kpis([
        ("In-Place Rent /mo", usd(rents["avg_inplace_rent"]), None, None, None, f"${rents['avg_inplace_psf']:.2f}/SF"),
        ("HD Market T90", usd(mtm["hd_market_t90"]), None, None, None, f"T365 {usd(mtm['hd_market_t365'])}, mix-wtd"),
        ("Loss-to-Lease", spct(ll, 1), None, None, (ll or 0) > 0, "in-place vs HD market"),
        ("New-Lease Trade-Out", spct(mtm["new_lease_to"], 1), None, None, (mtm["new_lease_to"] or 0) >= 0,
         f"{lto.get('new_n',0)} new / {lto.get('renewal_n',0)} renewals (T90)"),
        ("HD Asking YoY", spct(mtm["hd_yoy"], 1), None, None, (mtm["hd_yoy"] or 0) >= 0, "HelloData executed"),
        ("Resident Median Income", usd(demo["hh_income_median"]), None, None, None, f"rent-to-income {pct(der['rent_to_income'],0)}"),
    ], height=0.112)

    # unit mix on top ~40% of the band, mark-to-market + demographics below
    band_top, band_bot = pg._y, pg._bottom
    pg._bottom = band_top - 0.40 * (band_top - band_bot)
    mid = pg._bottom
    pg.grid(1, 5, hgap=0.030, vgap=0.0)

    # ── unit mix by bed (full width top) ──
    umix = []
    for b in mix["by_bed"]:
        umix.append([
            BEDNAME[b["bed"]], f"{b['units']}", pct(b["occ"] / b["units"], 0) if b["units"] else "—",
            f"{b['avg_sf']:.0f}", usd(b["in_place"]), usd(b["hd90_ask"]), usd(b["hd90_eff"]), usd(b["hd365_ask"]),
            (f"{b['lto_new_n']} ({spct(b['lto_new_to'],0)})" if b["lto_new_n"] else "—"),
            (f"{b['lto_ren_n']} ({spct(b['lto_ren_to'],0)})" if b["lto_ren_n"] else "—"),
            spct(b["lto_to"], 1),
        ])
    tu = sum(b["units"] for b in mix["by_bed"]); to = sum(b["occ"] for b in mix["by_bed"])
    umix.append(["Total / Wtd", f"{tu}", pct(to / tu, 0) if tu else "—", "",
                 usd(rents["avg_inplace_rent"]), usd(mix["hd_t90_ask"]), usd(mix["hd_t90_eff"]), usd(mix["hd_t365_ask"]),
                 f"{lto.get('new_n',0)} ({spct(lto.get('new_tradeout_pct'),0)})",
                 f"{lto.get('renewal_n',0)} ({spct(lto.get('renewal_tradeout_pct'),0)})", spct(lto.get("tradeout_lease_pct"), 1)])
    pg.table(0, 0, 1, 5, headers=["Bed", "Units", "Occ", "Avg SF", "In-Place", "HD90 Ask", "HD90 Eff",
                                  "HD365 Ask", "New (T/O)", "Renewal (T/O)", "Blend T/O"],
             rows_data=umix, title="Unit Mix — In-Place vs Market, Lease Trade-Outs", highlight=[len(umix) - 1], heat=False,
             note=f"In-place = avg occupied lease rent; ties to T1 AGPR — RR AGPR {usdM(ag['rr_agpr_mo']*12)} vs T12 AGPR "
                  f"{usdM(ag['t1_agpr_mo']*12)} ({spct(ag['var_pct'],1)}). HD90/HD365 = HelloData executed asking & effective "
                  f"(T90/T365), mix-weighted, per-property join. (T/O) = trade-out vs prior lease (T90).")

    # ── mark-to-market + demographics (bottom 60%) ──
    pg._y = mid - 0.055
    pg._bottom = band_bot
    pg.grid(1, 5, hgap=0.030, vgap=0.0)
    mrows = [
        ["In-place rent (avg occ.)", usd(mtm["in_place"])],
        ["HD market — T90 asking", usd(mtm["hd_market_t90"])],
        ["HD market — T365 asking", usd(mtm["hd_market_t365"])],
        ["Loss / (gain) to lease", spct(ll, 1)],
        ["HD effective — T90", usd(mtm["hd_eff_t90"])],
        ["HD concession (ask→eff)", pct(mtm["hd_conc_pct"], 1)],
        ["New-lease trade-out (T90)", spct(mtm["new_lease_to"], 1)],
        ["HD asking YoY", spct(mtm["hd_yoy"], 1)],
    ]
    pg.table(0, 0, 1, 2, headers=["Mark-to-Market", "Value"], rows_data=mrows,
             title="Mark-to-Market & Forward Signal", heat=False,
             note="Loss-to-lease = HD market ÷ in-place − 1 (>0 = upside).")

    # ── demographics (right bottom, wider) ──
    bands = demo["income_dist"]; btot = sum(bands.values()) or 1
    distline = " · ".join(f"{k} {v/btot*100:.0f}%" for k, v in bands.items())
    drows = [
        ["Median household income", usd(demo["hh_income_median"]), f"{pct(demo['pct_over_100k'],0)} earn $100K+"],
        ["Mean household income", usd(demo["hh_income_mean"]), "(skewed by open top band)"],
        ["Median personal income", usd(demo["personal_income_median"]), "per earner"],
        ["Rent-to-income (in-place)", pct(der["rent_to_income"], 0), "healthy < 30%" if der["rent_to_income"] < 0.30 else "elevated"],
        ["Median age / household size", f"{demo['age_median']:.0f} / {demo['hh_size_median']:.1f}", f"{demo['resident_total']:.0f} records"],
        ["30+ day delinquency", pct(der["delinq_pct"], 1), f"of GPR · net bal {usdk(d['delinq']['net_balance'])}"],
    ]
    pg.table(0, 2, 1, 3, headers=["Resident Demographics & Credit", "Value", "Context"], rows_data=drows,
             title="Resident Demographics & Credit", heat=False,
             note=f"Household-income distribution: {distline}.  Prospect pool (leads): {demo['lead_count']:.0f} records.")

    probs = pg.save_into(pdf, png_path=os.path.join(OUT, f"asset_{d['key']}_B.png"), final=True)
    return probs


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
    tot_exit = sum(x["jll"]["exit_price"] for x in deals)
    tot_noi_exit = sum(x["jll"]["noi_exit"] for x in deals)
    tot_tax_noi = sum(x["walk"]["tax"] for x in deals)   # NOI impact of reassessment (RedIQ basis)
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
        (usdM(tot_price) + " ask", True), (" — an actual trailing-12 cap of ", False),
        (pct(blend_trailing, 2), True), (", a JLL underwritten ", False), (pct(blend_inplace, 2) + " Year-0", True),
        (", and a ", False), (pct(blend_exit, 2) + " exit", True),
        (". New-lease trade-outs are negative at three of four assets; two deals carry assumable ", False),
        ("3.9–4.3% debt", True), (".", False),
    ], size=11.5)
    pg.kpis([
        ("Total Units", f"{tot_units:,}", None, None, None, "5 properties / 4 deals"),
        ("Total Ask", usdM(tot_price), None, None, None, f"{usd(tot_price/tot_units)}/unit"),
        ("Actual Cap (T12)", pct(blend_trailing, 2), None, None, None, "seller trailing-12 NOI"),
        ("JLL UW Cap (Yr-0)", pct(blend_inplace, 2), None, None, None, f"exit {pct(blend_exit,2)}"),
        ("Wtd Occupancy", pct(wtd_occ, 1), None, None, wtd_occ >= 0.93, "physical, rent roll"),
        ("Tax Reassess (NOI)", ("+" if tot_tax_noi >= 0 else "−") + usdM(abs(tot_tax_noi)), None, None, tot_tax_noi >= 0,
         f"{spct(tot_tax_noi/tot_noi,0)} of NOI · taxes {spct((tot_uw_tax-tot_redIQ_tax)/tot_redIQ_tax,0)}"),
    ], height=0.112)

    pg.grid(2, 1, vgap=0.085)
    rows = []
    for x in deals:
        j, opx, lto, occ = x["jll"], x["op"], x["lto"], x["occ"]
        rows.append([shortname(x), f"{occ['units']:,}", str(j.get("year_built")), usdM(j["price"]),
                     usdk(j["price_unit"]), pct(occ["phys_occ"], 1), usd(x["rents"]["avg_inplace_rent"]),
                     usd(x["mix"]["hd_t90_ask"]), spct(x["mtm"]["loss_to_lease_pct"], 1),
                     spct(lto.get("new_tradeout_pct"), 1), usdM(opx["noi_t12"]),
                     pct(x["derived"]["trailing_cap"], 2), pct(x["derived"]["inplace_cap"], 2),
                     pct(j["exit_cap"], 2), pct(j["irr_lev"], 1)])
    rows.append(["PORTFOLIO", f"{tot_units:,}", "—", usdM(tot_price), usdk(tot_price / tot_units),
                 pct(wtd_occ, 1), "—", "—", "—", "—", usdM(tot_noi), pct(blend_trailing, 2),
                 pct(blend_inplace, 2), pct(blend_exit, 2), "—"])
    pg.table(0, 0, 1, 1,
             headers=["Asset", "Units", "Built", "Ask", "$/Unit", "Occ", "In-Place", "HD90", "L-to-L",
                      "New T/O", "T12 NOI", "Act Cap", "UW Cap", "Exit", "Lev IRR"],
             rows_data=rows, title="Asset-Level Data Tape", highlight=[len(rows) - 1], heat=False,
             note="In-Place = avg occupied lease rent; HD90 = HelloData executed T90 asking (mix-wtd, per-property join); "
                  "L-to-L = loss-to-lease (HD market vs in-place); Act Cap = trailing-12 NOI ÷ ask; UW Cap = JLL Year-0 NOI ÷ price.")
    brows = []
    for x in deals:
        opx, j, der, lo = x["op"], x["jll"], x["derived"], x["losses"]
        ract = opx["expense_t12"].get("Real Estate Taxes", 0)
        ruw = x["jll_pnl"]["tax"]["uw_taxes_yr0"]
        brows.append([shortname(x), usdM(lo["agpr_t12"]), usdM(opx["egr_t12"]), usdM(opx["opex_t12"]), usdM(opx["noi_t12"]),
                      usdM(j["noi_yr0"]), spct(der["jll_noi_vs_trailing"], 0), usd(ract), usd(ruw),
                      spct((ruw - ract) / ract if ract else 0, 0),
                      pct(lo["vacancy"]["t12"], 1), pct(lo["concessions"]["t12"], 1), pct(lo["ltl"]["t12"], 1)])
    brows.append(["PORTFOLIO", usdM(sum(x["losses"]["agpr_t12"] for x in deals)), usdM(sum(x["op"]["egr_t12"] for x in deals)),
                  usdM(sum(x["op"]["opex_t12"] for x in deals)), usdM(tot_noi), usdM(tot_noi_yr0),
                  spct(tot_noi_yr0 / tot_noi - 1, 0), usd(tot_redIQ_tax), usd(tot_uw_tax),
                  spct((tot_uw_tax - tot_redIQ_tax) / tot_redIQ_tax, 0), "", "", ""])
    pg.table(1, 0, 1, 1,
             headers=["Asset", "AGPR", "T12 EGR", "T12 Opex", "T12 NOI", "JLL NOI", "NOI Δ",
                      "Tax Act", "Tax UW", "Tax Δ", "Vac %AGPR", "Conc %AGPR", "LtL %GPR"],
             rows_data=brows, title="NOI Bridge, Tax Reassessment & Economic Losses (T12)", highlight=[len(brows) - 1], heat=False,
             note="JLL NOI = underwritten Year-0 (in-place). Tax UW reassessed to the purchase price (FL steps up; TX/Houston "
                  "can step down where over-assessed). Vacancy/Concessions as % of AGPR; loss-to-lease as % of gross potential.")
    probs = pg.save_into(pdf, png_path=os.path.join(OUT, "portfolio_tape.png"), final=True)
    return probs


def findings_page(pdf, deals, page_no):
    """Cross-asset scorecard — the trends & findings the data surfaces."""
    by = {x["key"]: x for x in deals}
    pw, gg, cc, te = by["pearl_washington"], by["golden_glades"], by["city_centre"], by["pearl_21eleven"]
    n_neg = sum(1 for x in deals if (x["lto"].get("new_tradeout_pct") or 0) < 0)
    ltl_widen = [shortname(x) for x in deals if x["losses"]["ltl"]["t3"] > x["losses"]["ltl"]["t12"] + 0.002]
    tot_noi = sum(x["op"]["noi_t12"] for x in deals)
    tot_tax_noi = sum(x["walk"]["tax"] for x in deals)
    pg = header("Morgan Recap  ·  Portfolio  ·  Key Findings & Trends", "Key Findings & Trends",
                f"What the trailing data and JLL underwriting reveal  ·  {ASOF}", page_no)
    pg.insight([
        ("Rents are rolling over at the Houston podiums while ", False), ("City Centre + Residences", True),
        (" holds; the recap's value is ", False), ("assumable sub-4.3% debt", True),
        (" and embedded loss-to-lease at City Centre — set against ", False),
        ("a +$0.6M tax reassessment drag and JLL expense optimism", True), (".", False),
    ], size=12)
    sc = [
        ("New-lease rents", f"neg at {n_neg} of 4: PW -15%, GG -12%, 21E -7%; City Centre +4%", "down"),
        ("Loss-to-lease quality", "City Centre upside real; PW HD upside belied by -15% new leases", "flat"),
        ("Loss-to-lease trend", f"widening at {(ltl_widen[0] if ltl_widen else 'none')} — downside on turnover", "down"),
        ("Concessions", "rising at Houston podiums; Golden Glades lease-up ~6% of EGR", "down"),
        ("Tax reassessment", "net -$0.6M NOI: GG +28% / CC +15% up, PW -3% down (TX)", "down"),
        ("JLL underwriting", "Yr-0 NOI +11% over trailing at PW; -2% at City Centre", "flat"),
        ("Cap rates / basis", "4.83% actual to 4.96% UW to 4.93% exit; GG tightest on top basis", "flat"),
        ("Capital stack", "two assumable loans 3.9-4.3% IO — the standout value", "up"),
        ("Resident credit", "median income $93-150K, rent/income 19-24%, delinq <0.5%", "up"),
    ]
    pg.grid(1, 1)
    pg.scorecard(0, 0, 1, 1, sc, headers=("DRIVER", "OBSERVATION", "TREND"))
    return pg.save_into(pdf, png_path=os.path.join(OUT, "findings.png"), final=True)


def main():
    path = os.path.join(OUT, "Morgan_Recap_Analysis.pdf")
    allp = {}
    with PdfPages(path) as pdf:
        allp["portfolio"] = portfolio_page(pdf, DEALS, 1)
        allp["findings"] = findings_page(pdf, DEALS, 2)
        n = 3
        for d in DEALS:
            allp[d["key"] + "_A"] = asset_financials(pdf, d, n); n += 1
            allp[d["key"] + "_B"] = asset_rents(pdf, d, n); n += 1
    print("Wrote", path)
    for k, v in allp.items():
        print(f"  {'OK' if not v else 'PROBLEMS'} [{k}]")
        for p in (v or []):
            print("     -", p)


if __name__ == "__main__":
    main()
