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
    occ_u = [u for u in units if u.occupancy == "Occupied" and u.contract_rent > 0]
    contract = [u.contract_rent for u in occ_u]
    sf = [u.sqft for u in occ_u if u.sqft]
    tot_contract = sum(u.contract_rent for u in units)
    tot_other = sum(u.other_income for u in units if u.other_income > 0)
    return {
        "avg_inplace_rent": (sum(contract) / len(contract)) if contract else 0.0,
        "avg_inplace_psf": (sum(contract) / sum(sf)) if sf else 0.0,
        "total_contract_mo": tot_contract,
        "total_other_mo": tot_other,
        "n_occ": len(occ_u),
    }


def unit_mix_summary(units, hd):
    # group by bedroom count from inferred bed/bath
    rr = il.RentRoll(units=units)
    mix = il.build_unit_mix(rr, hd)
    by_bed = {}
    for m in mix:
        bd = m.bed if isinstance(m.bed, int) else None
        key = bd
        g = by_bed.setdefault(key, {"units": 0, "occ": 0, "vac": 0, "sf": 0.0, "sf_n": 0,
                                    "contract_sum": 0.0, "contract_n": 0,
                                    "t90_ask_sum": 0.0, "t90_ask_w": 0,
                                    "new": 0})
        g["units"] += m.units
        g["occ"] += m.occ
        g["vac"] += m.vac
        g["new"] += m.new_count
        if m.avg_sqft:
            g["sf"] += m.avg_sqft * m.units
            g["sf_n"] += m.units
        if m.avg_contract:
            g["contract_sum"] += m.avg_contract * m.occ
            g["contract_n"] += m.occ
        if m.t90_ask:
            g["t90_ask_sum"] += m.t90_ask * m.units
            g["t90_ask_w"] += m.units
    rows = []
    for bd in sorted(by_bed, key=lambda x: (99 if x is None else x)):
        g = by_bed[bd]
        rows.append({
            "bed": bd, "units": g["units"], "occ": g["occ"], "vac": g["vac"],
            "avg_sf": g["sf"] / g["sf_n"] if g["sf_n"] else 0,
            "avg_contract": g["contract_sum"] / g["contract_n"] if g["contract_n"] else 0,
            "t90_ask": g["t90_ask_sum"] / g["t90_ask_w"] if g["t90_ask_w"] else 0,
        })
    # mix-weighted HelloData executed reads (portfolio-level)
    t90a = t90e = t365a = t365e = w90 = w365 = 0.0
    yoy_num = yoy_w = 0.0
    for m in mix:
        if m.t90_ask:
            t90a += m.t90_ask * m.units; w90 += m.units
        if m.t90_eff:
            t90e += m.t90_eff * m.units
        if m.t365_ask:
            t365a += m.t365_ask * m.units; w365 += m.units
        if m.t365_eff:
            t365e += m.t365_eff * m.units
        if m.yoy_ask is not None:
            yoy_num += m.yoy_ask * m.units; yoy_w += m.units
    return {
        "by_bed": rows,
        "hd_t90_ask": t90a / w90 if w90 else 0,
        "hd_t90_eff": t90e / w90 if w90 else 0,
        "hd_t365_ask": t365a / w365 if w365 else 0,
        "hd_t365_eff": t365e / w365 if w365 else 0,
        "hd_yoy_ask": yoy_num / yoy_w if yoy_w else None,
        "n_plans": len(mix),
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
    wb.close()
    return out


# ════════════════════════════════════════════════════════════════════════════
# LEASE TRADE-OUT (LTO)
# ════════════════════════════════════════════════════════════════════════════
def parse_lto(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    period = il._s(ws.cell(4, 1).value)
    # --- Summary 'Total/Average:' row ---
    # header row 7: 3=Leases 5=PriorLeaseRent 8=PriorEffRent 10=CurLeaseRent 12=CurEffRent
    res = {"period": period}
    for r in range(7, min(ws.max_row, 40) + 1):
        a = il._s(ws.cell(r, 1).value)
        if a.startswith("Total/Average"):
            res["leases"] = num(ws.cell(r, 3).value)
            res["prior_rent"] = num(ws.cell(r, 5).value)
            res["prior_eff"] = num(ws.cell(r, 8).value)
            res["cur_rent"] = num(ws.cell(r, 10).value)
            res["cur_eff"] = num(ws.cell(r, 12).value)
            break
    if res.get("prior_rent"):
        res["tradeout_lease_pct"] = res["cur_rent"] / res["prior_rent"] - 1
        res["tradeout_eff_pct"] = (res["cur_eff"] / res["prior_eff"] - 1) if res.get("prior_eff") else None

    # --- Detail: split new (Application) vs renewal/MTM ---
    # find detail header row (has 'Current Lease Type')
    hdr = None
    for r in range(1, ws.max_row + 1):
        labs = [il._s(ws.cell(r, c).value).lower() for c in range(1, ws.max_column + 1)]
        if any(l == "current lease type" for l in labs):
            hdr = r
            cols = {il._s(ws.cell(r, c).value).lower(): c for c in range(1, ws.max_column + 1)}
            break
    # accumulate rent-weighted sums per group (Yardi's own trade-out method:
    # Σcurrent / Σprior − 1), so the split ties to the blended summary number
    groups = {"new": [0.0, 0.0, 0], "renewal": [0.0, 0.0, 0]}   # [prior_sum, cur_sum, n]
    if hdr:
        c_type = cols.get("current lease type")
        c_prior = cols.get("prior lease rent")
        c_cur = cols.get("current lease rent") or cols.get("current  lease rent")
        for r in range(hdr + 1, ws.max_row + 1):
            t = il._s(ws.cell(r, c_type).value) if c_type else ""
            if not t:
                continue
            pr = num(ws.cell(r, c_prior).value) if c_prior else 0
            cu = num(ws.cell(r, c_cur).value) if c_cur else 0
            if pr <= 0 or cu <= 0 or abs(cu / pr - 1) > 0.6:   # drop data errors
                continue
            tl = t.lower()
            is_new = ("appl" in tl) or tl.startswith("new")   # NOT 're-NEW-al'
            g = groups["new"] if is_new else groups["renewal"]
            g[0] += pr; g[1] += cu; g[2] += 1
    res["_groups"] = groups
    wb.close()
    return finalize_lto(res)


def finalize_lto(res):
    for grp in ("new", "renewal"):
        pr, cu, n = res.get("_groups", {}).get(grp, [0, 0, 0])
        res[f"{grp}_n"] = n
        res[f"{grp}_tradeout_pct"] = (cu / pr - 1) if pr else None
    return res


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
    # new/renewal: pool the per-group prior/current rent sums, then ratio
    pooled = {"new": [0.0, 0.0, 0], "renewal": [0.0, 0.0, 0]}
    for p in parts:
        for grp in ("new", "renewal"):
            g = p.get("_groups", {}).get(grp, [0, 0, 0])
            pooled[grp][0] += g[0]; pooled[grp][1] += g[1]; pooled[grp][2] += g[2]
    res["_groups"] = pooled
    return finalize_lto(res)


def run_deal(d):
    print(f"\n{'='*70}\n{d['label']}")
    hd_path, hd_n = split_hellodata(d["hd_props"])
    hd = il.parse_hellodata(hd_path)
    units, as_of = parse_rr(d["rr"])
    occ = occ_breakdown(units)
    rents = inplace_rents(units)
    mix = unit_mix_summary(units, hd)
    op = parse_rediq(d["rediq"])
    lto = combine_lto(d["lto"]) if len(d["lto"]) > 1 else parse_lto(d["lto"][0])
    _dq = [parse_delinquency(p) for p in d["delinq"]]
    delq = {k: sum(x[k] for x in _dq) for k in ("total_delinquent", "past_due_30", "net_balance")}
    demo = parse_demographics(d["demo"])
    jll = parse_jll(d["jll"])

    # derived comparisons
    trailing_cap = op["noi_t12"] / jll["price"] if jll["price"] else 0
    forward_cap_t3 = op["noi_t3_ann"] / jll["price"] if jll["price"] else 0
    delinq_pct = delq["total_delinquent"] / op["rentinc_t12"] if op["rentinc_t12"] else 0
    conc_pct_egr = abs(op["concessions_t12"]) / op["egr_t12"] if op["egr_t12"] else 0
    rent_to_income = (rents["avg_inplace_rent"] * 12 / demo["hh_income_median"]) if demo["hh_income_median"] else 0

    rec = {
        "label": d["label"], "key": d["key"],
        "occ": occ, "rents": rents, "mix": mix, "op": op, "lto": lto,
        "delinq": delq, "demo": demo, "jll": jll, "hd_rows": hd_n,
        "as_of": as_of,
        "derived": {
            "trailing_cap": trailing_cap, "forward_cap_t3": forward_cap_t3,
            "jll_noi_vs_trailing": (jll["noi_yr0"] / op["noi_t12"] - 1) if op["noi_t12"] else 0,
            "delinq_pct": delinq_pct, "conc_pct_egr": conc_pct_egr,
            "rent_to_income": rent_to_income,
        },
    }
    if d.get("sub"):
        s = d["sub"]
        su, _ = parse_rr(s["rr"])
        sub_hd_path, _ = split_hellodata(s["hd_props"])
        sub_hd = il.parse_hellodata(sub_hd_path)
        rec["sub"] = {
            "label": s["label"],
            "occ": occ_breakdown(su),
            "rents": inplace_rents(su),
            "mix": unit_mix_summary(su, sub_hd),
            "lto": combine_lto(s["lto"]) if len(s["lto"]) > 1 else parse_lto(s["lto"][0]),
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
