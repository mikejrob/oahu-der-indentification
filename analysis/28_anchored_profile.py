#!/usr/bin/env python3
"""28_anchored_profile.py -- hour-of-day profile of the PV and storage effects,
anchored on a pre-dawn hour.

WHY ANCHOR

The storage stock is a smooth function of time, so a trend control flexible
enough to absorb genuine secular drift also absorbs the storage ramp. Every
unanchored specification tried before this one failed the same way: a large
significant storage coefficient overnight, where no mechanism exists.

Subtracting a pre-dawn hour removes the level and the secular trend without a
spline, because that hour carries them too. It is a clean reference for this
question: no solar yet, and a battery that discharged inside the Rule 31 window
of 18:00-20:30 is long empty. Raw load at 3am is flat across 2010-2024 -- 616 to
640 MW while installed PV went from 52 to 765 MW -- which is the evidence that
the anchor is uncontaminated.

  outcome:  load(h,d) - load(anchor,d)
  controls: season spline, weekend, temperature and dewpoint (station-based,
            PV-weighted), contemporaneous GHI, linear trend
  effects:  PV   = per MW of all rooftop capacity
            BATT = extra per MW of storage-era capacity (BatteryBonus+SmartDER)

PREDICTIONS
  PV    negative through daylight, zero after dark
  BATT  positive while charging, negative inside 18:00-20:30, zero overnight
  the overnight hours are the placebo: nothing can happen there
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
# Sample ends 2025-06-30: der_points' last install date. After it the storage
# stock is carried forward flat at 177 MW while EIA-861M shows the real stock
# still rising (263 -> 284 MWh over 2025 H2), so a longer window would hold the
# treatment variable fixed while the treatment itself grew -- attenuation by
# construction. Splicing EIA growth on after mid-2025 is possible and is the
# obvious extension; it is not done here because it mixes two measurement bases.
SAMPLE_END = pd.Timestamp("2025-06-30")
h = h[(h.year >= 2010) & (h.date <= SAMPLE_END)]
h["doy"] = h.date.dt.dayofyear
h["we"] = (h.date.dt.dayofweek >= 5).astype(int)
h["hs"] = (h.date - h.date.min()).dt.days

KEY = [12, 17, 18, 19, 20, 21, 0, 1, 2]


def profile(anchor, trend):
    a = h[h.hour == anchor].set_index("date").load_mw.rename("anch")
    d0 = h.merge(a, on="date", how="left").dropna(subset=["anch"])
    d0 = d0[d0.hour != anchor].copy()
    d0["y"] = d0.load_mw - d0.anch
    out = {}
    for hh in range(24):
        s = d0[d0.hour == hh].sort_values("date")
        if len(s) < 500:
            continue
        f = ("y ~ cr(doy, df=5) + C(we) + %s + t_pv + I(t_pv**2) + td_pv + ghi + PV + BATT"
             % ("hs" if trend == "linear" else "cr(hs, df=%d)" % trend))
        r = smf.ols(f, data=s).fit(cov_type="HAC",
                                   cov_kwds={"maxlags": 28, "use_correction": True})
        out[hh] = (r.params.BATT, r.bse.BATT, r.params.PV, r.bse.PV)
    return out


print("sample %s to %s ; storage-era capacity 0 to %.0f MW"
      % (h.date.min().date(), h.date.max().date(), h.BATT.max()))
print("ROBUSTNESS: storage coefficient (MW per MW of storage-era capacity)")
print("charging hour 12 | dispatch window 19, 20 | placebo 00-02\n")
print("  anchor  trend  |    h12      h17      h18      h19      h20      h21   |   h00     h01     h02")
for anchor in (2, 3, 4, 5):
    for trend in ("linear", 4, 6):
        o = profile(anchor, trend)
        row = "    %dam  %-6s |" % (anchor, trend)
        for hh in KEY:
            if hh not in o:
                row += "      -  "
                continue
            b, e = o[hh][0], o[hh][1]
            row += " %+7.3f%s" % (b, "*" if abs(b / e) > 1.96 else " ")
            if hh == 21:
                row += "  |"
        print(row)
    print()
print("* = |t| > 1.96.  A clean result needs h19/h20 negative and h00-h02 null.")
print("DONE 28")
