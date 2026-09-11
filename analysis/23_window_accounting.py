#!/usr/bin/env python3
"""23_window_accounting.py -- where does the solar anomaly go?

One cloud shock per day, traced through all 24 hours in six 4-hour windows,
separately by program era, so the day's energy is fully accounted for.

SPECIFICATION

  load(h,d) = a_w(h) . seasonal_w(doy) . weekend_w
            + trend(t) + temp_w(T_pv)
            + sum_w  gamma_w  . 1[w(h)=w] . A(d)
            + sum_w sum_e beta_we . 1[w(h)=w] . A(d) . kW_e(d)
            + e(h,d)

  A(d)      the day's cloud shock: the residual from regressing GHI on a
            natural spline in day-of-year interacted with hour, averaged over
            10:00-14:00. Positive A = sunnier than that calendar date normally is.
  w         six windows: 0-3, 4-7, 8-11, 12-15, 16-19, 20-23 HST
  kW_e(d)   installed capacity under program era e, measured, cumulative
  gamma_w   response at zero rooftop capacity: the air-conditioning and
            lighting channel a sunny day opens regardless of panels
  beta_w    response per installed MW of ANY rooftop capacity
  delta_w   ADDITIONAL response per installed MW of storage-era capacity

  Parameterised as total-plus-increment rather than one term per era. The era
  stocks saturate -- NEM/CGS is constant at 441 MW for 69 percent of days -- so
  A*kW_NEM is exactly proportional to A after 2016 and competes with the main
  effect, which is what made a per-era parameterisation unstable at night.
  Total capacity grows throughout (CV 0.29); storage grows only 2021-2024
  (CV 1.92). delta_w is still "storage era minus NEM/CGS", just better
  conditioned.

Reported as ENERGY: beta * 4 hours = MWh per installed MW per 1,000 W/m2 of
midday anomaly. Summing over the six windows accounts for the whole day.

IDENTIFYING ASSUMPTIONS

  A1 Cloud shocks are exogenous to demand. Deviations of radiation from its
     seasonal-by-hour climatology are unrelated to electricity demand except
     through weather channels that enter the controls. The live threat is
     temperature and humidity co-moving with cloud; a window-specific quadratic
     in station-based temperature absorbs the first. Humidity is not controlled.
  A2 Capacity is predetermined. Installed kW on day d cannot respond to day d's
     weather; installation takes months.
  A3 Era composition is exogenous conditional on controls. THE WEAK ONE.
     Households adopting under BatteryBonus differ from 2013 net-metering
     adopters in house age, income and cooling equipment. Differencing against
     NEM/CGS removes channels common to rooftop capacity, not selection.
  A4 Common time-varying confounds are absorbed by the secular trend and the
     seasonal-by-window surface. A trend in weather-sensitivity that coincides
     with one era's growth cannot be separated from it; the defence is that the
     three eras grow in staggered, saturating windows that a single smooth
     trend cannot mimic.
  A5 The response is linear in installed capacity. No saturation.
  A6 No carryover across days, so the six windows exhaust the response.
     TESTED below against the next day's windows.

FALSIFICATION

  - Night windows (0-3, 4-7) should show no era differences: no generation, and
    storage on Oahu discharges in the evening peak, not overnight.
  - The NEXT day's windows should show no response to today's shock under A6.
  - The PREVIOUS day's windows should show none either: no anticipation.
"""
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
h = pd.read_parquet(REPO / "data/analysis/oahu_hourly_panel.parquet")
h = h.sort_values(["date", "hour"]).reset_index(drop=True)
h["date"] = pd.to_datetime(h["date"])
h["day_of_year"] = h.date.dt.dayofyear
h["hour_seq"] = np.arange(1, len(h) + 1)
h = h.dropna(subset=["t_pv"]).copy()

S1 = "ghi ~ cr(day_of_year, df=7):C(hour) + cr(day_of_year, df=7) + C(hour)"
h["ghi_anomaly"] = smf.ols(S1, data=h).fit().resid
A = h[h.hour.between(10, 14)].groupby("date").ghi_anomaly.mean().rename("A")
h = h.merge(A, on="date", how="left")
# lead and lag of the same shock, for the carryover and anticipation tests
sh = A.reset_index()
h = h.merge(sh.assign(date=sh.date + pd.Timedelta(days=1)).rename(columns={"A": "A_lag"}),
            on="date", how="left")
h = h.merge(sh.assign(date=sh.date - pd.Timedelta(days=1)).rename(columns={"A": "A_lead"}),
            on="date", how="left")

h["kw_storage"] = h.kw_BatteryBonus + h.kw_SmartDER
h["kw_total"] = h.kw_NEM_CGS + h.kw_CSS_SmartExport + h.kw_storage
TERMS = [("x_total", "kw_total", "all rooftop capacity"),
         ("x_css", "kw_CSS_SmartExport", "CSS/SmartExport increment"),
         ("x_sto", "kw_storage", "storage-era increment")]
h["win"] = (h.hour // 4) * 4
WINS = sorted(h.win.unique())
WLAB = {0: "00-03", 4: "04-07", 8: "08-11", 12: "12-15", 16: "16-19", 20: "20-23"}
for nmc, col, _ in TERMS:
    h[nmc] = h.A * h[col]
h["tidx"] = h["date"].rank(method="dense").astype(int) - 1
h = h.dropna(subset=["A", "A_lag", "A_lead"])

F = ("load_mw ~ C(win):cr(day_of_year, df=5) + C(win):C(is_weekend) + C(hour)"
     " + cr(hour_seq, df=4) + C(win):t_pv + C(win):I(t_pv**2)"
     " + C(win):A + C(win):A_lag + C(win):A_lead"
     " + " + " + ".join("C(win):%s" % t for t, _, _ in TERMS))
r = smf.ols(F, data=h).fit(cov_type="hac-groupsum",
                           cov_kwds={"time": h.tidx.to_numpy(), "maxlags": 28,
                                     "use_correction": "cluster"})
nm = list(r.params.index)
V = r.cov_params().values
print("n = %d, parameters = %d\n" % (int(r.nobs), len(nm)))

def find(win, var):
    """Patsy names these C(win)[<level>]:<var>; win is the integer window."""
    want = "C(win)[%d]:%s" % (win, var)
    if want in nm:
        return want
    alt = "%s:C(win)[%d]" % (var, win)
    return alt if alt in nm else None

def val(win, var, kw=1e6):
    n = find(win, var)
    g = np.zeros(len(nm)); g[nm.index(n)] = 1.0
    return r.params[n] * kw, float(np.sqrt(g @ V @ g)) * kw, g

def lincomb(g, kw=1e6):
    d = float(g @ r.params.values) * kw
    return d, float(np.sqrt(g @ V @ g)) * kw

H = 4.0   # hours per window: coefficients are MW, energy is MW x 4h
print("ENERGY per installed MW per 1,000 W/m2 of midday anomaly (MWh, 4h windows)")
print("negative = that capacity LOWERS grid load in that window\n")
print("  window   all capacity        CSS increment      storage increment")
acc = {t: np.zeros(len(nm)) for t, _, _ in TERMS}
for w in WINS:
    line = "  %s " % WLAB[w]
    for t, _, _ in TERMS:
        _, _, g = val(w, t)
        acc[t] += g * H
        d, e = lincomb(g * H)
        line += " %8.3f (%.3f)%s" % (d, e, "*" if abs(d / e) > 1.96 else " ")
    print(line)
print("  " + "-" * 68)
print("\n  DAILY TOTAL (sum of the six windows)")
for t, _, lab in TERMS:
    d, e = lincomb(acc[t])
    print("   %-28s %8.3f MWh (se %.3f)  t %+5.2f" % (lab, d, e, d / e))

print("\nFALSIFICATION")
for lab, var in (("next day's shock (carryover, A6)", "A_lead"),
                 ("previous day's shock (anticipation)", "A_lag")):
    g = np.zeros(len(nm))
    for w in WINS:
        n = find(w, var)
        if n:
            g[nm.index(n)] = H
    d, e = lincomb(g, kw=1.0)
    print("  %-38s summed over the day: %+8.2f MW (se %.2f) t %+5.2f"
          % (lab, d, e, d / e))
print("DONE 23")
