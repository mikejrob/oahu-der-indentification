#!/usr/bin/env python3
"""26_stacked_lag_model.py -- stacked distributed-lag model of the cloud shock.

One equation per 3-hour outcome bin of the solar day, estimated jointly so the
whole lag surface shares a covariance matrix and sums can be tested.

    load(b,d) = controls_b(d)
              + sum_{s<=b} gamma[b,s] . A_s(d)
              + sum_{s<=b} beta[b,s]  . A_s(d) . PV(d)
              + sum_{s<=b} delta[b,s] . A_s(d) . BATT(d)

  A_s(d)  mean radiation anomaly in source bin s of solar day d, the residual
          from GHI on a natural spline in day-of-year interacted with hour
  b,s     solar-day bins: 0=06-08 1=09-11 2=12-14 3=15-17 4=18-20 5=21-23
          6=00-02 7=03-05.  Sources are the four daylight bins 0-3.
  PV      cumulative installed rooftop capacity (MW)
  BATT    cumulative storage-era capacity (MW), BatteryBonus + SmartDER

WHAT EACH BLOCK IS

  gamma   the response at ZERO rooftop capacity. This is the thermal channel:
          a sunny bin warms the building and air conditioning runs, now and
          later. Identified off the low-capacity years, which is why the sample
          starts in 2006 when installed PV was under 1 MW.
  beta    the response per installed MW. At s == b this is contemporaneous
          generation NET of thermal, because gamma absorbs the thermal part.
          Estimates that omit gamma conflate the two and understate generation.
  delta   the additional response per MW of storage-era capacity. Storage
          predicts delta > 0 where charging displaces metered export and
          delta < 0 in the discharge window.

Errors: Driscoll-Kraay across solar days, 28 lags, so within-day correlation
across the eight bins and day-to-day persistence are both handled.
"""
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "raw"
NB, NS = 8, 4
BLAB = {0: "06-08", 1: "09-11", 2: "12-14", 3: "15-17",
        4: "18-20", 5: "21-23", 6: "00-02", 7: "03-05"}

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
h["day_of_year"] = h.date.dt.dayofyear
h["anom"] = smf.ols("ghi ~ cr(day_of_year, df=7):C(hour) + cr(day_of_year, df=7) + C(hour)",
                    data=h).fit().resid

h["ts"] = h.date + pd.to_timedelta(h.hour, unit="h")
h["sday"] = (h.ts - pd.Timedelta(hours=6)).dt.normalize()
h["bin"] = ((h.ts - pd.Timedelta(hours=6) - h.sday).dt.total_seconds() // (3 * 3600)).astype(int)

der = pd.read_parquet(RAW / "der_points.parquet")
der["date"] = pd.to_datetime(der["date"], errors="coerce")
der = der.dropna(subset=["date"])
w = (der.groupby([der.date.dt.normalize(), "era"]).kw_est.sum()
     .unstack(fill_value=0.).sort_index().cumsum())
w = w.reindex(pd.date_range(der.date.min().normalize(), h.date.max(), freq="D")).ffill().fillna(0)
w.index.name = "date"; w = w.reset_index()
w["PV"] = w[[c for c in w.columns if c != "date"]].sum(1) / 1e3
w["BATT"] = (w.get("BatteryBonus", 0.) + w.get("SmartDER", 0.)) / 1e3
h = h.merge(w[["date", "PV", "BATT"]], on="date", how="left")

# collapse to one row per (solar day, bin)
g = (h.groupby(["sday", "bin"])
     .agg(load=("load_mw", "mean"), anom=("anom", "mean"), t=("t_pv", "mean"),
          td=("td_pv", "mean"), doy=("day_of_year", "first"),
          we=("date", lambda s: int(s.iloc[0].dayofweek >= 5)),
          PV=("PV", "first"), BATT=("BATT", "first"))
     .reset_index())
src = g[g.bin < NS].pivot(index="sday", columns="bin", values="anom")
src.columns = ["A%d" % c for c in src.columns]
g = g.merge(src, on="sday", how="left").dropna()
g["hs"] = (g.sday - g.sday.min()).dt.total_seconds() / 3600.
g = g.sort_values(["sday", "bin"]).reset_index(drop=True)

# triangular design: source s enters outcome bin b only for s <= b
terms = []
for b in range(NB):
    for s in range(min(b + 1, NS)):
        for nm, mult in (("g", 1.0), ("b", g.PV), ("d", g.BATT)):
            col = "%s_b%d_s%d" % (nm, b, s)
            g[col] = (g["A%d" % s] * (g.bin == b).astype(float)) * mult
            terms.append(col)
print("solar days %d, rows %d, lag terms %d" % (g.sday.nunique(), len(g), len(terms)))
print("PV %.1f to %.0f MW ; storage 0 to %.0f MW" % (g.PV.min(), g.PV.max(), g.BATT.max()))

F = ("load ~ C(bin):cr(doy, df=4) + C(bin):C(we) + C(bin) + cr(hs, df=6)"
     " + C(bin):t + C(bin):I(t**2) + C(bin):td + " + " + ".join(terms))
g["tidx"] = g["sday"].rank(method="dense").astype(int) - 1
r = smf.ols(F, data=g).fit(cov_type="hac-groupsum",
                           cov_kwds={"time": g.tidx.to_numpy(), "maxlags": 28,
                                     "use_correction": "cluster"})
nm = list(r.params.index); V = r.cov_params().values
np.save(REPO / "data/derived/stacked_V.npy", V)
pd.Series(r.params.values, index=nm).to_csv(REPO / "data/derived/stacked_params.csv")


def show(block, label, scale, unit):
    print("\n%s  (%s)" % (label, unit))
    print("  outcome |" + "".join("   src %s " % BLAB[s] for s in range(NS)))
    for b in range(NB):
        line = "   %s  |" % BLAB[b]
        for s in range(NS):
            k = "%s_b%d_s%d" % (block, b, s)
            if k not in nm:
                line += "          ."
                continue
            i = nm.index(k)
            v = r.params.iloc[i] * scale
            e = np.sqrt(V[i, i]) * scale
            line += " %+8.3f%s" % (v, "*" if abs(v / e) > 1.96 else " ")
        print(line)


show("g", "GAMMA  response at zero rooftop capacity (thermal)", 1000.0,
     "MW per 1000 W/m2 of that source bin's anomaly")
show("b", "BETA   per installed MW of rooftop PV", 1000.0,
     "MW per MW installed, per 1000 W/m2")
show("d", "DELTA  extra per MW of storage-era capacity", 1000.0,
     "MW per MW installed, per 1000 W/m2")
print("\n(* = |t| > 1.96;  '.' = source after outcome, excluded by the triangular design)")


def Ftest(keys):
    idx = [nm.index(k) for k in keys if k in nm]
    R = np.zeros((len(idx), len(nm)))
    for i, j in enumerate(idx):
        R[i, j] = 1.0
    w = r.f_test(R)
    return float(w.fvalue), float(w.pvalue), len(idx)


offb = ["b_b%d_s%d" % (b, s) for b in range(NB) for s in range(min(b + 1, NS)) if s != b]
dia = ["b_b%d_s%d" % (b, b) for b in range(NS)]
dall = ["d_b%d_s%d" % (b, s) for b in range(NB) for s in range(min(b + 1, NS))]
gall = ["g_b%d_s%d" % (b, s) for b in range(NB) for s in range(min(b + 1, NS))]
print("\nJOINT TESTS")
for lab, ks in (("BETA off-diagonal = 0 (PV generates only contemporaneously)", offb),
                ("BETA diagonal = 0", dia),
                ("GAMMA all = 0 (no thermal channel)", gall),
                ("DELTA all = 0 (no storage increment)", dall)):
    f, p, k = Ftest(ks)
    print("  %-54s F=%7.2f p=%.3g (%d)" % (lab, f, p, k))

print("\nTHE BOUND: does omitting the thermal block shrink measured generation?")
F_nog = ("load ~ C(bin):cr(doy, df=4) + C(bin):C(we) + C(bin) + cr(hs, df=6)"
         " + C(bin):t + C(bin):I(t**2) + C(bin):td + "
         + " + ".join([x for x in terms if not x.startswith("g_")]))
r2 = smf.ols(F_nog, data=g).fit(cov_type="hac-groupsum",
                                cov_kwds={"time": g.tidx.to_numpy(), "maxlags": 28,
                                          "use_correction": "cluster"})
print("  bin      with gamma   without gamma   change in |beta|")
for b in range(NS):
    k = "b_b%d_s%d" % (b, b)
    a = r.params[k] * 1000
    c = r2.params[k] * 1000
    print("   %s   %+10.3f  %+13.3f   %+9.1f%%" % (BLAB[b], a, c, 100 * (abs(c) / abs(a) - 1)))

print("\nCOLUMN SUMS: whole-solar-day effect of each source bin's anomaly")
for blk, lab in (("b", "BETA  per installed MW of PV"),
                 ("d", "DELTA per MW of storage-era capacity")):
    print("  %s" % lab)
    for s in range(NS):
        gv = np.zeros(len(nm))
        for b in range(NB):
            k = "%s_b%d_s%d" % (blk, b, s)
            if k in nm:
                gv[nm.index(k)] = 1.0
        v = float(gv @ r.params.values) * 1000
        e = float(np.sqrt(gv @ V @ gv)) * 1000
        print("     source %s : %+8.3f (se %.3f) t %+5.2f" % (BLAB[s], v, e, v / e))
print("DONE 26")
