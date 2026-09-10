#!/usr/bin/env python3
"""16_write_task_notes.py -- assemble TASK_A_NOTES.md and TASK_B_NOTES.md from result files."""
import os, pandas as pd
ANA = os.environ.get(
    "OAHU_ANA",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "raw"))
OUT = os.environ.get(
    "OAHU_OUT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "derived"))
os.makedirs(OUT, exist_ok=True)

# ---------- TASK A ----------
a_reg = open(os.path.join(OUT, "taskA_regression.txt")).read()
ya = pd.read_csv(os.path.join(OUT, "taskA_lowsun_by_year.csv"))
A = f"""# TASK A -- Low-sun-day grid-defection test

**Hypothesis.** Self-supplied households draw from the grid on very low-sun days, so daily net
load is elevated on low-radiation days beyond a linear-in-radiation prediction, and that
convexity grows with installed behind-the-meter capacity.

**Design.** Daily daytime (8-17h) net load (clock-corrected 714) vs daily midday GHI (NSRDB
island mean). Low-sun = bottom 2 deciles of midday GHI. Two estimators:
(1) pooled OLS with a low-sun x installed-PV interaction, controlling season, temp+temp^2, and a
linear secular/EV trend; (2) per-year "low-sun excess" = mean residual on the year's own
bottom-2-decile GHI days after a within-year linear-in-GHI+temp+season fit (pure convexity, trend
removed).

**Radiation coverage:** see regression output header (extended to 2013-2024 when the S3 pull for
2013-2019 completed).

## Results
```
{a_reg}
```

## Reading
- The pooled `lowsun_x_pv` coefficient is the defection signal: MW of extra low-sun-day grid draw
  per installed MW of distributed PV, growing as the fleet grows.
- The per-year excess traces whether low-sun days became relatively more load-elevated as capacity
  rose. corr(installed PV, low-sun excess) and its slope quantify the growth.
- Reliability translation: multiply the per-MW low-sun excess by installed MW to get the
  firm-capacity stress a low-sun day adds; compare to the naive "low sun = low daytime demand"
  (the negative `ghi_midday` coefficient) to see how much of that relief the defection offsets.

## Caveats
- Identification strengthens with the PV range; a narrow window (2018-2024, PV 476-722 MW) has
  little leverage and the two estimators can disagree in sign there. The 2013-2024 range
  (~200-765 MW) is the credible test.
- AC/temperature on cloudy days is a confound (controlled by temp+temp^2, not eliminated).
- 250-MWh battery scale UNVERIFIED (affects battery, not the PV-defection, interpretation).
"""
open(os.path.join(OUT, "TASK_A_NOTES.md"), "w").write(A)

# ---------- TASK B ----------
wr = pd.read_csv(os.path.join(OUT, "taskB_weighted_vs_uniform_radiation.csv"))
zt_txt = open(os.path.join(OUT, "taskB_zone_install_totals.txt")).read()
last = wr.iloc[-1]
verdict = "MATERIAL" if abs(last.cf_delta_pct) > 2 else "immaterial (< 2%)"
B = f"""# TASK B -- Install-location / zone-weighted radiation

**Question.** Does weighting Oahu radiation by where distributed PV is actually installed change
the effective capacity factor enough to matter for the netting calibration, or is the
island-uniform mean adequate?

## Installed capacity by zone (cross-check)
```
{zt_txt}
```
der_points totals reconcile exactly with der_by_era.csv. Fleet is concentrated in the leeward,
sunnier Ewa_PearlHarbor + Honolulu_South zones.

## Install-weighted vs uniform radiation
Per-cell midday GHI (11-13h) from 264 NSRDB Oahu cells; DER points mapped to nearest cell
(EPSG:26904 -> WGS84). Weighted = cumulative-installed-MW-weighted cell GHI.
```
{wr.round(4).to_string(index=False)}
```

**Finding (2024): weighted/uniform ratio = {last.ratio:.4f} ({last.cf_delta_pct:+.2f}%).**
Implied DistPV CF = {last.implied_distpv_cf:.4f} vs the model's {0.1822:.4f} (annual mean of the
DistPV rows in inputs/variable_capacity_factors.csv).

**Verdict: zone-weighting is {verdict} for the DistPV CF.** The location-invariant inverter/tilt
derate passes through, so the radiation ratio maps directly to a CF ratio.

## Caveats
- Per-cell climatology is midday-GHI mean (11-13h), a proxy for the daily CF; a full 8760 per-cell
  CF would refine it but the spatial ratio is dominated by the leeward/windward GHI gradient.
- EIA-861 net-metering cross-check NOT reachable from this environment (no API/web egress);
  der_by_era is the internal control and it reconciles.
- Permit data (oahu-grid fetch_permits.py) can refine recent install locations but the zone/x-y in
  der_points already localizes the fleet.
- 250-MWh battery scale UNVERIFIED (does not affect the PV-location weighting).
"""
open(os.path.join(OUT, "TASK_B_NOTES.md"), "w").write(B)
print("wrote TASK_A_NOTES.md and TASK_B_NOTES.md")
