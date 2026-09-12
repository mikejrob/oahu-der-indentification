#!/usr/bin/env python3
"""31_combined_spec.py -- the anchored hour profile (28) and the radiation
interactions (22/26) in one equation, per hour of day.

  load(h,d) - load(4am,d) =
      season spline + weekend + linear trend + f(T(h,d)) + dewpoint
      + g0 GHI(h,d) + sum_k a_k GHI_day(d-k), k=0..2          [uninteracted:
                                                          the pre-PV response]
      + p PV(d) + q BATT(d)                                   [hour profile]
      + b GHI(h,d).PV(d) + c GHI_day(d).PV(d)                 [PV x radiation]
      + e GHI(h,d).BATT(d) + f GHI_day(d).BATT(d)             [storage x radiation]

Radiation in kW/m2, stocks in MW, so interaction coefficients read MW per MW
per kW/m2. PV is all rooftop capacity; BATT is storage-era capacity, so q, e, f
are the extra per storage-era MW over an average rooftop MW.

Predictions if the pieces are what we say they are
  overnight 0-3   : p, q, b, c, e, f all zero (placebo)
  daylight        : b negative (generation), e positive (charging absorbs the
                    anomaly), p and q levels absorbed mostly by b and e
  after dark      : b = e = 0 by construction (GHI(h)=0); q negative at 19-20
                    (contractual discharge); f small negative (fuller battery
                    after a bright day); c the growth of evening weather
                    dependence with PV
Newey-West, 28 lags, one observation per date. Two sample starts, 2006 and
2010, because the uninteracted terms are pinned by the low-PV years.
"""
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "raw"
OUT = REPO / "data" / "derived"
SAMPLE_END = pd.Timestamp("2025-06-30")

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
w = w.reindex(pd.date_range("2006-01-01", h.date.max(), freq="D")).ffill().fillna(0)
w.index.name = "date"
h = h.merge(w[["PV", "BATT"]].reset_index(), on="date", how="left")
day = h[h.hour.between(8, 16)].groupby("date").ghi.mean().rename("gd").to_frame()
day = day.reindex(pd.date_range(day.index.min(), day.index.max(), freq="D"))
day["gd1"] = day.gd.shift(1); day["gd2"] = day.gd.shift(2)
day.index.name = "date"
h = h.merge(day.reset_index(), on="date", how="left")
anch = h[h.hour == 4].set_index("date").load_mw.rename("anch")
h = h.merge(anch, on="date", how="left")
h = h.dropna(subset=["load_mw", "anch", "t_pv", "td_pv", "ghi", "gd", "gd1", "gd2"])
h = h[h.date <= SAMPLE_END].copy()
h["y"] = h.load_mw - h.anch
for c in ("ghi", "gd", "gd1", "gd2"):
    h[c] = h[c] / 1e3
h["doy"] = h.date.dt.dayofyear
h["we"] = (h.date.dt.dayofweek >= 5).astype(int)


# Centered version. Radiation enters as anomalies from an hour-by-season
# climatology, so the level terms p, q are read at normal weather and the
# interactions are the marginal weather dependence. One radiation interaction
# per hour: the same-hour anomaly by day, the daytime-mean anomaly after dark.
# Same-hour and daytime-mean GHI correlate above 0.8 at midday, which is why the
# uncentered two-interaction version returns offsetting pairs.
h["ghi_a"] = smf.ols("ghi ~ cr(doy, df=7):C(hour) + cr(doy, df=7) + C(hour)", data=h).fit().resid
dd = h[h.hour == 12][["date", "doy", "gd", "gd1", "gd2"]].copy()
m = smf.ols("gd ~ cr(doy, df=7)", data=dd).fit()
dd["gd_a"] = m.resid
dd["gd1_a"] = dd.gd1 - m.predict(dd.assign(doy=(dd.doy - 1).clip(lower=1)))
dd["gd2_a"] = dd.gd2 - m.predict(dd.assign(doy=(dd.doy - 2).clip(lower=1)))
h = h.merge(dd[["date", "gd_a", "gd1_a", "gd2_a"]], on="date", how="left")
print("corr(ghi, gd) at noon: %.2f ; corr(ghi_a, gd_a) at noon: %.2f"
      % (h[h.hour == 12][["ghi", "gd"]].corr().iloc[0, 1], h[h.hour == 12][["ghi_a", "gd_a"]].corr().iloc[0, 1]))

DAY = range(7, 19)   # hours with enough sun that the same-hour anomaly has variance; 6 and 19 use the daytime mean
BASE = "y ~ cr(doy, df=5) + C(we) + hs + t_pv + I(t_pv**2) + td_pv + gd_a + gd1_a + gd2_a + PV + BATT"
F_DAY = BASE + " + ghi_a + ghi_a:PV + ghi_a:BATT"
F_NIGHT = BASE + " + gd_a:PV + gd_a:BATT"
TERMS = ["PV", "BATT", "ghi_a:PV", "ghi_a:BATT", "gd_a:PV", "gd_a:BATT", "gd_a"]


def run(start):
    s0 = h[h.year >= start].copy()
    s0["hs"] = (s0.date - s0.date.min()).dt.days
    rows = []
    for hh in range(24):
        if hh == 4:
            continue
        s = s0[s0.hour == hh].sort_values("date")
        r = smf.ols(F_DAY if hh in DAY else F_NIGHT, data=s).fit(
            cov_type="HAC", cov_kwds={"maxlags": 28, "use_correction": True})
        d = dict(start=start, hour=hh, n=len(s))
        for k in TERMS:
            d[k] = r.params.get(k, np.nan); d[k + "_se"] = r.bse.get(k, np.nan)
        rows.append(d)
    return pd.DataFrame(rows)


res = pd.concat([run(2010), run(2006)], ignore_index=True)
res.to_csv(OUT / "combined_spec_by_hour.csv", index=False)


def cell(r, k, w=7):
    b, e = r[k], r[k + "_se"]
    if np.isnan(b):
        return " " * (w + 1) + "-"
    return "%+*.3f%s" % (w, b, "*" if abs(b / e) > 1.96 else " ")


for start in (2010, 2006):
    o = res[res.start == start].set_index("hour")
    print("\n=== sample %d-2025H1, anchor 4am, linear trend, radiation as anomalies (kW/m2) ===" % start)
    print(" hour |  PV lvl   BATT lvl  (PV+BATT) | anom.PV  anom.BATT  (PV+BATT) | gday_a(main)   [anom = same-hour 7-18, daytime-mean otherwise]")
    for hh in range(24):
        if hh == 4:
            print("    4 | anchor"); continue
        r = o.loc[hh]
        ip, ib = ("ghi_a:PV", "ghi_a:BATT") if hh in DAY else ("gd_a:PV", "gd_a:BATT")
        print(" %4d | %s %s  %+7.3f  | %s %s  %+7.3f  | %s" % (hh, cell(r, "PV"), cell(r, "BATT"), r.PV + r.BATT,
              cell(r, ip), cell(r, ib), r[ip] + r[ib], cell(r, "gd_a")))
    nb = o.loc[[0, 1, 2, 3]]
    print("  placebo 0-3, |t|: PV %.1f  BATT %.1f  gd_a:PV %.1f  gd_a:BATT %.1f" % tuple(
        abs(nb[k] / nb[k + "_se"]).max() for k in ["PV", "BATT", "gd_a:PV", "gd_a:BATT"]))
    d = o.loc[7:18]
    print("  levels, MWh/day per MW:  PV daylight 7-18 %+.2f, BATT %+.2f | 19-20: PV %+.2f, BATT %+.2f | 21-23: PV %+.2f, BATT %+.2f"
          % (d.PV.sum(), d.BATT.sum(), o.loc[19:20].PV.sum(), o.loc[19:20].BATT.sum(), o.loc[21:23].PV.sum(), o.loc[21:23].BATT.sum()))
    print("  same-hour anomaly pass-through 7-18, per kW/m2-h: average MW  %+.2f ; storage-era MW %+.2f"
          % (d["ghi_a:PV"].mean(), (d["ghi_a:PV"] + d["ghi_a:BATT"]).mean()))
    print("  daytime-mean anomaly after dark, per kW/m2: 19-20 PV %+.3f BATT %+.3f | 21-23 PV %+.3f BATT %+.3f | 0-3 PV %+.3f BATT %+.3f"
          % (o.loc[19:20]["gd_a:PV"].sum(), o.loc[19:20]["gd_a:BATT"].sum(), o.loc[21:23]["gd_a:PV"].sum(), o.loc[21:23]["gd_a:BATT"].sum(),
             o.loc[0:3]["gd_a:PV"].sum(), o.loc[0:3]["gd_a:BATT"].sum()))
print("\nwrote", OUT / "combined_spec_by_hour.csv")
