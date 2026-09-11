#!/usr/bin/env python3
"""22_anomaly_spec.py -- the two-stage anomaly specification (MJR, R draft),
with the temperature control added and the identified quantity reported.

Stage 1 purges radiation of its predictable seasonal-by-hour climatology, so the
regressor is a pure cloud shock. Stage 2 regresses load on a flexible
seasonal-by-hour and weekend-by-hour surface, a smooth secular trend, an
hour-varying temperature control, and the cloud shock interacted with installed
capacity.

The interaction coefficient on its own is NOT the PV response. With a free
ghi_anomaly main effect the two are correlated at -0.88, because total installed
capacity has a coefficient of variation of only 0.29 over the sample -- not
enough independent variation to separate "response at zero PV" from "response
per installed MW". The identified quantity is the total response evaluated at an
observed stock, b0 + b1*kW, reported below by hour with delta-method errors.
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
h["tidx"] = h["date"].rank(method="dense").astype(int) - 1
h = h.dropna(subset=["t_pv"])

S1 = "ghi ~ cr(day_of_year, df=7):C(hour) + cr(day_of_year, df=7) + C(hour)"
h["ghi_anomaly"] = smf.ols(S1, data=h).fit().resid
h["kw_total"] = h[["kw_NEM_CGS", "kw_CSS_SmartExport",
                   "kw_BatteryBonus", "kw_SmartDER"]].sum(1)

BASE = ("(cr(day_of_year, df=7) + C(is_weekend)):C(hour) + cr(day_of_year, df=7)"
        " + C(is_weekend) + C(hour) + cr(hour_seq, df=4)"
        " + (t_pv + I(t_pv**2)):C(hour)")
F = f"load_mw ~ {BASE} + ghi_anomaly:C(hour) + ghi_anomaly:C(hour):kw_total"
r = smf.ols(F, data=h).fit(cov_type="hac-groupsum",
                           cov_kwds={"time": h.tidx.to_numpy(), "maxlags": 28,
                                     "use_correction": "cluster"})
names = list(r.params.index)
V = r.cov_params().values
kw = float(h.kw_total.max())
print("total response by hour at the 2024 stock (%.0f MW), MW per installed MW:" % (kw / 1e3))
for hh in range(7, 18):
    a = [n for n in names if "hour)[%d]" % hh in n and "kw_total" not in n
         and "ghi_anomaly" in n]
    b = [n for n in names if "hour)[%d]" % hh in n and "kw_total" in n]
    if not a or not b:
        continue
    g = np.zeros(len(names))
    g[names.index(a[0])] = 1.0
    g[names.index(b[0])] = kw
    tot = r.params[a[0]] + r.params[b[0]] * kw
    se = float(np.sqrt(g @ V @ g))
    print("   %2d   %7.3f  (se %.3f)" % (hh, -tot * 1000 / (kw / 1e3),
                                         se * 1000 / (kw / 1e3)))
print("DONE 22")
