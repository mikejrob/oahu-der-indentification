#!/usr/bin/env python3
"""29_weather_split.py -- weather as a falsification test on the anchored profile.

The anchored profile (28) estimates the storage notch with power but is exposed
to smooth level confounds: induced demand, EV adoption, an imperfect trend. None
of those know what today's cloud cover is. A battery does. So split days into
terciles on the charging-window (09-16) radiation anomaly and ask whether each
hour's coefficient MOVES with today's sun.

  BATT x dark / bright   state-of-charge limit: notch smaller on dark days
                         grid top-up: midday coefficient LARGER on dark days
  PV   x dark / bright   PV cannot generate after 18:00. An evening PV
                         coefficient is induced demand if weather-blind and
                         thermal persistence if larger after a bright day.

Same anchored specification as 28: outcome = load(h) - load(4am), season spline,
weekend, temperature, dewpoint, contemporaneous GHI, linear trend. Sample
2010-01-01 to 2025-06-30. HAC 28 lags. Tercile dummies enter as main effects so
the interactions are net of any level difference between dark and bright days.
"""
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "raw"

h = pd.read_parquet(RAW / "panel_hourly_shifted.parquet")
h["date"] = pd.to_datetime(h["date"])
rad = pd.concat([pd.read_parquet(f)[["year", "month", "day", "hour", "ghi"]]
                 for f in sorted(RAW.glob("_nsrdb_isl_*.parquet"))],
                ignore_index=True).drop_duplicates(["year", "month", "day", "hour"])
rad["date"] = pd.to_datetime(rad[["year", "month", "day"]])
h = h.merge(rad[["date", "hour", "ghi"]], on=["date", "hour"], how="inner")
t = pd.read_parquet(REPO / "data/analysis/oahu_temperature_hourly.parquet")
t["date"] = pd.to_datetime(t["date"])
h = h.merge(t[["date", "hour", "t_pv", "td_pv"]], on=["date", "hour"], how="left")
der = pd.read_parquet(RAW / "der_points.parquet")
der["date"] = pd.to_datetime(der["date"], errors="coerce")
w = (der.dropna(subset=["date"]).groupby([der.date.dt.normalize(), "era"]).kw_est.sum()
     .unstack(fill_value=0.).sort_index().cumsum())
w["PV"] = w.sum(1) / 1e3
w["BATT"] = (w.get("BatteryBonus", 0.) + w.get("SmartDER", 0.)) / 1e3
w = w.reindex(pd.date_range(w.index.min(), h.date.max(), freq="D")).ffill().fillna(0)
w.index.name = "date"
h = h.merge(w[["PV", "BATT"]].reset_index(), on="date", how="left")
h = h.dropna(subset=["t_pv", "td_pv", "load_mw"])
h["doy"] = h.date.dt.dayofyear
h["anom"] = smf.ols("ghi ~ cr(doy, df=7):C(hour) + cr(doy, df=7) + C(hour)", data=h).fit().resid
A = h[h.hour.between(9, 16)].groupby("date").anom.mean().rename("A")
h = h.merge(A, on="date", how="left")
h = h[(h.year >= 2010) & (h.date <= pd.Timestamp("2025-06-30"))]
a = h[h.hour == 4].set_index("date").load_mw.rename("anch")
h = h.merge(a, on="date", how="left").dropna(subset=["anch", "A"])
h = h[h.hour != 4].copy()
h["y"] = h.load_mw - h.anch
h["we"] = (h.date.dt.dayofweek >= 5).astype(int)
h["hs"] = (h.date - h.date.min()).dt.days
q = h.groupby("date").A.first().quantile([1 / 3, 2 / 3])
h["dark"] = (h.A <= q.iloc[0]).astype(int)
h["bright"] = (h.A >= q.iloc[1]).astype(int)

rows = []
for hh in range(24):
    s = h[h.hour == hh].sort_values("date").copy()
    if len(s) < 500:
        continue
    for v in ("BATT", "PV"):
        s[v + "d"] = s[v] * s.dark
        s[v + "b"] = s[v] * s.bright
    r = smf.ols("y ~ cr(doy, df=5) + C(we) + hs + t_pv + I(t_pv**2) + td_pv + ghi"
                " + C(dark) + C(bright) + PV + PVd + PVb + BATT + BATTd + BATTb",
                data=s).fit(cov_type="HAC", cov_kwds={"maxlags": 28, "use_correction": True})
    V = r.cov_params(); nm = list(r.params.index)
    for v in ("BATT", "PV"):
        i, j = nm.index(v + "b"), nm.index(v + "d")
        c = r.params[v + "b"] - r.params[v + "d"]
        ec = float(np.sqrt(V.iloc[i, i] + V.iloc[j, j] - 2 * V.iloc[i, j]))
        rows.append(dict(hour=hh, var=v, mid=r.params[v], mid_se=r.bse[v],
                         dark=r.params[v + "d"], dark_se=r.bse[v + "d"],
                         bright=r.params[v + "b"], bright_se=r.bse[v + "b"],
                         contrast=c, contrast_se=ec))
out = pd.DataFrame(rows)
out.to_csv(REPO / "data/derived/weather_split_profile.csv", index=False)

st = lambda v, e: "*" if abs(v / e) > 1.96 else " "
for v, lab in (("BATT", "STORAGE-era capacity"), ("PV", "all rooftop PV")):
    print("\n%s: coefficient on a middle-tercile day, extra on dark / bright, bright-minus-dark"
          % lab)
    print("  hour   middle            x dark            x bright          contrast")
    for _, r in out[out["var"] == v].iterrows():
        if r.hour not in (12, 13, 17, 18, 19, 20, 21, 22, 23, 0, 1, 2, 3):
            continue
        print("   %2d   %+7.3f (%.3f)%s  %+7.3f (%.3f)%s  %+7.3f (%.3f)%s  %+7.3f (t %+5.2f)%s"
              % (r.hour, r.mid, r.mid_se, st(r.mid, r.mid_se),
                 r.dark, r.dark_se, st(r.dark, r.dark_se),
                 r.bright, r.bright_se, st(r.bright, r.bright_se),
                 r.contrast, r.contrast / r.contrast_se, st(r.contrast, r.contrast_se)))
print("\nDONE 29")
