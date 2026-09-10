#!/usr/bin/env python3
"""
02_estimator1_baseline.py  — Estimator 1: slow-trend dose-response (BIASED baseline).

For each hour-of-day h, regress the 4am-anchored load anomaly (cell mean over year x quarter)
on cumulative installed PV (MW) and battery (MWh), with quarter (season) fixed effects:

    load_anom[y,q,h] = a_h + season_q + beta_pv,h * PV_cum + beta_batt,h * Batt_cum + e

Known to be collinear (PV, battery, EV adoption all trend up post-2020) -> the battery coefficient
absorbs EV charging and PV self-consumption. Reported as the biased reference against Estimator 2.

Outputs: estimator1_coeffs_by_hour.csv
"""
import os
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ANA = os.environ.get(
    "OAHU_ANA",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "raw"))
OUT = os.environ.get(
    "OAHU_OUT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "derived"))
os.makedirs(OUT, exist_ok=True)
cell = pd.read_csv(os.path.join(OUT, "panel_qtr_hour_anchored.csv"))
cell["quarter"] = cell["quarter"].astype("category")

rows = []
for h in range(24):
    sub = cell[cell["hour"] == h].copy()
    # scale installs to natural units: PV in MW, battery in MWh
    m = smf.ols("load_anom ~ C(quarter) + pv_mw_cum + batt_mwh_cum", data=sub).fit()
    rows.append(dict(
        hour=h,
        beta_pv=m.params.get("pv_mw_cum", np.nan),
        se_pv=m.bse.get("pv_mw_cum", np.nan),
        beta_batt=m.params.get("batt_mwh_cum", np.nan),
        se_batt=m.bse.get("batt_mwh_cum", np.nan),
        n=int(m.nobs), r2=m.rsquared))
res = pd.DataFrame(rows)
res.to_csv(os.path.join(OUT, "estimator1_coeffs_by_hour.csv"), index=False)
pd.set_option("display.width", 160)
print(res.round(4).to_string(index=False))

# quick sanity: report the key anchors mentioned in prior work
for h in [4, 12, 18]:
    r = res[res.hour == h].iloc[0]
    print(f"h={h:02d}: PV={r.beta_pv:+.3f} MW/MW  Batt={r.beta_batt:+.3f} MW/MWh")
