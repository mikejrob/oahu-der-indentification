#!/usr/bin/env python3
"""20_build_analysis_dataset.py -- assemble the analysis-ready panels.

Every regression in this repository was previously built by merging inside the
estimator script, so no single file held the estimation sample. This writes it
out, hourly and daily, for 2013-2024 (the years with continuous radiation).

Outputs (data/analysis/):
  oahu_hourly_panel.csv / .parquet   one row per corrected-clock (date, hour)
  oahu_daily_panel.csv  / .parquet   one row per date
  der_installs_by_era.csv            cumulative systems and kW by program era

Variable definitions: docs/CODEBOOK.md.
"""
import os
import numpy as np
import pandas as pd
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ANA = Path(os.environ.get("OAHU_ANA", REPO / "data" / "raw"))
OUTD = Path(os.environ.get("OAHU_ANALYSIS", REPO / "data" / "analysis"))
OUTD.mkdir(parents=True, exist_ok=True)
Y0, Y1 = 2013, 2024

# ---------------------------------------------------------------- radiation
rad = pd.concat(
    [pd.read_parquet(ANA / f)[["year", "month", "day", "hour", "ghi", "temp"]]
     for f in ("nsrdb_oahu_island_hourly_2013_2019.parquet",
               "nsrdb_oahu_island_hourly_2020_2024.parquet")],
    ignore_index=True).drop_duplicates(["year", "month", "day", "hour"])
rad["date"] = pd.to_datetime(rad[["year", "month", "day"]])
rad = rad[["date", "hour", "ghi", "temp"]]

daily = (rad[rad.hour.between(10, 14)].groupby("date")
         .agg(ghi_midday=("ghi", "mean"), temp_midday=("temp", "mean")).reset_index()
         .merge(rad[rad.hour.between(17, 20)].groupby("date")
                .agg(temp_evening=("temp", "mean")).reset_index(), on="date")
         .merge(rad.groupby("date").agg(ghi_daily=("ghi", "mean"),
                                        temp_daily=("temp", "mean")).reset_index(),
                on="date"))

# ---------------------------------------------------------------- load + stocks
pan = pd.read_parquet(ANA / "panel_hourly_shifted.parquet")
pan["date"] = pd.to_datetime(pan["date"])
pan = pan[pan.year.between(Y0, Y1)][
    ["date", "year", "month", "hour", "quarter", "load_mw",
     "pv_mw_cum", "batt_mwh_cum", "era_714", "roll_h", "dt_hst"]].copy()

# ---------------------------------------------------------------- era stocks
der = pd.read_parquet(ANA / "der_points.parquet")
der["date"] = pd.to_datetime(der["date"], errors="coerce")
der = der.dropna(subset=["date"])
wide = (der.assign(n=1).groupby([der.date.dt.normalize(), "era"])[["n", "kw_est"]]
        .sum().unstack(fill_value=0.0).sort_index().cumsum())
wide.columns = ["%s_%s" % ("sys" if a == "n" else "kw",
                           b.replace("/", "_")) for a, b in wide.columns]
wide = wide.reindex(pd.date_range(der.date.min().normalize(),
                                  pd.Timestamp(f"{Y1}-12-31"), freq="D")).ffill()
wide.index.name = "date"
wide = wide.reset_index()
wide.to_csv(OUTD / "der_installs_by_era.csv", index=False)

# ---------------------------------------------------------------- hourly panel
h = (pan.merge(rad, on=["date", "hour"], how="inner")
        .merge(daily, on="date", how="left")
        .merge(wide, on="date", how="left"))
h["day"] = h.date.dt.day
h["dow"] = h.date.dt.dayofweek
h["ym"] = h.year * 100 + h.month
h["season"] = h["quarter"]
h["is_weekend"] = (h.dow >= 5).astype(int)

# pre-dawn anchor. After the clock roll the battery-inert reference hour is 3.
for a in (3, 4):
    ref = (h[h.hour == a].set_index("date")["load_mw"]
           .rename("load_anchor%d" % a))
    h = h.merge(ref, on="date", how="left")
    h["load_anom%d" % a] = h["load_mw"] - h["load_anchor%d" % a]

h["ghi_x_pv"] = h.ghi * h.pv_mw_cum
h["middayghi_x_batt"] = h.ghi_midday * h.batt_mwh_cum
h["middayghi_x_pv"] = h.ghi_midday * h.pv_mw_cum
h["middayghi_x_sysBB"] = h.ghi_midday * h.get("sys_BatteryBonus", 0.0)

COLS = ["date", "year", "month", "day", "hour", "dow", "ym", "quarter", "season",
        "is_weekend", "load_mw", "load_anchor3", "load_anom3",
        "load_anchor4", "load_anom4", "ghi", "temp", "ghi_midday", "temp_midday",
        "temp_evening", "ghi_daily", "temp_daily", "pv_mw_cum", "batt_mwh_cum",
        "ghi_x_pv", "middayghi_x_batt", "middayghi_x_pv", "middayghi_x_sysBB",
        "era_714", "roll_h", "dt_hst"] + [c for c in wide.columns if c != "date"]
h = h[[c for c in COLS if c in h.columns]].sort_values(["date", "hour"])
h.to_parquet(OUTD / "oahu_hourly_panel.parquet", index=False)
h.to_csv(OUTD / "oahu_hourly_panel.csv", index=False)

# ---------------------------------------------------------------- daily panel
dly = (h.groupby("date")
       .agg(load_mean=("load_mw", "mean"), load_peak=("load_mw", "max"),
            load_min=("load_mw", "min"),
            load_midday=("load_mw", lambda s: s[h.loc[s.index, "hour"].between(10, 14)].mean()),
            load_evening=("load_mw", lambda s: s[h.loc[s.index, "hour"].between(19, 22)].mean()),
            ghi_midday=("ghi_midday", "first"), ghi_daily=("ghi_daily", "first"),
            temp_midday=("temp_midday", "first"), temp_evening=("temp_evening", "first"),
            pv_mw_cum=("pv_mw_cum", "first"), batt_mwh_cum=("batt_mwh_cum", "first"),
            year=("year", "first"), month=("month", "first"), dow=("dow", "first"),
            ym=("ym", "first"))
       .reset_index())
thr = dly.ghi_midday.quantile(0.20)
dly["lowsun"] = (dly.ghi_midday <= thr).astype(int)
dly["lowsun_threshold_wm2"] = thr
for c in ("sys_BatteryBonus", "kw_BatteryBonus", "sys_NEM_CGS", "kw_NEM_CGS",
          "sys_CSS_SmartExport", "kw_CSS_SmartExport", "sys_SmartDER", "kw_SmartDER"):
    if c in h.columns:
        dly = dly.merge(h.groupby("date")[c].first().reset_index(), on="date", how="left")
dly.to_parquet(OUTD / "oahu_daily_panel.parquet", index=False)
dly.to_csv(OUTD / "oahu_daily_panel.csv", index=False)

print("hourly %s rows x %d cols  (%d-%d)" % (f"{len(h):,}", h.shape[1], Y0, Y1))
print("daily  %s rows x %d cols" % (f"{len(dly):,}", dly.shape[1]))
print("low-sun threshold (20th pct midday GHI) = %.0f W/m2" % thr)
print("era columns:", [c for c in wide.columns if c != "date"])
print("DONE 20")
