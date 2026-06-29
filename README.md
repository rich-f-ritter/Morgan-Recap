# Morgan Recap — Portfolio & Asset Analysis

High-level trend analysis and JLL-underwriting comparison for **The Morgan Group's
"Morgan Recap"** — a JLL-brokered recapitalization of four multifamily deals / five
properties (three Houston, one Miami) currently owned by Morgan.

Produced to the **Milestone Group brand spec** using the **RR‑T12 Processor**
methodology (RedIQ-replacement underwriting intake): rent rolls, RedIQ‑standardized
operating statements, lease trade‑out (LTO), HelloData executed rents, delinquency,
and resident demographics — compared against the JLL models.

## Deliverables (`output/`)

| File | What it is |
|---|---|
| `Morgan_Recap_Analysis.pdf` | 5 branded pages — **portfolio data tape** (p1) + a **one‑pager per deal** (p2–5). |
| `Morgan_Recap_Data_Tape.xlsx` | Editable, brand‑styled Excel: dashboard (KPIs + asset tape + underwriting + trend scorecard) and four raw detail tabs (operating T12 monthly, rent & leasing, underwriting & returns, demographics). |
| `*.png` | Page previews of each PDF page. |

## Portfolio at a glance

5 properties · **1,232 units** · **$318.5M ask** · blended **4.96% in‑place cap**
(4.83% on trailing‑12 actuals) → **4.93% exit** · 5‑yr hold.

| Deal | Units | Built | Ask | $/Unit | Occ | New‑lease T/O | Trailing cap | JLL in‑place cap | Exit | Debt | Lev IRR / EM |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|--:|
| Pearl City Centre + Residences | 459 | '15/'16 | $127.0M | $277K | 96.9% | **+3.5%** | 5.16% | 5.07% | 5.00% | New 5.55% IO | 16.3% / 2.00x |
| Caroline Golden Glades (Miami) | 236 | 2024 | $85.0M | $360K | 92.4% | **−11.5%** | 4.47% | 4.67% | 4.75% | New 5.55% IO | 15.2% / 1.92x |
| Pearl Washington | 322 | 2016 | $60.0M | $186K | 93.8% | **−15.2%** | 4.62% | 5.13% | 5.00% | **Assumption 4.26% IO** | 17.7% / 2.14x |
| Pearl 21 Eleven | 215 | 2015 | $46.5M | $216K | 94.9% | **−7.0%** | 4.82% | 4.97% | 5.00% | **Assumption 3.90% IO** | 16.4% / 2.02x |

## Key trends & findings

- **Rents are bifurcated.** New‑lease trade‑outs (the truest in‑place market signal) are
  **negative at three of four assets** — Pearl Washington −15.2%, Golden Glades −11.5%,
  21 Eleven −7.0% — while **City Centre + Residences is the lone outlier at +3.5%**
  (97% occupied trophy). Renewals stay slightly positive everywhere; operators are
  cutting **new** leases to hold occupancy.
- **Concessions are escalating** at the Houston assets (Pearl Washington from ~$0.4K/mo
  to ~$16K/mo over the trailing year). Golden Glades is a 2024 lease‑up still burning off
  heavy concessions (6.6% of EGR).
- **JLL underwrites above seller actuals on the soft assets.** JLL's Year‑0 (in‑place)
  NOI runs **+11% above the seller's trailing‑12 at Pearl Washington** (and modestly above
  at GG/21E), while it is **−2% (conservative) at City Centre**. The PW gap, paired with a
  **7.0% loss‑to‑lease recapture assumption against new leases trading −15.2%**, is the
  sharpest underwriting tension in the portfolio.
- **Cap rates are full.** Blended ~4.96% in‑place to a ~4.93% exit, with **Golden Glades
  the tightest (4.67% in‑place / 4.75% exit) and highest basis ($360K/unit)** despite the
  weakest market‑rent momentum (HelloData asking −7.4% YoY).
- **Debt is the standout value.** Two deals (Pearl Washington, Pearl 21 Eleven) carry
  **assumable below‑market fixed‑rate debt at 4.26% / 3.90%, interest‑only** — a meaningful
  edge versus the ~5.55% new financing on the other two.
- **Resident credit is strong across the board** — median household income $93K–$150K,
  rent‑to‑income 19–24%, and 30+ day delinquency under 0.5% of GPR.

## Methodology (what feeds each number)

- **Operating trend (EGR / Opex / NOI, vacancy, concessions, loss‑to‑lease):** RedIQ
  standardized operating statements, trailing‑12 May 2025 – Apr 2026 (monthly series +
  T3/T6 annualizations).
- **Occupancy & in‑place rent / unit mix:** Yardi rent rolls (May 2026), parsed via the
  RR‑T12 library; charge codes remapped `MNEMONIC - Name → Name` so base rent ties to
  contract rent. **Physical occupancy reconciles exactly to the JLL models** (resident‑
  in‑place incl. units on notice ÷ total units).
- **Rent direction:** Yardi Lease Trade‑Out (trailing 90 days) — rent‑weighted
  current‑vs‑prior lease, split into new (Application) vs renewal — cross‑checked against
  HelloData executed T90 asking/effective and HD asking YoY.
- **Cap rates:** *Trailing/Actual* = seller trailing‑12 NOI ÷ JLL ask; *JLL* = the model's
  underwritten Year‑0 (in‑place) and Year‑1 NOI ÷ price; *Exit* = the model's residual.
- **Underwriting & returns:** JLL model `Executive Summary` (price, caps, IRR/EM, debt,
  rent‑growth / loss‑to‑lease / concession / vacancy assumptions).
- **Demographics & credit:** resident demographic reports (median household & personal
  income, household size, age) and aged‑receivable delinquency.

## Decisions taken (adjustable)

A clarifying question prompt didn't reach you, so these defaults were used — easy to change:
1. **Format:** branded PDF one‑pagers + an editable branded Excel data tape.
2. **Grouping:** Pearl City Centre and Pearl Residences are treated as **one deal**
   (matching the JLL model & consolidated P&L), with a **Residences sub‑breakout** noted
   on the page → **4 one‑pagers**.
3. **Editorial stance:** data + trend read + risk flags; **no explicit buy/sell or pricing
   call** (valuation left to your internal models).

## Data flags

- The **Golden Glades** JLL model lists the state as **"TX"; it should read "FL"** (Golden
  Glades / North Miami‑Dade). City/values are otherwise consistent with a Miami asset.
- The **Pearl Residences delinquency** file appears to be a **duplicate of the City Centre
  (North)** tab (same sheet name and row count).
- Source documents reference **"The Morgan Group"** (the Houston developer/owner), not
  "Morgan Properties."

## Reproducing

```bash
pip install openpyxl pandas numpy matplotlib
python3 analysis/extract.py      # parses source files -> analysis/data.json
python3 analysis/render_pdf.py   # data.json -> output/Morgan_Recap_Analysis.pdf
python3 analysis/render_xlsx.py  # data.json -> output/Morgan_Recap_Data_Tape.xlsx
```

`extract.py` expects the source workbooks under `_uploads/morgan_info/` and the two
provided skills (RR‑T12 processor, Milestone brand kit) under `_uploads/`; these raw
inputs are git‑ignored (confidential deal materials), but the derived `analysis/data.json`
is committed so the renderers reproduce the deliverables without them.
