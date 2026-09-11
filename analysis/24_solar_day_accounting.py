#!/usr/bin/env python3
"""24_solar_day_accounting.py -- a full-day energy account of the solar anomaly,
by program era, on a day indexed so every window is downstream of the shock.

THE UNIT OF OBSERVATION

A "solar day" tau runs 06:00 on calendar day d to 05:00 on day d+1, and is cut
into six 4-hour windows:

    W1 06-09   morning generation
    W2 10-13   peak generation; the shock is measured here
    W3 14-17   afternoon generation
    W4 18-21   evening peak, sun down, storage discharges
    W5 22-01   late evening and midnight
    W6 02-05   pre-dawn

Indexing this way is what makes the accounting causal. On a calendar day the
00-03 and 04-07 windows PRECEDE the midday shock, so a coefficient on them is
within-day weather persistence, not a battery. That is what produced a profile
peaking at night in the calendar-day version of this specification.

THE SHOCK

    A(tau) = mean over the solar day's daylight hours of the residual from
             GHI ~ ns(day_of_year, df=7) * hour

Positive A means the day delivered more radiation than that calendar date
normally does. Because the seasonal-by-hour climatology is removed, A is cloud.

THE SPECIFICATION

    load(h,tau) = a_w(h) . seasonal_w(doy) . weekend_w + trend(t) + temp_w(T_pv)
                + sum_w gamma_w . 1[w] . A(tau)
                + sum_w beta_w  . 1[w] . A(tau) . kW_total(tau)
                + sum_w delta_w . 1[w] . A(tau) . kW_storage(tau)
                + e

    gamma_w  response to sunshine at ZERO rooftop capacity: the air
             conditioning and lighting channel
    beta_w   response per installed MW of any rooftop capacity
    delta_w  ADDITIONAL response per installed MW of storage-era capacity
             (BatteryBonus + SmartDER); this is the storage signature

Reported as energy: coefficient x 4 hours = MWh per installed MW per 1,000 W/m2
of anomaly. Summing the six windows exhausts the solar day.

WHY THE SAMPLE STARTS IN 2006

gamma and beta are separately identified only if capacity varies away from its
mean. On 2013-2024 alone, installed capacity runs 216 to 765 MW, a coefficient
of variation of 0.29, and the two are correlated at -0.88: the fit puts an
implausible -224 MW on gamma and attenuates beta. Extending to 2006, when
capacity was 0.7 MW, supplies a genuine zero-capacity baseline.

IDENTIFYING ASSUMPTIONS

  A1 Cloud is exogenous to demand given the controls. Radiation deviations from
     the seasonal-by-hour climatology are unrelated to demand except through
     weather. Temperature enters as a window-specific quadratic in the
     station-based series. Humidity does not, and is the main residual threat:
     cloudy days are humid, humidity raises cooling load, which would bias
     gamma and, through it, beta.
  A2 Capacity is predetermined: installation takes months, so kW on day tau
     cannot respond to that day's cloud.
  A3 gamma_w is stable over 2006-2024. THE KEY ASSUMPTION under this design,
     because gamma is identified largely off the early, low-capacity years. If
     the zero-capacity response to sunshine drifted -- air-conditioning
     saturation, building stock, appliance efficiency -- that drift is
     attributed to beta. Probed by re-estimating on 2006-2016 and 2013-2024
     and comparing, and by allowing gamma_w a linear trend.
  A4 Era composition is exogenous given controls. THE WEAK ONE. Households
     adopting under BatteryBonus differ from 2008 adopters in house age,
     income and cooling equipment. delta is a technology contrast only if those
     differences do not themselves change the response to cloud.
  A5 The response is linear in installed capacity: no saturation, no
     congestion, no curtailment threshold.
  A6 No carryover past the solar day, so the six windows exhaust the response.

FALSIFICATION

  F1 W6 (02-05) should show no storage increment: residential batteries are
     empty by the small hours.
  F2 The NEXT solar day's windows should show no response to today's shock.
  F3 The PREVIOUS solar day's should show none either: no anticipation.
  F4 beta summed over the six windows should be negative and of the order of a
     day's rooftop generation; delta summed should be near zero if storage only
     moves energy, and positive if storage moves it behind the meter instead.
"""
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "raw"
h = pd.read_parquet(RAW / "panel_hourly_shifted.parquet")
h["date"] = pd.to_datetime(h["date"])

rad = []
for f in sorted(RAW.glob("_nsrdb_isl_*.parquet")):
    rad.append(pd.read_parquet(f)[["year", "month", "day", "hour", "ghi", "temp"]])
rad = pd.concat(rad, ignore_index=True).drop_duplicates(["year", "month", "day", "hour"])
rad["date"] = pd.to_datetime(rad[["year", "month", "day"]])
h = h.merge(rad[["date", "hour", "ghi"]], on=["date", "hour"], how="inner")

t = pd.read_parquet(REPO / "data/analysis/oahu_temperature_hourly.parquet")
t["date"] = pd.to_datetime(t["date"])
h = h.merge(t[["date", "hour", "t_pv", "td_pv"]], on=["date", "hour"], how="left")

h = h.sort_values(["date", "hour"]).reset_index(drop=True)
h["day_of_year"] = h.date.dt.dayofyear
h["is_weekend"] = (h.date.dt.dayofweek >= 5).astype(int)
h["ts"] = h.date + pd.to_timedelta(h.hour, unit="h")
h["hour_seq"] = (h.ts - h.ts.min()).dt.total_seconds() / 3600.0

# solar day: 06:00 to 05:00, and the six windows within it
h["sday"] = (h.ts - pd.Timedelta(hours=6)).dt.normalize()
h["wpos"] = ((h.ts - pd.Timedelta(hours=6) - h.sday).dt.total_seconds() // (4 * 3600)).astype(int)
WLAB = {0: "06-09", 1: "10-13", 2: "14-17", 3: "18-21", 4: "22-01", 5: "02-05"}

h["ghi_anom"] = smf.ols("ghi ~ cr(day_of_year, df=7):C(hour) + cr(day_of_year, df=7) + C(hour)",
                        data=h).fit().resid
A = (h[h.wpos.isin([0, 1, 2])].groupby("sday").ghi_anom.mean().rename("A"))
h = h.merge(A, on="sday", how="left")
sh = A.reset_index()
h = h.merge(sh.assign(sday=sh.sday + pd.Timedelta(days=1)).rename(columns={"A": "A_lag"}),
            on="sday", how="left")
h = h.merge(sh.assign(sday=sh.sday - pd.Timedelta(days=1)).rename(columns={"A": "A_lead"}),
            on="sday", how="left")

der = pd.read_parquet(RAW / "der_points.parquet")
der["date"] = pd.to_datetime(der["date"], errors="coerce")
der = der.dropna(subset=["date"])
w = (der.assign(n=1).groupby([der.date.dt.normalize(), "era"])["kw_est"].sum()
     .unstack(fill_value=0.0).sort_index().cumsum())
w = w.reindex(pd.date_range(der.date.min().normalize(), h.date.max(), freq="D")).ffill().fillna(0)
w.index.name = "date"
w = w.reset_index()
w["kw_total"] = w[[c for c in w.columns if c != "date"]].sum(1)
w["kw_storage"] = w.get("BatteryBonus", 0.0) + w.get("SmartDER", 0.0)
h = h.merge(w[["date", "kw_total", "kw_storage"]], on="date", how="left")

h["x_tot"] = h.A * h.kw_total
h["x_sto"] = h.A * h.kw_storage
h["tidx"] = h["sday"].rank(method="dense").astype(int) - 1
h = h.dropna(subset=["A", "A_lag", "A_lead", "t_pv", "td_pv", "load_mw"])
print("sample %s to %s, %d hours, %d solar days"
      % (h.date.min().date(), h.date.max().date(), len(h), h.sday.nunique()))
print("capacity range in sample: %.1f to %.0f MW (CV %.2f)"
      % (h.kw_total.min() / 1e3, h.kw_total.max() / 1e3, h.kw_total.std() / h.kw_total.mean()))

F = ("load_mw ~ C(wpos):cr(day_of_year, df=5) + C(wpos):C(is_weekend) + C(hour)"
     " + cr(hour_seq, df=6) + C(wpos):t_pv + C(wpos):I(t_pv**2) + C(wpos):td_pv"
     " + C(wpos):A + C(wpos):A_lag + C(wpos):A_lead"
     " + C(wpos):x_tot + C(wpos):x_sto")
r = smf.ols(F, data=h).fit(cov_type="hac-groupsum",
                           cov_kwds={"time": h.tidx.to_numpy(), "maxlags": 28,
                                     "use_correction": "cluster"})
nm = list(r.params.index); V = r.cov_params().values
H = 4.0

def gvec(wp, var):
    g = np.zeros(len(nm)); g[nm.index("C(wpos)[%d]:%s" % (wp, var))] = 1.0
    return g

def lc(g, kw):
    return float(g @ r.params.values) * kw, float(np.sqrt(g @ V @ g)) * kw

print("\nENERGY per installed MW per 1,000 W/m2 (MWh over each 4-hour window)")
print("negative = lowers grid load\n")
print("  window   gamma (zero-capacity, MW)    beta (per MW, all)     delta (storage extra)")
acc = {"x_tot": np.zeros(len(nm)), "x_sto": np.zeros(len(nm))}
for wp in range(6):
    ga, gs = lc(gvec(wp, "A") * H, 1.0)
    line = "  %s  %9.2f (%.2f)      " % (WLAB[wp], ga, gs)
    for v in ("x_tot", "x_sto"):
        g = gvec(wp, v) * H
        acc[v] += g
        d, e = lc(g, 1e6)
        line += " %8.3f (%.3f)%s" % (d, e, "*" if abs(d / e) > 1.96 else " ")
    print(line)
print("  " + "-" * 76)
for v, lab in (("x_tot", "beta  total over the solar day"),
               ("x_sto", "delta storage increment")):
    d, e = lc(acc[v], 1e6)
    print("   %-34s %8.3f MWh (se %.3f)  t %+5.2f" % (lab, d, e, d / e))

print("\nFALSIFICATION")
for lab, var in (("F2 next solar day's shock", "A_lead"),
                 ("F3 previous solar day's shock", "A_lag")):
    g = np.zeros(len(nm))
    for wp in range(6):
        g += gvec(wp, var) * H
    d, e = lc(g, 1.0)
    print("  %-32s summed: %+8.2f MW (se %.2f) t %+5.2f" % (lab, d, e, d / e))
d, e = lc(gvec(5, "x_sto") * H, 1e6)
print("  F1 storage increment in 02-05    %+8.3f MWh (se %.3f) t %+5.2f" % (d, e, d / e))
print("DONE 24")
