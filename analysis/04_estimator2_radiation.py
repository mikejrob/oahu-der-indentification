#!/usr/bin/env python3
"""
04_estimator2_radiation.py — Estimator 2: radiation-identified (PRIMARY design).

Identify off high-frequency day-to-day radiation variation (exogenous, orthogonal to slow
install/EV trends). Two terms:

 PV term (contemporaneous): for daytime hours, load responds to GHI[h] x PV_installed.
   Coefficient b (MW load reduction per (W/m2 * MW installed)) -> convert to MW/MW at
   reference GHI. This is identified within-year from cloud-driven GHI variation, so it
   does NOT rely on the slow PV install trend and is not confounded by EV growth.

 Battery term (predictive): evening load[17-20h] responds to same-day MIDDAY GHI x Batt_installed.
   Sunny midday -> fuller battery -> more evening discharge -> LOWER evening load. PV cannot
   generate in the evening so this cleanly separates battery from PV. Controlled for EVENING
   temperature (the AC confound for evening load) + hour x season FE + year FE (EV/secular).

CAVEAT: on-disk radiation covers only 2007,2008,2018,2019. Battery installs in those years are
~0 (BatteryBonus started 2022), so the battery term here is a PIPELINE VALIDATION with ~no
signal. The PV term IS estimable (PV ~500 MW by 2018/19). Battery-era radiation (2020-2024)
is the blocker.

Outputs: estimator2_pv_term.csv, estimator2_battery_term.csv, estimator2_summary.txt
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
YEARS = [2007, 2008, 2018, 2019]
REF_GHI = 1000.0  # reference irradiance (W/m2) for reporting MW/MW at "full sun"

# ---- load hourly panel with installs, restrict to radiation years
pan = pd.read_parquet(os.path.join(OUT, "panel_hourly_with_installs.parquet"))
pan = pan[pan["year"].isin(YEARS)].copy()
pan["date"] = pd.to_datetime(pan["date"])

# ---- radiation island-hourly
isl = pd.read_parquet(os.path.join(OUT, "nsrdb_oahu_island_hourly.parquet"))
isl["date"] = pd.to_datetime(isl[["year", "month", "day"]])
isl = isl.rename(columns={"hour": "hour"})

# ---- merge hourly GHI/temp onto load
m = pan.merge(isl[["date", "hour", "ghi", "temp", "dni", "ws"]],
              on=["date", "hour"], how="inner")
# same-day midday GHI + evening temp
daily = pd.read_csv(os.path.join(OUT, "nsrdb_oahu_daily_midday.csv"))
daily["date"] = pd.to_datetime(daily["date"])
m = m.merge(daily, on="date", how="left")
m["season"] = m["quarter"].astype("category")
m["hourF"] = m["hour"].astype("category")
m["yearF"] = m["year"].astype("category")
m["ghi_x_pv"] = m["ghi"] * m["pv_mw_cum"]                 # W/m2 * MW
m["middayghi_x_batt"] = m["ghi_midday"] * m["batt_mwh_cum"]

out = []

# =============================== PV TERM ===============================
# daytime hours 7-17, load ~ hour x season FE + year FE + temp/ws controls + ghi_x_pv
day = m[m["hour"].between(7, 17)].copy()
# per-hour PV response so we can convert to MW/MW and see the midday-deep shape
pv_rows = []
for h in range(7, 18):
    sub = day[day["hour"] == h].copy()
    if sub["ghi"].std() < 1 or sub["pv_mw_cum"].max() < 1:
        continue
    # within-hour: identify off day-to-day GHI variation; control temp (AC), year (secular)
    mod = smf.ols("load_mw ~ C(season) + C(yearF) + temp + I(temp**2) + ws "
                  "+ ghi + ghi_x_pv", data=sub).fit()
    b = mod.params.get("ghi_x_pv", np.nan)      # MW per (W/m2 * MW installed)
    se = mod.bse.get("ghi_x_pv", np.nan)
    pv_rows.append(dict(hour=h, b_ghi_x_pv=b, se=se,
                        mw_per_mw_at_ref=b * REF_GHI,  # MW load / MW installed at REF_GHI
                        n=int(mod.nobs)))
pv = pd.DataFrame(pv_rows)
pv.to_csv(os.path.join(OUT, "estimator2_pv_term.csv"), index=False)
out.append("PV TERM (radiation-identified, years %s):" % YEARS)
out.append(pv.round(5).to_string(index=False))
# noon capacity-factor equivalent
if not pv.empty:
    noon = pv[pv.hour == 12]
    if len(noon):
        out.append("  noon (h=12) MW load-reduction per MW installed at %g W/m2 = %.3f"
                   % (REF_GHI, -noon["mw_per_mw_at_ref"].iloc[0]))

# =============================== BATTERY TERM ===============================
# evening load 17-20h ~ hour x season FE + year FE + EVENING temp control + midday_ghi_x_batt
eve = m[m["hour"].between(17, 20)].copy()
if eve["batt_mwh_cum"].max() < 1:
    out.append("\nBATTERY TERM: batt_mwh_cum ~ 0 in radiation years (max=%.2f MWh) "
               "-> term is a PIPELINE VALIDATION ONLY, no signal to identify. "
               "BLOCKER: need 2020-2024 NSRDB radiation." % eve["batt_mwh_cum"].max())
    # still fit to prove it runs
    try:
        modb = smf.ols("load_mw ~ C(hourF) + C(season) + C(yearF) + temp_evening "
                       "+ I(temp_evening**2) + middayghi_x_batt", data=eve).fit()
        cb = modb.params.get("middayghi_x_batt", np.nan)
        out.append("  (pipeline check) coef middayghi_x_batt = %.6g (expected ~0 here)" % cb)
        pd.DataFrame([dict(coef_middayghi_x_batt=cb,
                           note="validation only, batt~0 in years")]).to_csv(
            os.path.join(OUT, "estimator2_battery_term.csv"), index=False)
    except Exception as e:
        out.append("  battery fit error: %s" % e)
else:
    modb = smf.ols("load_mw ~ C(hourF) + C(season) + C(yearF) + temp_evening "
                   "+ I(temp_evening**2) + middayghi_x_batt", data=eve).fit()
    cb = modb.params.get("middayghi_x_batt", np.nan)
    seb = modb.bse.get("middayghi_x_batt", np.nan)
    out.append("\nBATTERY TERM: coef = %.6g (se %.6g) MW per (W/m2 * MWh)" % (cb, seb))
    pd.DataFrame([dict(coef_middayghi_x_batt=cb, se=seb)]).to_csv(
        os.path.join(OUT, "estimator2_battery_term.csv"), index=False)

txt = "\n".join(out)
with open(os.path.join(OUT, "estimator2_summary.txt"), "w") as fh:
    fh.write(txt + "\n")
print(txt)
print("\nDONE 04")
