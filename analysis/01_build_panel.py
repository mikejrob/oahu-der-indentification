#!/usr/bin/env python3
"""
01_build_panel.py
Build the (quarter x hour-of-day) load panel for HECO-Oahu from FERC 714 hourly
demand + cumulative distributed PV / battery installs (oahu-grid der_points).

Outputs (all to analysis/ dir):
  - load_hourly_oahu.parquet         : cleaned hourly load, HST-local, with hour/season/date
  - installs_cumulative_daily.csv    : cumulative PV MW and battery MWh by date
  - panel_hourly_with_installs.parquet: hourly load joined to cumulative installs
  - panel_qtr_hour_anchored.csv      : (year,quarter,hour) cell means, 4am-anchored per (year,day)

Design notes:
  - FERC 714 respondent_id_ferc714_csv == 178 is the ONLY Hawaii (Pacific/Honolulu)
    respondent, and it is Oahu ALONE. Maui Electric and Hawaii Electric Light fall
    under the Form 714 reporting threshold (peak demand below 200 MW), so neither
    files and neither is folded into 178. The load series and the Oahu install
    series therefore cover the same territory. One consequence: no separate
    Maui / Hawaii Island respondent exists in this parquet, so a cross-island
    placebo is BLOCKED (documented in methods notes).
  - datetime_utc is tz-naive UTC -> localize UTC -> convert Pacific/Honolulu.
  - der_points.kw_est is per-system kW; cumulative sum /1000 -> installed MW.
  - 4am anchor: within each (year, calendar day) subtract that day's 4am HST load
    from every hour, removing the slow secular level trend and day-type effects so
    the hour-of-day SHAPE is what's modeled.
"""
import os
import numpy as np
import pandas as pd

# Paths overridable by env (audit finding 6: PUDL previously pointed at a
# purgeable session temp dir, since purged). Re-pulled 2026-09-06 to durable
# scratch (sha256 8fa79daa...); fresh annual aggregates match the vendored
# 2026-07-24 pull in sources/ferc714/ to <0.05 MW — the nightly build is
# stable for respondent 178. Full table, not a pre-sliced file: the
# respondent filter below does the slicing.
ANA = os.environ.get("OAHU_ANA", os.path.dirname(os.path.abspath(__file__)))
PUDL = os.environ.get(
    "OAHU_PUDL_714",
    os.path.join(OUT, "out_ferc714__hourly_planning_area_demand.parquet"))
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DER = os.environ.get(
    "OAHU_DER_POINTS",
    os.path.join(_REPO, "sources", "der", "der_points.parquet"))
os.makedirs(ANA, exist_ok=True)

# ---------------------------------------------------------------- load 714
d = pd.read_parquet(PUDL, columns=[
    "respondent_id_ferc714_csv", "datetime_utc",
    "demand_imputed_pudl_mwh", "demand_imputed_pudl_mwh_imputation_code"])
d = d[d["respondent_id_ferc714_csv"] == 178].copy()
d["dt_utc"] = pd.to_datetime(d["datetime_utc"]).dt.tz_localize("UTC")
d["dt_hst"] = d["dt_utc"].dt.tz_convert("Pacific/Honolulu")
d = d.dropna(subset=["demand_imputed_pudl_mwh"]).sort_values("dt_hst")
d = d.rename(columns={"demand_imputed_pudl_mwh": "load_mw"})
d["load_mw"] = d["load_mw"].astype(float)

d["date"] = d["dt_hst"].dt.date
d["year"] = d["dt_hst"].dt.year
d["month"] = d["dt_hst"].dt.month
d["hour"] = d["dt_hst"].dt.hour
d["quarter"] = d["dt_hst"].dt.quarter
# format-break flag: FERC switched CSV->XBRL for report years >=2021
d["era_714"] = np.where(d["year"] >= 2021, "XBRL", "CSV")

# drop obviously bad rows (nonpositive load)
d = d[d["load_mw"] > 0]
d[["dt_hst", "date", "year", "month", "hour", "quarter", "load_mw", "era_714",
   "demand_imputed_pudl_mwh_imputation_code"]].to_parquet(
    os.path.join(OUT, "load_hourly_oahu.parquet"), index=False)
print("load_hourly_oahu.parquet:", len(d), "rows,",
      d["year"].min(), "-", d["year"].max())

# ---------------------------------------------------------------- installs
der = pd.read_parquet(DER)
der["date"] = pd.to_datetime(der["date"])
der = der.sort_values("date")
der["mw_inc"] = der["kw_est"] / 1000.0          # per-system kW -> MW
der["batt_inc"] = der["batt_mwh"].fillna(0.0)
daily = der.groupby(der["date"].dt.date).agg(
    mw_inc=("mw_inc", "sum"), batt_inc=("batt_inc", "sum")).reset_index()
daily.columns = ["date", "mw_inc", "batt_inc"]
daily = daily.sort_values("date")
daily["pv_mw_cum"] = daily["mw_inc"].cumsum()
daily["batt_mwh_cum"] = daily["batt_inc"].cumsum()
daily.to_csv(os.path.join(OUT, "installs_cumulative_daily.csv"), index=False)
print("installs: final cumulative PV MW = %.1f, batt MWh = %.1f (as of %s)" % (
    daily["pv_mw_cum"].iloc[-1], daily["batt_mwh_cum"].iloc[-1],
    daily["date"].iloc[-1]))

# ---------------------------------------------------------------- join installs to hourly (as-of by date)
inst = daily[["date", "pv_mw_cum", "batt_mwh_cum"]].copy()
inst["date"] = pd.to_datetime(inst["date"])
dd = d.copy()
dd["date_dt"] = pd.to_datetime(dd["date"])
dd = pd.merge_asof(dd.sort_values("date_dt"), inst.sort_values("date"),
                   left_on="date_dt", right_on="date", direction="backward")
dd["pv_mw_cum"] = dd["pv_mw_cum"].fillna(0.0)
dd["batt_mwh_cum"] = dd["batt_mwh_cum"].fillna(0.0)
dd = dd.drop(columns=["date_y"]).rename(columns={"date_x": "date"})
dd.to_parquet(os.path.join(OUT, "panel_hourly_with_installs.parquet"), index=False)
print("panel_hourly_with_installs.parquet:", len(dd), "rows")

# ---------------------------------------------------------------- 4am anchor
# subtract each (year, day) 4am load from every hour of that day
anchor = dd[dd["hour"] == 4][["date", "load_mw"]].rename(
    columns={"load_mw": "load_4am"})
dd2 = dd.merge(anchor, on="date", how="left")
dd2 = dd2.dropna(subset=["load_4am"])
dd2["load_anom"] = dd2["load_mw"] - dd2["load_4am"]

# (year, quarter, hour) cell means of the anchored anomaly + raw + installs
cell = dd2.groupby(["year", "quarter", "hour"]).agg(
    load_anom=("load_anom", "mean"),
    load_mw=("load_mw", "mean"),
    pv_mw_cum=("pv_mw_cum", "mean"),
    batt_mwh_cum=("batt_mwh_cum", "mean"),
    n=("load_mw", "size")).reset_index()
cell.to_csv(os.path.join(OUT, "panel_qtr_hour_anchored.csv"), index=False)
print("panel_qtr_hour_anchored.csv:", len(cell), "cells")
print("DONE 01")
