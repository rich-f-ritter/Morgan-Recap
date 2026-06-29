"""
Morgan Recap — master data extractor.

For each deal (4 deals / 5 properties) pulls a structured dict of every metric the
one-pagers and portfolio tape need, then dumps analysis/data.json.

Sources, per the rr-t12-processor methodology:
  - Operating series (EGR/Opex/NOI, vacancy, concessions, LtL, expense lines):
        RedIQ standardized Operating Statement (Overview + monthly sheet)   [seller's RedIQ output]
  - Occupancy / unit mix / in-place contract rent:
        Yardi rent roll  -> rr-t12 lib (parse_rent_roll, build_unit_mix)
  - Executed market-rent trend (T90/T365 asking & effective, YoY):
        HelloData unit-details CSV (split by Property Name) -> rr-t12 lib
  - Rent direction (lease trade-out, new vs renewal):
        Yardi Lease Trade-Out (LTO) 90-day report
  - Credit / collections:
        Yardi delinquency (aged receivables)
  - Resident profile:
        Resident demographics report
  - Underwriting (cap rate, returns, debt, assumptions):
        JLL model 'Executive Summary'
"""
from __future__ import annotations
import sys, os, csv, json, re, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "_uploads", "rrt12_skill", "scripts"))
import openpyxl
import intake_lib as il
import account_map as am

ROOT = os.path.join(os.path.dirname(__file__), "..")
INFO = os.path.join(ROOT, "_uploads", "morgan_info")
MODELS = os.path.join(INFO, "JLL Models - Morgan Recap - Models")
SCRATCH = os.path.join(ROOT, "analysis", "_scratch")
os.makedirs(SCRATCH, exist_ok=True)
HD_CSV = os.path.join(INFO, "hello-data-unit-details-2026-06-29.csv")


def num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if v is None:
        return 0.0
    s = str(v).replace(",", "").replace("$", "").replace("%", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        f = float(s)
        return -f if neg else f
    except ValueError:
        return 0.0


# ── charge lookup: 'MNEMONIC - Human Name' -> Human Name (so categorize_charge works) ──
def build_charge_lookup(path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = max(wb.worksheets, key=lambda w: w.max_row)
    look = {}
    for row in ws.iter_rows():
        for cell in row:
            v = cell.value
            if isinstance(v, str) and " - " in v and not v.startswith("Charge Total"):
                look[v] = (v.split(" - ", 1)[1].strip(), "")
    wb.close()
    return look


def split_hellodata(prop_names):
    """Write a temp HelloData CSV holding only the given Property Name(s); return its path."""
    with open(HD_CSV, newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        hdr = rd.fieldnames
        rows = [r for r in rd if r["Property Name"] in prop_names]
    out = os.path.join(SCRATCH, "hd_" + re.sub(r"\W+", "", "".join(prop_names))[:30] + ".csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=hdr)
        w.writeheader()
        w.writerows(rows)
    return out, len(rows)


# ════════════════════════════════════════════════════════════════════════════
# RENT ROLL  (occupancy, in-place contract rent, unit mix, lease classification)
# ════════════════════════════════════════════════════════════════════════════
def parse_rr(paths):
    """Parse one or more rent rolls (combined) -> merged RentRoll-like dict of metrics."""
    units = []
    as_of = None
    for p in paths:
        look = build_charge_lookup(p)
        rr = il.parse_rent_roll(p, charge_lookup=look)
        units.extend(rr.units)
        as_of = rr.as_of or as_of
    return units, as_of


def occ_breakdown(units):
    """Occupancy from the raw status text (matches the operator/JLL convention):
    a resident physically in place — including units on NOTICE — counts as
    occupied; only 'Vacant *' units are vacant; model/excluded/down are non-revenue."""
    from collections import Counter
    statuses = Counter(str(u.status) for u in units)
    n = len(units)
    def is_nonrev(s):
        return bool(re.search(r"exclud|model|down|admin", s, re.I))
    def is_vacant(s):
        return s.lower().startswith("vacant") or (s.strip().lower() == "vacant")
    phys_occ_n = sum(1 for u in units if not is_nonrev(str(u.status)) and not is_vacant(str(u.status)))
    nonrev = sum(1 for u in units if is_nonrev(str(u.status)))
    vacant = sum(1 for u in units if is_vacant(str(u.status)) and not is_nonrev(str(u.status)))
    vacant_rented = sum(1 for u in units if is_vacant(str(u.status)) and not is_nonrev(str(u.status))
                        and re.search(r"rented|leas", str(u.status), re.I))
    notice = sum(1 for u in units if re.search(r"notice", str(u.status), re.I))
    notice_unrented = sum(1 for u in units if re.search(r"notice", str(u.status), re.I)
                          and re.search(r"unrent|unleas", str(u.status), re.I))
    denom = n  # JLL/operator convention: total units incl model in denominator
    return {
        "units": n, "occupied": phys_occ_n, "vacant": vacant, "nonrev": nonrev,
        "notice": notice, "notice_unrented": notice_unrented, "vacant_rented": vacant_rented,
        "phys_occ": phys_occ_n / denom,
        "leased_occ": (phys_occ_n + vacant_rented) / denom,
        "avail_occ": (phys_occ_n - notice_unrented) / denom,  # economic/available (notice-unrented treated as coming-vacant)
        "status_counts": dict(statuses),
    }


def inplace_rents(units):
    occ_u = [u for u in units if u.contract_rent > 0]          # paying (in-place) units
    contract = [u.contract_rent for u in occ_u]
    sf = [u.sqft for u in occ_u if u.sqft]
    tot_contract = sum(u.contract_rent for u in units)
    tot_other = sum(u.other_income for u in units if u.other_income > 0)
    # rent-roll AGPR (full-occupancy in-place): paying units at lease rent, vacant at market
    rr_agpr = sum(u.contract_rent if u.contract_rent > 0 else u.market_rent for u in units)
    return {
        "avg_inplace_rent": (sum(contract) / len(contract)) if contract else 0.0,
        "avg_inplace_psf": (sum(contract) / sum(sf)) if sf else 0.0,
        "total_contract_mo": tot_contract,
        "rr_agpr_mo": rr_agpr,
        "total_other_mo": tot_other,
        "n_occ": len(occ_u),
    }


def parse_demographics_full(paths):
    """Full resident-demographics analysis (resident-weighted across files for a combined
    deal): median/mean household & personal income, the income distribution, % of residents
    earning $100K+, median household size & age, and a Leads (prospect-pool) income compare."""
    SECTIONS = ("Household Income", "Personal Income", "Household Size", "Age", "Legal Gender")
    agg = {}   # (section, bucket) -> {"res":x, "lead":y}
    stat = {}  # (section, stat) -> [(val, weight)]
    file_resid = []
    for path in paths:
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb[wb.sheetnames[0]]
        section = None
        this_resid = 0
        for r in range(6, ws.max_row + 1):
            a = il._s(ws.cell(r, 1).value)
            b = ws.cell(r, 2).value
            c = ws.cell(r, 3).value
            if a in SECTIONS and il._s(b) in ("", "Leads"):
                section = a
                continue
            if not section:
                continue
            if a in ("Mean", "Median", "Total"):
                stat.setdefault((section, a), []).append((num(c), None))
                if section == "Household Income" and a == "Total":
                    this_resid = num(c)
            elif a and a != "Unknown":
                d = agg.setdefault((section, a), {"res": 0.0, "lead": 0.0})
                d["res"] += num(c); d["lead"] += num(b)
        file_resid.append(this_resid or 1)
        wb.close()
    wsum = sum(file_resid) or 1

    def stat_w(section, s):
        vals = stat.get((section, s), [])
        if not vals:
            return 0.0
        if len(vals) == len(file_resid) and s in ("Mean", "Median"):
            return sum(v * w for (v, _), w in zip(vals, file_resid)) / wsum
        return sum(v for v, _ in vals)

    # income distribution (residents) for Household Income
    inc_buckets = [(k[1], v["res"]) for k, v in agg.items() if k[0] == "Household Income"]
    tot_res = sum(v for _, v in inc_buckets) or 1
    over100 = sum(v for kk, v in inc_buckets if "100" in kk) / tot_res
    return {
        "hh_income_median": stat_w("Household Income", "Median"),
        "hh_income_mean": stat_w("Household Income", "Mean"),
        "personal_income_median": stat_w("Personal Income", "Median"),
        "personal_income_mean": stat_w("Personal Income", "Mean"),
        "lead_income_mean": stat_w("Household Income", "Mean"),   # placeholder; leads handled below
        "hh_size_median": stat_w("Household Size", "Median"),
        "age_median": stat_w("Age", "Median"),
        "age_mean": stat_w("Age", "Mean"),
        "resident_total": stat_w("Household Income", "Total"),
        "pct_over_100k": over100,
        "income_dist": _income_bands(agg),
        "lead_count": sum(v["lead"] for k, v in agg.items() if k[0] == "Household Income"),
    }


def _income_bands(agg):
    """Collapse the fine income buckets into 5 readable bands (residents)."""
    bands = {"<$50K": 0.0, "$50–75K": 0.0, "$75–100K": 0.0, "$100K+": 0.0}
    import re as _re
    for (sec, bucket), v in agg.items():
        if sec != "Household Income":
            continue
        nums = [int(x.replace(",", "")) for x in _re.findall(r"\d[\d,]*", bucket)]
        lo = nums[0] if nums else 0
        if "100" in bucket:
            bands["$100K+"] += v["res"]
        elif lo < 50000:
            bands["<$50K"] += v["res"]
        elif lo < 75000:
            bands["$50–75K"] += v["res"]
        else:
            bands["$75–100K"] += v["res"]
    return bands


def unit_mix_summary(segments, lto=None):
    """Per-bedroom unit mix. `segments` is a list of (units, hellodata) pairs — ONE per
    physical property — so HelloData is joined to its OWN rent roll by unit number
    (combining properties first would collide on shared unit numbers and corrupt the
    HD market reads / bed inference). Per-segment mixes are concatenated, then aggregated
    by bedroom; also returns per-plan detail and mix-weighted portfolio HelloData reads."""
    mix = []
    for su, shd in segments:
        mix += il.build_unit_mix(il.RentRoll(units=su), shd)
    bed_to = lto_by_bed(lto) if lto else {}
    by_bed = {}
    for m in mix:
        bd = m.bed if isinstance(m.bed, int) else None
        g = by_bed.setdefault(bd, {"units": 0, "occ": 0, "vac": 0, "sf": 0.0, "sf_n": 0,
                                   "contract_sum": 0.0, "contract_n": 0,
                                   "t90a": 0.0, "t90e": 0.0, "t90w": 0, "t365a": 0.0, "t365e": 0.0, "t365w": 0,
                                   "new": 0, "renewal": 0})
        g["units"] += m.units; g["occ"] += m.occ; g["vac"] += m.vac
        g["new"] += m.new_count; g["renewal"] += m.renewal_count
        if m.avg_sqft:
            g["sf"] += m.avg_sqft * m.units; g["sf_n"] += m.units
        if m.avg_contract:
            g["contract_sum"] += m.avg_contract * m.occ; g["contract_n"] += m.occ
        if m.t90_ask:
            g["t90a"] += m.t90_ask * m.units; g["t90e"] += m.t90_eff * m.units; g["t90w"] += m.units
        if m.t365_ask:
            g["t365a"] += m.t365_ask * m.units; g["t365e"] += m.t365_eff * m.units; g["t365w"] += m.units
    rows = []
    for bd in sorted(by_bed, key=lambda x: (99 if x is None else x)):
        g = by_bed[bd]
        lb = bed_to.get(bd, {})
        rows.append({
            "bed": bd, "units": g["units"], "occ": g["occ"], "vac": g["vac"],
            "avg_sf": g["sf"] / g["sf_n"] if g["sf_n"] else 0,
            "in_place": g["contract_sum"] / g["contract_n"] if g["contract_n"] else 0,
            "hd90_ask": g["t90a"] / g["t90w"] if g["t90w"] else 0,
            "hd90_eff": g["t90e"] / g["t90w"] if g["t90w"] else 0,
            "hd365_ask": g["t365a"] / g["t365w"] if g["t365w"] else 0,
            "hd365_eff": g["t365e"] / g["t365w"] if g["t365w"] else 0,
            "lto_new_n": lb.get("new_n", 0), "lto_ren_n": lb.get("ren_n", 0),
            "lto_new_to": lb.get("new_tradeout"), "lto_ren_to": lb.get("ren_tradeout"),
            "lto_to": lb.get("tradeout"),
        })
    # per-plan detail (for the Excel)
    plans = []
    for m in mix:
        plans.append({
            "plan": m.plan, "bed": m.bed, "bath": m.bath, "units": m.units, "occ": m.occ, "vac": m.vac,
            "avg_sf": round(m.avg_sqft), "in_place": round(m.avg_contract),
            "hd90_ask": round(m.t90_ask), "hd90_eff": round(m.t90_eff),
            "hd365_ask": round(m.t365_ask), "hd365_eff": round(m.t365_eff),
            "new_n": m.new_count, "renewal_n": m.renewal_count,
            "last5_new_avg": round(m.avg_new_last5), "hd_yoy_ask": m.yoy_ask,
        })
    # mix-weighted portfolio HelloData reads
    def wavg(attr):
        num_ = den = 0.0
        for m in mix:
            v = getattr(m, attr)
            if v:
                num_ += v * m.units; den += m.units
        return num_ / den if den else 0
    yoy_num = yoy_w = 0.0
    for m in mix:
        if m.yoy_ask is not None:
            yoy_num += m.yoy_ask * m.units; yoy_w += m.units
    return {
        "by_bed": rows, "by_plan": plans,
        "hd_t90_ask": wavg("t90_ask"), "hd_t90_eff": wavg("t90_eff"),
        "hd_t365_ask": wavg("t365_ask"), "hd_t365_eff": wavg("t365_eff"),
        "hd_yoy_ask": yoy_num / yoy_w if yoy_w else None, "n_plans": len(mix),
    }


# ════════════════════════════════════════════════════════════════════════════
# REDIQ OPERATING STATEMENT  (EGR/Opex/NOI monthly + expense lines)
# ════════════════════════════════════════════════════════════════════════════
def parse_rediq(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ov = wb["Overview"]
    # columns: 1=code 2=label 3-5=annual(empty) 6-17=12 monthly (May25..Apr26)
    mon_cols = list(range(6, 18))
    # month labels from monthly detail sheet header? Overview row4 says Annual x3 + Monthly x12
    months = ["May'25", "Jun'25", "Jul'25", "Aug'25", "Sep'25", "Oct'25",
              "Nov'25", "Dec'25", "Jan'26", "Feb'26", "Mar'26", "Apr'26"]

    def row_series(rlabel_or_code, by="label"):
        for r in range(6, ov.max_row + 1):
            code = il._s(ov.cell(r, 1).value)
            lab = il._s(ov.cell(r, 2).value)
            hit = (lab.lower() == rlabel_or_code.lower()) if by == "label" else (code == rlabel_or_code)
            if hit:
                return [num(ov.cell(r, c).value) for c in mon_cols]
        return [0.0] * 12

    # subtotals by label (the second 'Effective Gross Revenue' / 'Operating Expenses' are the totals)
    def subtotal_series(label):
        hits = []
        for r in range(6, ov.max_row + 1):
            if il._s(ov.cell(r, 1).value) == "" and il._s(ov.cell(r, 2).value).lower() == label.lower():
                hits.append([num(ov.cell(r, c).value) for c in mon_cols])
        return hits[-1] if hits else [0.0] * 12

    egr = subtotal_series("Effective Gross Revenue")
    opex = subtotal_series("Operating Expenses")
    noi = subtotal_series("Net Operating Income")
    out = {
        "months": months,
        "egr": egr, "opex": opex, "noi": noi,
        "rentinc": row_series("Rentinc", "code"),
        "vacancy": row_series("vac", "code"),
        "concessions": row_series("conc", "code"),
        "ltl": row_series("ltl", "code"),
        "bad_debt": row_series("cl", "code"),
        "nonrev": row_series("nr", "code"),
        "other_income": row_series("OI", "code"),
    }
    # expense line items (T12 totals)
    exp_codes = {"Pay": "Payroll", "adv": "Marketing", "GA": "G&A", "turn": "Turnover",
                 "cont": "Contract Svc", "mgt": "Mgmt Fee", "ins": "Insurance",
                 "ret": "Real Estate Taxes", "UWS": "Util W/S", "UC": "Util Common",
                 "PB": "Payroll Burden"}
    exp = {}
    for code, name in exp_codes.items():
        s = row_series(code, "code")
        exp[name] = sum(s)
    # R&M interior/exterior may use a combined code
    rm = row_series("inter/exte", "code")
    if sum(rm):
        exp["R&M Int/Ext"] = sum(rm)
    out["expense_t12"] = exp

    def t(series, n):  # trailing-n annualized
        return sum(series[-n:]) * (12 / n)
    out["egr_t12"] = sum(egr)
    out["opex_t12"] = sum(opex)
    out["noi_t12"] = sum(noi)
    out["noi_t3_ann"] = t(noi, 3)
    out["noi_t6_ann"] = t(noi, 6)
    out["egr_t3_ann"] = t(egr, 3)
    out["egr_t6_ann"] = t(egr, 6)
    out["rentinc_t12"] = sum(out["rentinc"])
    out["concessions_t12"] = sum(out["concessions"])
    # AGPR (Adjusted Gross Potential Rent) = Gross Potential + Loss-to-Lease, per month
    out["agpr"] = [out["rentinc"][i] + out["ltl"][i] for i in range(12)]
    wb.close()
    return out


def _win(series, n):
    """Trailing-n-month sum, annualized."""
    return sum(series[-n:]) * (12 / n)


def loss_ratios(op, jll_lines):
    """Economic losses as a % of AGPR, on a trailing T12 / T6 / T3 basis (and JLL Year-0).
    AGPR = Gross Potential Rent + Loss-to-Lease (the 'adjusted GPR' off the financials).
    Vacancy, bad debt and concessions are expressed as a share of AGPR; loss-to-lease as a
    share of gross potential. Rising loss ratios = softening; falling = tightening."""
    agpr = op["agpr"]
    def ratio(series_code, denom_code="agpr", win=12):
        s = op[series_code]
        d = op[denom_code]
        num_ = abs(_win(s, win))
        den = _win(d, win)
        return num_ / den if den else 0.0
    out = {"agpr_t12": _win(agpr, 12), "agpr_t6": _win(agpr, 6), "agpr_t3": _win(agpr, 3)}
    for code, label in (("vacancy", "vacancy"), ("bad_debt", "bad_debt"), ("concessions", "concessions")):
        out[label] = {"t12": ratio(code, "agpr", 12), "t6": ratio(code, "agpr", 6), "t3": ratio(code, "agpr", 3)}
    # loss-to-lease as % of gross potential (how far in-place sits below market scheduled)
    out["ltl"] = {"t12": abs(_win(op["ltl"], 12)) / _win(op["rentinc"], 12),
                  "t6": abs(_win(op["ltl"], 6)) / _win(op["rentinc"], 6),
                  "t3": abs(_win(op["ltl"], 3)) / _win(op["rentinc"], 3)}
    # economic occupancy = 1 - vacancy/AGPR
    out["econ_occ"] = {"t12": 1 - out["vacancy"]["t12"], "t6": 1 - out["vacancy"]["t6"], "t3": 1 - out["vacancy"]["t3"]}
    # JLL Year-0 loss ratios (off the model's in-place line items)
    L = jll_lines
    agpr_j = L["gsr"]["yr0"] + L["ltl"]["yr0"]
    out["jll"] = {
        "agpr": agpr_j,
        "vacancy": abs(L["vacancy"]["yr0"] + L["model"]["yr0"]) / agpr_j if agpr_j else 0,
        "bad_debt": abs(L["collection"]["yr0"]) / agpr_j if agpr_j else 0,
        "concessions": abs(L["conc"]["yr0"]) / agpr_j if agpr_j else 0,
        "ltl": abs(L["ltl"]["yr0"]) / L["gsr"]["yr0"] if L["gsr"]["yr0"] else 0,
    }
    return out


def operating_trends(op):
    """T12 / T6 / T3 annualized operating series — the momentum read (revenue/NOI run-rate)."""
    return {
        "egr": {"t12": _win(op["egr"], 12), "t6": _win(op["egr"], 6), "t3": _win(op["egr"], 3)},
        "noi": {"t12": _win(op["noi"], 12), "t6": _win(op["noi"], 6), "t3": _win(op["noi"], 3)},
        "agpr": {"t12": _win(op["agpr"], 12), "t6": _win(op["agpr"], 6), "t3": _win(op["agpr"], 3)},
    }


# ════════════════════════════════════════════════════════════════════════════
# LEASE TRADE-OUT (LTO)
# ════════════════════════════════════════════════════════════════════════════
def _bed_of(unit_type):
    """Bed count from a floor-plan / unit-type code first letter (S/E=studio, A=1, B=2 ...)."""
    s = il._s(unit_type).upper()
    if not s:
        return None
    return {"S": 0, "E": 0, "A": 1, "B": 2, "C": 3, "D": 4, "F": 5}.get(s[0])


def parse_lto(path):
    """Lease trade-out. Returns the blended summary plus the raw per-lease detail
    rows (beds, new/renewal, prior/current lease & effective rents) so trade-outs
    can be rolled up by bedroom and split new vs renewal downstream."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    period = il._s(ws.cell(4, 1).value)
    res = {"period": period, "rows": []}
    # --- Summary 'Total/Average:' row (cols: 3 Leases,5 PriorRent,8 PriorEff,10 CurRent,12 CurEff) ---
    # also capture unit-type -> beds from the summary (col2 = Beds)
    ut_beds = {}
    for r in range(7, min(ws.max_row, 60) + 1):
        a = il._s(ws.cell(r, 1).value)
        if a.startswith("Total/Average"):
            res.update(leases=num(ws.cell(r, 3).value), prior_rent=num(ws.cell(r, 5).value),
                       prior_eff=num(ws.cell(r, 8).value), cur_rent=num(ws.cell(r, 10).value),
                       cur_eff=num(ws.cell(r, 12).value))
            break
        b = ws.cell(r, 2).value
        if a and isinstance(b, (int, float)):
            ut_beds[a] = int(b)
    res["ut_beds"] = ut_beds
    if res.get("prior_rent"):
        res["tradeout_lease_pct"] = res["cur_rent"] / res["prior_rent"] - 1
        res["tradeout_eff_pct"] = (res["cur_eff"] / res["prior_eff"] - 1) if res.get("prior_eff") else None

    # --- Detail rows ---
    hdr = None
    for r in range(1, ws.max_row + 1):
        labs = {il._s(ws.cell(r, c).value).lower(): c for c in range(1, ws.max_column + 1)}
        if "current lease type" in labs:
            hdr, cols = r, labs
            break
    if hdr:
        c_ut = cols.get("unit type")
        c_type = cols.get("current lease type")
        c_pr = cols.get("prior lease rent")
        c_cu = cols.get("current lease rent") or cols.get("current  lease rent")
        c_pe = cols.get("prior effective rent")
        c_ce = cols.get("current effective rent")
        for r in range(hdr + 1, ws.max_row + 1):
            t = il._s(ws.cell(r, c_type).value) if c_type else ""
            if not t:
                continue
            pr = num(ws.cell(r, c_pr).value) if c_pr else 0
            cu = num(ws.cell(r, c_cu).value) if c_cu else 0
            if pr <= 0 or cu <= 0 or abs(cu / pr - 1) > 0.6:
                continue
            ut = il._s(ws.cell(r, c_ut).value) if c_ut else ""
            beds = ut_beds.get(ut, _bed_of(ut))
            tl = t.lower()
            res["rows"].append({
                "beds": beds, "kind": "new" if ("appl" in tl or tl.startswith("new")) else "renewal",
                "prior": pr, "cur": cu,
                "prior_eff": num(ws.cell(r, c_pe).value) if c_pe else 0,
                "cur_eff": num(ws.cell(r, c_ce).value) if c_ce else 0,
            })
    wb.close()
    return finalize_lto(res)


def finalize_lto(res):
    for grp in ("new", "renewal"):
        rws = [x for x in res["rows"] if x["kind"] == grp]
        pr, cu = sum(x["prior"] for x in rws), sum(x["cur"] for x in rws)
        res[f"{grp}_n"] = len(rws)
        res[f"{grp}_tradeout_pct"] = (cu / pr - 1) if pr else None
    return res


def lto_by_bed(res):
    """Roll the LTO detail rows up by bedroom: blended + new/renewal trade-outs & counts."""
    out = {}
    for x in res["rows"]:
        b = x["beds"]
        g = out.setdefault(b, {"prior": 0.0, "cur": 0.0, "n": 0,
                               "new_prior": 0.0, "new_cur": 0.0, "new_n": 0,
                               "ren_prior": 0.0, "ren_cur": 0.0, "ren_n": 0})
        g["prior"] += x["prior"]; g["cur"] += x["cur"]; g["n"] += 1
        p = "new" if x["kind"] == "new" else "ren"
        g[f"{p}_prior"] += x["prior"]; g[f"{p}_cur"] += x["cur"]; g[f"{p}_n"] += 1
    for b, g in out.items():
        g["tradeout"] = (g["cur"] / g["prior"] - 1) if g["prior"] else None
        g["new_tradeout"] = (g["new_cur"] / g["new_prior"] - 1) if g["new_prior"] else None
        g["ren_tradeout"] = (g["ren_cur"] / g["ren_prior"] - 1) if g["ren_prior"] else None
    return out


# ════════════════════════════════════════════════════════════════════════════
# DELINQUENCY (aged receivables)
# ════════════════════════════════════════════════════════════════════════════
def parse_delinquency(path):
    """Aged receivables. Columns: ...|0-30|31-60|61-90|90+|Pre-Payments|Balance.
    The final all-blank-label row is the grand total. Past-due (30+) = 31-60 +
    61-90 + 90+; net balance is after prepayments."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    hdr = None
    for r in range(1, 12):
        labs = {il._s(ws.cell(r, c).value).lower(): c for c in range(1, ws.max_column + 1)}
        if any("0-30" in l for l in labs):
            hdr = r
            cols = labs
            break
    res = {"total_delinquent": 0.0, "past_due_30": 0.0, "net_balance": 0.0}
    if hdr:
        c0 = next((c for l, c in cols.items() if "0-30" in l), None)
        c1 = next((c for l, c in cols.items() if "31-60" in l), None)
        c2 = next((c for l, c in cols.items() if "61-90" in l), None)
        c3 = next((c for l, c in cols.items() if "90+" in l or "over" in l), None)
        cbal = next((c for l, c in cols.items() if l.strip() == "balance"), None)
        # grand-total row = last row carrying a numeric balance with no resident name
        for r in range(ws.max_row, hdr, -1):
            name = il._s(ws.cell(r, 2).value)
            unit = il._s(ws.cell(r, 1).value)
            balv = ws.cell(r, cbal).value if cbal else None
            if not name and not unit and isinstance(balv, (int, float)):
                b0 = num(ws.cell(r, c0).value) if c0 else 0
                b1 = num(ws.cell(r, c1).value) if c1 else 0
                b2 = num(ws.cell(r, c2).value) if c2 else 0
                b3 = num(ws.cell(r, c3).value) if c3 else 0
                res["total_delinquent"] = b0 + b1 + b2 + b3
                res["past_due_30"] = b1 + b2 + b3
                res["net_balance"] = num(balv)
                break
    wb.close()
    return res


# ════════════════════════════════════════════════════════════════════════════
# DEMOGRAPHICS
# ════════════════════════════════════════════════════════════════════════════
def parse_demographics(paths):
    """Combine one or more demographic reports (resident-weighted)."""
    agg = {}
    for path in paths:
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb[wb.sheetnames[0]]
        section = None
        for r in range(6, ws.max_row + 1):
            a = il._s(ws.cell(r, 1).value)
            b = ws.cell(r, 2).value
            c = ws.cell(r, 3).value
            if a and (b is None or il._s(b) in ("", "Leads")) and not re.match(r"^[\$\d]", a):
                # section header rows repeat the section name; capture the section
                if il._s(b) == "Leads":
                    section = a
                    continue
                if a not in ("Total", "Mean", "Median", "Unknown"):
                    section = a
            if a in ("Mean", "Median", "Total") and section:
                key = f"{section}|{a}"
                resid = num(c)  # residents column
                agg.setdefault(key, []).append(resid)
        wb.close()
    # for combined, weight Mean by resident Total; take simple where single
    out = {}
    # residents total per file for weighting
    totals = agg.get("Household Income|Total") or agg.get("Personal Income|Total") or [1]
    wsum = sum(totals) or 1
    for key, vals in agg.items():
        metric = key.split("|")[1]
        if metric == "Mean" and len(vals) == len(totals):
            out[key] = sum(v * w for v, w in zip(vals, totals)) / wsum
        elif metric == "Total":
            out[key] = sum(vals)
        else:
            # median: resident-weighted average of the file medians (approx for combined)
            if len(vals) == len(totals) and len(vals) > 1:
                out[key] = sum(v * w for v, w in zip(vals, totals)) / wsum
            else:
                out[key] = vals[0] if vals else 0
    return {
        "hh_income_mean": out.get("Household Income|Mean", 0),
        "hh_income_median": out.get("Household Income|Median", 0),
        "personal_income_mean": out.get("Personal Income|Mean", 0),
        "personal_income_median": out.get("Personal Income|Median", 0),
        "hh_size_median": out.get("Household Size|Median", 0),
        "age_median": out.get("Age|Median", 0),
        "age_mean": out.get("Age|Mean", 0),
        "resident_total": out.get("Household Income|Total", 0),
    }


# ════════════════════════════════════════════════════════════════════════════
# JLL MODEL  (Executive Summary)
# ════════════════════════════════════════════════════════════════════════════
def g(ws, addr):
    v = ws[addr].value
    return v if not isinstance(v, str) or "DIV/0" not in v else None


def parse_jll(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Executive Summary"]
    price = num(g(ws, "D12"))
    units = num(g(ws, "F6"))
    out = {
        "name": g(ws, "C6"), "address": g(ws, "C7"), "city": g(ws, "C8"), "state": g(ws, "C9"),
        "units": int(units), "sqft": num(g(ws, "F7")), "avg_unit_sf": num(g(ws, "F8")),
        "year_built": g(ws, "P6"), "product": g(ws, "P7"), "deal_type": g(ws, "P9"),
        "occupancy": num(g(ws, "S8")),
        "acq_date": str(g(ws, "S6")), "sale_date": str(g(ws, "S7")), "hold_months": num(g(ws, "U18")),
        "price": price, "price_unit": num(g(ws, "E12")), "price_sf": num(g(ws, "F12")),
        "capex": num(g(ws, "D13")), "total_cost": num(g(ws, "D26")), "cost_unit": num(g(ws, "E26")),
        "financing_type": g(ws, "P19"),
        "loan_amount": num(g(ws, "P21")), "ltv": num(g(ws, "P22")), "rate": num(g(ws, "P26")),
        "amort": g(ws, "P23"), "loan_term": num(g(ws, "P24")), "io_period": num(g(ws, "P25")),
        "cap_yr0": num(g(ws, "P39")), "cap_yr1": num(g(ws, "Q39")),
        "cap_yr3": num(g(ws, "R39")), "cap_yr5": num(g(ws, "S39")),
        "cap_yr0_cost": num(g(ws, "P40")), "cap_yr1_cost": num(g(ws, "Q40")),
        "exit_cap": num(g(ws, "P29")), "exit_price": num(g(ws, "Q29")), "exit_unit": num(g(ws, "R29")),
        "irr_unlev": num(g(ws, "P43")), "irr_lev": num(g(ws, "Q43")), "irr_lp": num(g(ws, "R43")),
        "em_unlev": num(g(ws, "P44")), "em_lev": num(g(ws, "Q44")), "em_lp": num(g(ws, "R44")),
        "rent_growth": [num(g(ws, a + "43")) for a in "CDEFG"],
        "ltl_assume": num(g(ws, "C47")), "conc_assume": num(g(ws, "C48")),
        "vac_assume": num(g(ws, "C49")), "econ_vac_assume": num(g(ws, "C55")),
        "exp_growth": num(g(ws, "D56")),
        "valueadd_prem": num(g(ws, "C71")) or num(g(ws, "C41")),
        "pct_renov": [num(g(ws, a + "73")) for a in "CDE"],
        "boy_revpou_y1": num(g(ws, "C60")),
    }
    out["noi_yr0"] = out["cap_yr0"] * price
    out["noi_yr1"] = out["cap_yr1"] * price
    out["noi_exit"] = out["exit_cap"] * out["exit_price"]
    wb.close()
    return out


def parse_jll_pnl(path):
    """JLL line-item P&L from 'Historical_YR 0': col D = annualized actual (T12),
    col F = Year-0 (in-place underwriting), col J = Year-1. Matched by row label so
    it is robust to row shifts. Also pulls the tax-reassessment analysis."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Historical_YR 0"]
    label_row = {}
    for r in range(1, ws.max_row + 1):
        lab = il._s(ws.cell(r, 1).value)
        if lab and lab not in label_row:
            label_row[lab] = r

    def get(label, col):
        r = label_row.get(label)
        return num(ws.cell(r, col).value) if r else 0.0

    def trip(label):
        r = label_row.get(label)
        if not r:
            return {"actual": 0.0, "yr0": 0.0, "yr1": 0.0}
        return {"actual": num(ws.cell(r, 4).value), "yr0": num(ws.cell(r, 6).value),
                "yr1": num(ws.cell(r, 10).value)}

    lines = {k: trip(lbl) for k, lbl in {
        "gsr": "Gross Scheduled Rent", "ltl": "Loss To Lease", "conc": "Concessions",
        "vacancy": "Vacancy Loss", "model": "Model/Office/Employee Units",
        "collection": "Collection Loss", "nri": "Net Rental Income",
        "other_income": "Other Income", "util_reimb": "Utility Reimbursement",
        "egr": "Total Income", "salaries": "Salaries", "advertising": "Advertising",
        "contract": "Contract Services", "turnover": "Turnover Costs",
        "maintenance": "Maintenance", "ga": "General & Administrative",
        "utilities": "Utilities", "mgmt": "Management Fee", "insurance": "Insurance",
        "taxes": "Property Taxes", "franchise": "Franchise Tax",
        "opex": "Total Operating Expenses", "reserves": "Normalized Capital Expenditures",
        "noi": "NCLF Before Partnership Costs",
    }.items()}
    # tax reassessment analysis
    ca_row = label_row.get("Actual Current Assessment")
    tax = {
        "current_assessment": num(ws.cell(ca_row, 4).value) if ca_row else 0.0,
        "purchase_price_basis": num(ws.cell(ca_row, 6).value) if ca_row else 0.0,
        "actual_taxes": lines["taxes"]["actual"], "uw_taxes_yr0": lines["taxes"]["yr0"],
    }
    tax["adjustment"] = tax["uw_taxes_yr0"] - tax["actual_taxes"]
    wb.close()
    return {"lines": lines, "tax": tax}


# ════════════════════════════════════════════════════════════════════════════
# DEAL CONFIG
# ════════════════════════════════════════════════════════════════════════════
def F(name):
    return os.path.join(INFO, name)


DEALS = [
    {
        "key": "city_centre", "label": "Pearl City Centre + Residences",
        "hd_props": ["Pearl CityCentre (North)", "Pearl Residences"],
        "rr": [F("Recap Rent Rolls 05.26_Pearl City Centre.xlsx"),
               F("Recap Rent Rolls 05.26_Pearl Residences.xlsx")],
        "rediq": F("REDIQ - Actuals-Operating Statement-Pearl CityCentre and Pearl Residences-20260626-030346.xlsx"),
        "lto": [F("Recap LTO 90 day 05.25.26_Pearl City Centre.xlsx"),
                F("Recap LTO 90 day 05.25.26_Pearl Residences.xlsx")],
        "delinq": [F("Recap Delinquency 05.26.26_City Centre.xlsx")],
        "demo": [F("Recap Resident Demographics 05.26_Pearl City Centre.xlsx"),
                 F("Recap Resident Demographics 05.26_Pearl Residences.xlsx")],
        "jll": os.path.join(MODELS, "Pearl City Centre + Residences - 061526_NewDebt.xlsx"),
        "sub": {  # residences sub-breakout
            "label": "Pearl Residences",
            "rr": [F("Recap Rent Rolls 05.26_Pearl Residences.xlsx")],
            "hd_props": ["Pearl Residences"],
            "lto": [F("Recap LTO 90 day 05.25.26_Pearl Residences.xlsx")],
        },
    },
    {
        "key": "golden_glades", "label": "Caroline Golden Glades",
        "hd_props": ["Caroline Golden Glades"],
        "rr": [F("Recap Rent Rolls 05.26_Golden Glades.xlsx")],
        "rediq": F("REDIQ - Actuals-Operating Statement-Caroline Golden Glades-20260626-000414.xlsx"),
        "lto": [F("Recap LTO 90 day 05.25.26_Golden Glades.xlsx")],
        "delinq": [F("Recap Delinquency 05.26.26_Golden Glades.xlsx")],
        "demo": [F("Recap Resident Demographics 05.26_Golden Glades.xlsx")],
        "jll": os.path.join(MODELS, "Caroline Golden Glades - 061526_NewDebt.xlsx"),
    },
    {
        "key": "pearl_washington", "label": "Pearl Washington",
        "hd_props": ["Pearl Washington"],
        "rr": [F("Recap Rent Rolls 05.26_Pearl Washington.xlsx")],
        "rediq": F("REDIQ - Actuals-Operating Statement-Pearl Washington-20260626-250528.xlsx"),
        "lto": [F("Recap LTO 90 day 05.25.26_Pearl Washington.xlsx")],
        "delinq": [F("Recap Delinquency 05.26.26_Pearl Washington.xlsx")],
        "demo": [F("Recap Resident Demographics 05.26_Pearl Washington.xlsx")],
        "jll": os.path.join(MODELS, "Pearl Washington - 061526_LoanAssumption.xlsx"),
    },
    {
        "key": "pearl_21eleven", "label": "Pearl 21 Eleven",
        "hd_props": ["Pearl 21Eleven"],
        "rr": [F("Recap Rent Rolls 05.26_Pearl 21Eleven.xlsx")],
        "rediq": F("REDIQ - Actuals-Operating Statement-Pearl 21Eleven-20260626-220535.xlsx"),
        "lto": [F("Recap LTO 90 day 05.25.26_Pearl 21Eleven.xlsx")],
        "delinq": [F("Recap Delinquency 05.26.26_Pearl 21Eleven.xlsx")],
        "demo": [F("Recap Resident Demographics 05.26_Pearl 21Eleven.xlsx")],
        "jll": os.path.join(MODELS, "Pearl 21 Eleven - 061526_LoanAssumption.xlsx"),
    },
]


def combine_lto(paths):
    """Resident-weight (by lease count) multiple LTO summaries into one blended trade-out."""
    parts = [parse_lto(p) for p in paths]
    tot_leases = sum(p.get("leases", 0) for p in parts) or 1
    def wavg(field):
        return sum(p.get(field, 0) * p.get("leases", 0) for p in parts) / tot_leases
    pr, cu = wavg("prior_rent"), wavg("cur_rent")
    pe, ce = wavg("prior_eff"), wavg("cur_eff")
    res = {"leases": tot_leases, "prior_rent": pr, "cur_rent": cu, "prior_eff": pe, "cur_eff": ce,
           "period": parts[0].get("period", "")}
    res["tradeout_lease_pct"] = cu / pr - 1 if pr else None
    res["tradeout_eff_pct"] = ce / pe - 1 if pe else None
    res["rows"] = [row for p in parts for row in p.get("rows", [])]
    return finalize_lto(res)


def build_segments(rr_paths, hd_props):
    """Pair each rent roll with its OWN property's HelloData (by index) so the HD-by-unit
    join never crosses properties (which share unit numbers)."""
    segs = []
    for rrp, prop in zip(rr_paths, hd_props):
        su, _ = parse_rr([rrp])
        hp, _ = split_hellodata([prop])
        segs.append((su, il.parse_hellodata(hp)))
    return segs


def run_deal(d):
    print(f"\n{'='*70}\n{d['label']}")
    _, hd_n = split_hellodata(d["hd_props"])
    units, as_of = parse_rr(d["rr"])
    occ = occ_breakdown(units)
    rents = inplace_rents(units)
    op = parse_rediq(d["rediq"])
    lto = combine_lto(d["lto"]) if len(d["lto"]) > 1 else parse_lto(d["lto"][0])
    segments = build_segments(d["rr"], d["hd_props"])
    mix = unit_mix_summary(segments, lto)
    _dq = [parse_delinquency(p) for p in d["delinq"]]
    delq = {k: sum(x[k] for x in _dq) for k in ("total_delinquent", "past_due_30", "net_balance")}
    demo = parse_demographics_full(d["demo"])
    jll = parse_jll(d["jll"])
    jll_pnl = parse_jll_pnl(d["jll"])

    # derived comparisons
    trailing_cap = op["noi_t12"] / jll["price"] if jll["price"] else 0
    forward_cap_t3 = op["noi_t3_ann"] / jll["price"] if jll["price"] else 0
    inplace_cap = jll["noi_yr0"] / jll["price"] if jll["price"] else 0   # JLL Year-0 in-place
    delinq_pct = delq["total_delinquent"] / op["rentinc_t12"] if op["rentinc_t12"] else 0
    conc_pct_egr = abs(op["concessions_t12"]) / op["egr_t12"] if op["egr_t12"] else 0
    rent_to_income = (rents["avg_inplace_rent"] * 12 / demo["hh_income_median"]) if demo["hh_income_median"] else 0
    # in-place AGPR tie: rent-roll AGPR vs T1 AGPR (latest-month Rentinc + LtL)
    t1_agpr_mo = op["rentinc"][-1] + op["ltl"][-1]
    agpr_tie = {
        "rr_agpr_mo": rents["rr_agpr_mo"], "t1_agpr_mo": t1_agpr_mo,
        "var_pct": (rents["rr_agpr_mo"] / t1_agpr_mo - 1) if t1_agpr_mo else None,
        "rr_agpr_unit": rents["rr_agpr_mo"] / occ["units"] if occ["units"] else 0,
    }
    losses = loss_ratios(op, jll_pnl["lines"])
    trends = operating_trends(op)
    # cap-rate stack — every cap defined off ONE basis so the reconciliation ties
    L = jll_pnl["lines"]
    caps = {
        "actual_t12": {"noi": op["noi_t12"], "cap": op["noi_t12"] / jll["price"]},
        "actual_t3": {"noi": op["noi_t3_ann"], "cap": op["noi_t3_ann"] / jll["price"]},
        "jll_actual": {"noi": L["noi"]["actual"], "cap": L["noi"]["actual"] / jll["price"]},
        "jll_uw_yr0": {"noi": jll["noi_yr0"], "cap": jll["noi_yr0"] / jll["price"]},
        "jll_yr1": {"noi": jll["noi_yr1"], "cap": jll["noi_yr1"] / jll["price"]},
        "exit": {"noi": jll["noi_exit"], "cap": jll["exit_cap"]},
    }
    # NOI walk: seller trailing-12 actual -> JLL UW Year-0, component by component
    tax_delta = -(jll_pnl["tax"]["uw_taxes_yr0"] - op["expense_t12"].get("Real Estate Taxes", 0))  # +NOI if taxes fall
    rev_delta = L["egr"]["yr0"] - op["egr_t12"]
    other_exp_delta = (op["opex_t12"] - op["expense_t12"].get("Real Estate Taxes", 0)) - (L["opex"]["yr0"] - L["taxes"]["yr0"])
    walk = {"actual_noi": op["noi_t12"], "rev": rev_delta, "tax": tax_delta,
            "opex_ex_tax": other_exp_delta, "uw_noi": jll["noi_yr0"]}
    # mark-to-market: in-place vs HelloData executed market (loss/gain to lease) + forward signal
    hd_mkt = mix["hd_t90_ask"] or mix["hd_t365_ask"]
    mtm = {
        "in_place": rents["avg_inplace_rent"], "hd_market_t90": mix["hd_t90_ask"], "hd_eff_t90": mix["hd_t90_eff"],
        "hd_market_t365": mix["hd_t365_ask"],
        "loss_to_lease_pct": (hd_mkt / rents["avg_inplace_rent"] - 1) if rents["avg_inplace_rent"] else None,
        "new_lease_to": lto.get("new_tradeout_pct"), "hd_yoy": mix["hd_yoy_ask"],
        "hd_conc_pct": (1 - mix["hd_t90_eff"] / mix["hd_t90_ask"]) if mix["hd_t90_ask"] else None,
    }

    rec = {
        "label": d["label"], "key": d["key"],
        "occ": occ, "rents": rents, "mix": mix, "op": op, "lto": lto,
        "delinq": delq, "demo": demo, "jll": jll, "jll_pnl": jll_pnl, "agpr": agpr_tie,
        "losses": losses, "trends": trends, "caps": caps, "walk": walk, "mtm": mtm,
        "hd_rows": hd_n, "as_of": as_of,
        "derived": {
            "trailing_cap": trailing_cap, "forward_cap_t3": forward_cap_t3,
            "inplace_cap": inplace_cap,
            "jll_noi_vs_trailing": (jll["noi_yr0"] / op["noi_t12"] - 1) if op["noi_t12"] else 0,
            "delinq_pct": delinq_pct, "conc_pct_egr": conc_pct_egr,
            "rent_to_income": rent_to_income,
        },
    }
    if d.get("sub"):
        s = d["sub"]
        su, _ = parse_rr(s["rr"])
        sub_lto = combine_lto(s["lto"]) if len(s["lto"]) > 1 else parse_lto(s["lto"][0])
        sub_segments = build_segments(s["rr"], s["hd_props"])
        rec["sub"] = {
            "label": s["label"],
            "occ": occ_breakdown(su),
            "rents": inplace_rents(su),
            "mix": unit_mix_summary(sub_segments, sub_lto),
            "lto": sub_lto,
        }
    # print summary
    print(f"  units(RR)={occ['units']} phys_occ={occ['phys_occ']*100:.1f}% leased={occ['leased_occ']*100:.1f}% | JLL occ={jll['occupancy']*100:.1f}% units={jll['units']}")
    print(f"  in-place rent ${rents['avg_inplace_rent']:,.0f} (${rents['avg_inplace_psf']:.2f}/sf) | HD T90 ask ${mix['hd_t90_ask']:,.0f} eff ${mix['hd_t90_eff']:,.0f} YoY {('%.1f%%'%(mix['hd_yoy_ask']*100)) if mix['hd_yoy_ask'] is not None else 'n/a'}")
    print(f"  LTO blended {('%.1f%%'%(lto['tradeout_lease_pct']*100)) if lto.get('tradeout_lease_pct') is not None else 'n/a'} (eff {('%.1f%%'%(lto['tradeout_eff_pct']*100)) if lto.get('tradeout_eff_pct') is not None else 'n/a'}) | new {('%.1f%%'%(lto['new_tradeout_pct']*100)) if lto.get('new_tradeout_pct') is not None else 'n/a'} ({lto.get('new_n')}) renew {('%.1f%%'%(lto['renewal_tradeout_pct']*100)) if lto.get('renewal_tradeout_pct') is not None else 'n/a'} ({lto.get('renewal_n')})")
    print(f"  T12 NOI ${op['noi_t12']:,.0f} (T3 ann ${op['noi_t3_ann']:,.0f}) EGR ${op['egr_t12']:,.0f} | conc {conc_pct_egr*100:.1f}% of EGR")
    print(f"  JLL price ${jll['price']:,.0f} cap Yr0 {jll['cap_yr0']*100:.2f}% Yr1 {jll['cap_yr1']*100:.2f}% exit {jll['exit_cap']*100:.2f}% | trailing cap {trailing_cap*100:.2f}% | JLL NOI vs trailing {rec['derived']['jll_noi_vs_trailing']*100:+.1f}%")
    print(f"  IRR lev {jll['irr_lev']*100:.1f}% LP {jll['irr_lp']*100:.1f}% EM {jll['em_lev']:.2f}x | debt {jll['financing_type']} {jll['rate']*100:.2f}% LTV {jll['ltv']*100:.0f}%")
    print(f"  delinq ${delq['total_delinquent']:,.0f} ({delinq_pct*100:.1f}% of GPR) | resident med HH inc ${demo['hh_income_median']:,.0f} rent/income {rent_to_income*100:.0f}%")
    return rec


def main():
    deals = [run_deal(d) for d in DEALS]
    out = {"generated": "2026-06-29", "deals": deals}
    with open(os.path.join(ROOT, "analysis", "data.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nWrote analysis/data.json ({len(deals)} deals)")


if __name__ == "__main__":
    main()
