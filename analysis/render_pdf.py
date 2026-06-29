"""Render the Milestone-branded PDF: page 1 = portfolio data tape/summary,
pages 2-5 = per-deal asset one-pagers. Uses brandkit Page + panels."""
import os, json
import brand_setup  # noqa: F401  (configures paths + fonts)
from brandkit import theme as T
from brandkit.page import Page
from brandkit import panels as P
from matplotlib.backends.backend_pdf import PdfPages

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = json.load(open(os.path.join(ROOT, "analysis", "data.json")))
DEALS = DATA["deals"]
OUT = os.path.join(ROOT, "output")
os.makedirs(OUT, exist_ok=True)
SRC = ("Yardi rent rolls, lease trade-out & delinquency (May 2026); RedIQ-standardized "
       "operating statements (T12 May 2025–Apr 2026); HelloData unit details (Jun 2026); "
       "resident demographics (May 2026); JLL underwriting models (Jun 2026).")
ASOF = "Data as of May–Jun 2026"


def usd(v):
    return f"${v:,.0f}"

def usdk(v):
    return f"${v/1000:,.0f}K"

def usdM(v):
    return f"${v/1e6:,.1f}M"

def pct(v, d=1):
    return f"{v*100:.{d}f}%" if v is not None else "n/a"

def signed_pct(v, d=1):
    return f"{v*100:+.{d}f}%" if v is not None else "n/a"


# ════════════════════════════════════════════════════════════════════════════
# ASSET ONE-PAGER
# ════════════════════════════════════════════════════════════════════════════
def asset_page(pdf, d, page_no):
    j = d["jll"]; op = d["op"]; lto = d["lto"]; mix = d["mix"]; occ = d["occ"]
    rents = d["rents"]; demo = d["demo"]; der = d["derived"]
    city = j.get("city") or ""
    state = "FL" if d["key"] == "golden_glades" else (j.get("state") or "")
    sub = (f"{city}, {state}   ·   {occ['units']:,} units   ·   built {j.get('year_built')}"
           f"   ·   {j.get('product') or 'Multifamily'}   ·   {j.get('deal_type')}")
    pg = Page(kicker="Morgan Recap  ·  Asset One-Pager  ·  " + d["label"],
              title=d["label"], page_no=page_no, sources=SRC, slim=True)
    # manual subtitle (slim header has no subtitle slot)
    pg.fig.text(pg.LEFT, pg._y, sub, fontfamily=T.SANS, fontsize=10.5,
                fontstyle="italic", color=T.GRAY, va="top")
    pg._y -= 0.030

    # ── insight ──
    newt = lto.get("new_tradeout_pct")
    direction = "softening" if (newt is not None and newt < -0.01) else ("firming" if (newt is not None and newt > 0.01) else "holding")
    pg.insight([
        ("Trailing-12 NOI of ", False), (usdM(op["noi_t12"]), True),
        (" prices to a ", False), (pct(der["trailing_cap"], 1) + " actual cap", True),
        (" vs JLL's ", False), (pct(j["cap_yr0"], 1) + " in-place", True),
        (" / ", False), (pct(j["cap_yr1"], 1) + " Yr-1", True),
        (" — NOI underwritten ", False), (signed_pct(der["jll_noi_vs_trailing"], 0) + " vs trailing", True),
        ("; new-lease trade-outs ", False), (signed_pct(newt, 1), True),
        (" — rents ", False), (direction, True),
        (" against a ", False), (pct(j["rent_growth"][0], 0) + "–" + pct(j["rent_growth"][1], 0) + " growth plan", True),
        (".", False),
    ], size=11.5)

    # ── KPI band ──
    occ_good = occ["phys_occ"] >= 0.93
    pg.kpis([
        ("Units", f"{occ['units']:,}", None, None, None, f"{j.get('product') or ''} · {j.get('year_built')}"),
        ("Physical Occupancy", pct(occ["phys_occ"], 1), None, None, occ_good, f"vs JLL {pct(j['occupancy'],1)}"),
        ("In-Place Rent /mo", usd(rents["avg_inplace_rent"]), None, None, None, f"${rents['avg_inplace_psf']:.2f}/SF"),
        ("T12 NOI", usdM(op["noi_t12"]), None, None, None, f"T3 ann {usdM(op['noi_t3_ann'])}"),
        ("JLL Going-in Cap", pct(j["cap_yr0"], 2), None, None, None, f"exit {pct(j['exit_cap'],2)}"),
        ("Asking Price", usdM(j["price"]), None, None, None, f"{usd(j['price_unit'])}/unit"),
    ], height=0.115)

    band_top, band_bot = pg._y, pg._bottom
    H = band_top - band_bot
    # ── charts band (top ~34%): 3 charts side by side ──
    pg._bottom = band_top - 0.34 * H
    charts_floor = pg._bottom
    pg.grid(1, 3, hgap=0.045, vgap=0.0)
    ax = pg.panel(0, 0, title="Operating Trend — EGR & NOI ($/mo)")
    P.line(ax, op["months"], {"EGR": op["egr"], "NOI": op["noi"]}, yfmt="usdk")
    ax = pg.panel(0, 1, title="Rent Direction — Trade-Out vs Prior Lease")
    P.diverging(ax, ["New lease", "Renewal", "Blended", "Mkt YoY (HD)"],
                [lto.get("new_tradeout_pct"), lto.get("renewal_tradeout_pct"),
                 lto.get("tradeout_lease_pct"), mix.get("hd_yoy_ask")], vfmt="pct1")
    ax = pg.panel(0, 2, title="Monthly Concessions Given ($/mo)")
    P.line(ax, op["months"], {"Concessions": [-c for c in op["concessions"]]}, yfmt="usdk")

    # ── table band (bottom): underwriting vs in-place, with detail in the note ──
    pg._y = charts_floor - 0.058
    pg._bottom = band_bot
    pg.grid(1, 1)
    rg = j["rent_growth"]
    debt = f"{j['financing_type']} · {pct(j['rate'],2)} {'IO' if 'Interest' in str(j['amort']) else ''} · {pct(j['ltv'],0)} LTV"
    rows = [
        ("Price / Unit", usdM(j["price"]), f"{usd(j['price_unit'])} · ${j['price_sf']:.0f}/SF"),
        ("Going-in cap (in-place)", pct(j["cap_yr0"], 2), pct(der["trailing_cap"], 2) + " trailing actual"),
        ("Year-1 / Exit cap", f"{pct(j['cap_yr1'],2)} / {pct(j['exit_cap'],2)}", f"T3-ann {pct(der['forward_cap_t3'],2)}"),
        ("NOI — UW Yr0 vs trailing", usdM(j["noi_yr0"]), usdM(op["noi_t12"]) + f" ({signed_pct(der['jll_noi_vs_trailing'],0)})"),
        ("Mkt rent growth Y1–3", f"{pct(rg[0],0)}/{pct(rg[1],0)}/{pct(rg[2],0)}", "new-lease " + signed_pct(lto.get("new_tradeout_pct"), 1)),
        ("Loss-to-lease / Conc. assumed", f"{pct(j['ltl_assume'],1)} / {pct(j['conc_assume'],1)}", f"T12 conc {pct(der['conc_pct_egr'],1)}"),
        ("Debt", debt, "assumable" if "Assum" in str(j["financing_type"]) else "new"),
        ("Levered IRR / EM", f"{pct(j['irr_lev'],1)} / {j['em_lev']:.2f}x", f"LP {pct(j['irr_lp'],1)} / {j['em_lp']:.2f}x"),
    ]
    bedmap = {0: "Studio", 1: "1BR", 2: "2BR", 3: "3BR", 4: "4BR", None: "Other"}
    mixtxt = " · ".join(f"{b['units']} {bedmap.get(b['bed'],'?')} {usd(b['avg_contract'])}"
                        for b in mix["by_bed"] if b["units"])
    note = (f"Mix: {mixtxt}.  Resident median HH income {usd(demo['hh_income_median'])}, rent-to-income "
            f"{pct(der['rent_to_income'],0)}, median age {demo['age_median']:.0f}; 30+ delinquency "
            f"{pct(der['delinq_pct'],1)} of GPR.")
    if d.get("sub"):
        s = d["sub"]
        note += (f"  Pearl Residences within deal: {s['occ']['units']} units, {pct(s['occ']['phys_occ'],1)} occ, "
                 f"{usd(s['rents']['avg_inplace_rent'])}/mo, trade-out {signed_pct(s['lto'].get('tradeout_lease_pct'),1)}.")
    fl = asset_flag(d)
    if fl:
        note += "  Flag: " + fl + "."
    pg.table(0, 0, 1, 1, headers=["Metric", "JLL Underwriting", "In-Place / Trailing Actual"],
             rows_data=rows, title="JLL Underwriting  vs.  In-Place / Trailing", note=note, heat=False)

    probs = pg.save_into(pdf, png_path=os.path.join(OUT, f"asset_{d['key']}.png"), final=True)
    return probs


def asset_flag(d):
    j = d["jll"]; der = d["derived"]; lto = d["lto"]
    if d["key"] == "golden_glades":
        return ("model state reads 'Miami, TX' (should be FL); 2024 lease-up still burning concessions; tightest cap "
                "(4.7%)/highest basis ($360K) yet weakest momentum (HD −7.4% YoY, new leases −11.5%)")
    flags = []
    if der["jll_noi_vs_trailing"] > 0.08:
        flags.append(f"JLL Yr-0 NOI {signed_pct(der['jll_noi_vs_trailing'],0)} above trailing-12 — UW leans on normalization/upside")
    if lto.get("new_tradeout_pct") is not None and lto["new_tradeout_pct"] < -0.05 and j["ltl_assume"] > 0.03:
        flags.append(f"JLL assumes {pct(j['ltl_assume'],1)} loss-to-lease recapture while new leases trade {signed_pct(lto['new_tradeout_pct'],1)} below prior")
    return "; ".join(flags) if flags else ""


# ════════════════════════════════════════════════════════════════════════════
# PORTFOLIO SUMMARY / DATA TAPE
# ════════════════════════════════════════════════════════════════════════════
def portfolio_page(pdf, deals, page_no):
    tot_units = sum(x["occ"]["units"] for x in deals)
    tot_price = sum(x["jll"]["price"] for x in deals)
    tot_noi = sum(x["op"]["noi_t12"] for x in deals)
    tot_noi_yr0 = sum(x["jll"]["noi_yr0"] for x in deals)
    tot_exit = sum(x["jll"]["exit_price"] for x in deals)
    tot_noi_exit = sum(x["jll"]["noi_exit"] for x in deals)
    blend_goingin = tot_noi_yr0 / tot_price
    blend_trailing = tot_noi / tot_price
    blend_exit = tot_noi_exit / tot_exit
    wtd_occ = sum(x["occ"]["phys_occ"] * x["occ"]["units"] for x in deals) / tot_units

    pg = Page(kicker="Morgan Recap  ·  Portfolio Recapitalization (JLL)",
              title="Portfolio Data Tape", page_no=page_no, sources=SRC, slim=True)
    pg.fig.text(pg.LEFT, pg._y, f"4 deals / 5 properties   ·   {tot_units:,} units   ·   3 Houston + 1 Miami   ·   {ASOF}",
                fontfamily=T.SANS, fontsize=10.5, fontstyle="italic", color=T.GRAY, va="top")
    pg._y -= 0.030
    pg.insight([
        ("The five-property portfolio totals ", False), (f"{tot_units:,} units", True),
        (" at a ", False), (usdM(tot_price) + " ask", True),
        (" — a blended ", False), (pct(blend_goingin, 2) + " in-place cap", True),
        (" (", False), (pct(blend_trailing, 2) + " on trailing-12 actuals", True),
        (") to a ", False), (pct(blend_exit, 2) + " exit", True),
        (". Two deals carry assumable ", False), ("3.9–4.3% debt", True),
        ("; new-lease trade-outs are negative at three of four assets, with City Centre the lone outlier.", False),
    ], size=12)

    pg.kpis([
        ("Total Units", f"{tot_units:,}", None, None, None, "5 properties / 4 deals"),
        ("Total Ask", usdM(tot_price), None, None, None, f"{usd(tot_price/tot_units)}/unit blended"),
        ("Blended Going-in Cap", pct(blend_goingin, 2), None, None, None, f"{pct(blend_trailing,2)} on actuals"),
        ("Blended Exit Cap", pct(blend_exit, 2), None, None, None, "5-yr hold"),
        ("Wtd Occupancy", pct(wtd_occ, 1), None, None, wtd_occ >= 0.93, "physical, rent roll"),
        ("Total T12 NOI", usdM(tot_noi), None, None, None, f"UW {usdM(tot_noi_yr0)}"),
    ], height=0.115)

    band_top, band_bot = pg._y, pg._bottom
    H = band_top - band_bot
    labels = [shortname(x) for x in deals]
    # ── charts band (top 34%) ──
    pg._bottom = band_top - 0.34 * H
    charts_floor = pg._bottom
    pg.grid(1, 3, hgap=0.05, vgap=0.0)
    ax = pg.panel(0, 0, title="Cap Rate — Actual vs JLL UW vs Exit")
    P.grouped_bar(ax, labels,
                  {"Trailing (actual)": [x["derived"]["trailing_cap"] for x in deals],
                   "JLL in-place": [x["jll"]["cap_yr0"] for x in deals],
                   "Exit": [x["jll"]["exit_cap"] for x in deals]}, yfmt="pct1")
    ax = pg.panel(0, 1, title="New-Lease Trade-Out vs Market (HD YoY)")
    P.grouped_bar(ax, labels,
                  {"New-lease trade-out": [x["lto"].get("new_tradeout_pct") or 0 for x in deals],
                   "Mkt asking YoY (HD)": [x["mix"].get("hd_yoy_ask") or 0 for x in deals]}, yfmt="pct1")
    ax = pg.panel(0, 2, title="Price / Unit by Asset")
    P.grouped_bar(ax, labels, {"$/Unit": [x["jll"]["price_unit"] for x in deals]}, yfmt="usdk")

    # ── table band (bottom): the data tape ──
    pg._y = charts_floor - 0.058
    pg._bottom = band_bot
    pg.grid(1, 1)
    rows = []
    for x in deals:
        j = x["jll"]; op = x["op"]; lto = x["lto"]; occ = x["occ"]
        rows.append([
            shortname(x), f"{occ['units']:,}", str(j.get("year_built")), usdM(j["price"]),
            usdk(j["price_unit"]), pct(occ["phys_occ"], 1), usd(x["rents"]["avg_inplace_rent"]),
            signed_pct(lto.get("new_tradeout_pct"), 1), usdM(op["noi_t12"]),
            pct(x["derived"]["trailing_cap"], 2), pct(j["cap_yr0"], 2), pct(j["exit_cap"], 2),
            pct(j["irr_lev"], 1),
        ])
    rows.append([
        "PORTFOLIO", f"{tot_units:,}", "—", usdM(tot_price), usdk(tot_price / tot_units),
        pct(wtd_occ, 1), "—", "—", usdM(tot_noi), pct(blend_trailing, 2),
        pct(blend_goingin, 2), pct(blend_exit, 2), "—",
    ])
    tape_note = ("Pearl Washington & Pearl 21 Eleven assume below-market fixed-rate debt (4.26%/3.90%, IO); "
                 "City Centre+Residences and Golden Glades use new ~5.55% financing.  'Act Cap' = trailing-12 NOI ÷ ask; "
                 "'JLL Cap' = underwritten Year-0 (in-place) NOI ÷ price; 'New T/O' = rent-weighted new-lease trade-out "
                 "vs prior lease (Yardi LTO, T90).  Flags: Golden Glades model reads 'TX' (should be FL); Pearl Residences "
                 "delinquency file duplicates the City Centre tab.")
    pg.table(0, 0, 1, 1,
             headers=["Asset", "Units", "Built", "Ask", "$/Unit", "Occ", "In-Place",
                      "New T/O", "T12 NOI", "Act Cap", "JLL Cap", "Exit", "Lev IRR"],
             rows_data=rows, title="Asset-Level Data Tape", highlight=[len(rows) - 1], note=tape_note)

    probs = pg.save_into(pdf, png_path=os.path.join(OUT, "portfolio_tape.png"), final=True)
    return probs


def shortname(x):
    return {"city_centre": "City Centre+Res", "golden_glades": "Golden Glades",
            "pearl_washington": "Pearl Washington", "pearl_21eleven": "Pearl 21 Eleven"}[x["key"]]


def main():
    path = os.path.join(OUT, "Morgan_Recap_Analysis.pdf")
    allprobs = {}
    with PdfPages(path) as pdf:
        allprobs["portfolio"] = portfolio_page(pdf, DEALS, 1)
        for i, d in enumerate(DEALS, start=2):
            allprobs[d["key"]] = asset_page(pdf, d, i)
    print("Wrote", path)
    for k, v in allprobs.items():
        if v:
            print(f"  LAYOUT PROBLEMS [{k}]:")
            for p in v:
                print("    -", p)
        else:
            print(f"  OK [{k}] — no layout problems")


if __name__ == "__main__":
    main()
