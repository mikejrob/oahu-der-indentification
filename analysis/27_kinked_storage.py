#!/usr/bin/env python3
"""27_kinked_storage.py -- structural restriction from the state-of-charge cap.

THE STRUCTURE

A residential battery stores min(E, surplus generation) and, under Battery
Bonus, discharges min(commitment, stored) in a fixed two-hour evening window.
Both operators are CENSORED, and that censoring is what buys identification.

  sunny day   battery reaches E before dusk. Extra radiation adds nothing to
              stored energy, so it adds nothing to evening discharge. The
              evening response to radiation is FLAT.
  cloudy day  battery does not fill. Extra radiation raises stored energy and
              therefore evening discharge. The evening response is NEGATIVE
              (more sun -> more discharge -> lower evening load).

So the storage signature is ONE-SIDED in the sign of the anomaly. Write

    A- = min(A, 0)    below-normal sun
    A+ = max(A, 0)    above-normal sun

and the prediction is delta- < 0 and delta+ ~ 0 in the discharge window.

WHY THIS HELPS IDENTIFICATION

Storage-era capacity and install vintage are the same column after 2021Q2, so
no linear contrast separates them. But the confounders are SYMMETRIC in the
anomaly: declining marginal effectiveness at higher penetration, changing
household composition, different system sizing all scale the response without
regard to the sign of A. The state-of-charge cap is one-sided. So the
asymmetry delta- minus delta+ is a signature of the battery constraint
specifically, identified WITHIN the storage cohort rather than against a
contemporaneous non-storage cohort that does not exist.

The same kink is applied to the thermal block and the PV block, so that an
asymmetric air-conditioning response or an export constraint on the PV side
cannot masquerade as the battery.

Discharge window is taken from Rule 31: two consecutive hours inside
18:00-20:30, so the 18-20 bin is where the prediction bites.
"""
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "raw"
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

g = (h.groupby(["sday", "bin"])
     .agg(load=("load_mw", "mean"), t=("t_pv", "mean"), td=("td_pv", "mean"),
          doy=("day_of_year", "first"),
          we=("date", lambda s: int(s.iloc[0].dayofweek >= 5)),
          PV=("PV", "first"), BATT=("BATT", "first")).reset_index())
# daily shock = mean anomaly over the four daylight bins
A = h[h.bin < 4].groupby("sday").anom.mean().rename("A")
g = g.merge(A, on="sday", how="left").dropna()
g["Aneg"] = np.minimum(g.A, 0.0)
g["Apos"] = np.maximum(g.A, 0.0)
g["hs"] = (g.sday - g.sday.min()).dt.total_seconds() / 3600.
g["tidx"] = g["sday"].rank(method="dense").astype(int) - 1
g = g.sort_values(["sday", "bin"]).reset_index(drop=True)

terms = []
for side in ("Aneg", "Apos"):
    for nmn, mult in (("g", 1.0), ("b", g.PV), ("d", g.BATT)):
        col = "%s_%s" % (nmn, side)
        g[col] = g[side] * mult
        terms.append(col)

print("solar days %d, rows %d" % (g.sday.nunique(), len(g)))
print("A: sd %.1f W/m2 ; %.0f%% of days below normal" % (g.A.std(), 100 * (g.A < 0).mean()))

F = ("load ~ C(bin):cr(doy, df=4) + C(bin):C(we) + C(bin) + cr(hs, df=6)"
     " + C(bin):t + C(bin):I(t**2) + C(bin):td + "
     + " + ".join("C(bin):%s" % c for c in terms))
r = smf.ols(F, data=g).fit(cov_type="hac-groupsum",
                           cov_kwds={"time": g.tidx.to_numpy(), "maxlags": 28,
                                     "use_correction": "cluster"})
nm = list(r.params.index); V = r.cov_params().values


def get(b, col):
    k = "C(bin)[%d]:%s" % (b, col)
    return (nm.index(k), r.params[k]) if k in nm else (None, np.nan)


print("\nONE-SIDED RESPONSE BY BIN. units: MW per MW installed per 1000 W/m2")
print("prediction for storage: delta- negative, delta+ near zero, in 18-20\n")
print("  bin     beta-     beta+   |   delta-    delta+   |  delta- minus delta+")
for b in range(8):
    row = "  %s " % BLAB[b]
    for blk in ("b", "d"):
        for side in ("Aneg", "Apos"):
            i, v = get(b, "%s_%s" % (blk, side))
            if i is None:
                row += "        ."
                continue
            e = np.sqrt(V[i, i]) * 1000
            row += " %+8.3f%s" % (v * 1000, "*" if abs(v * 1000 / e) > 1.96 else " ")
        row += "  |" if blk == "b" else ""
    i1, v1 = get(b, "d_Aneg"); i2, v2 = get(b, "d_Apos")
    if i1 is not None and i2 is not None:
        d = (v1 - v2) * 1000
        se = np.sqrt(V[i1, i1] + V[i2, i2] - 2 * V[i1, i2]) * 1000
        row += "   %+8.3f (se %.3f) t %+5.2f%s" % (d, se, d / se,
                                                   "*" if abs(d / se) > 1.96 else "")
    print(row)
print("\n* = |t| > 1.96")
print("DONE 27")
