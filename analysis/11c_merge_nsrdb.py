#!/usr/bin/env python3
"""11c_merge_nsrdb.py -- merge per-year _nsrdb_isl_*.parquet and _nsrdb_cellmid_*.csv into the
continuous panels the downstream scripts read.

Writes:
  nsrdb_oahu_island_hourly_2013_2019.parquet   (island hourly, 2013-2019; consumed by 14 Task A)
  nsrdb_oahu_cell_midday_ghi_by_year.csv        (per-cell midday GHI, all years 2013-2024; Task B)
Leaves nsrdb_oahu_island_hourly_2020_2024.parquet (from 07) as-is.
"""
import os
import glob, os, pandas as pd
ANA = os.environ.get(
    "OAHU_ANA",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "raw"))
OUT = os.environ.get(
    "OAHU_OUT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "derived"))
os.makedirs(OUT, exist_ok=True)

# island hourly 2013-2019 (from 11b fast pulls)
isl = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(os.path.join(ANA,"_nsrdb_isl_*.parquet")))],
                ignore_index=True)
isl1319 = isl[isl.year.between(2013,2019)].drop_duplicates(["year","month","day","hour"])
isl1319.to_parquet(os.path.join(ANA,"nsrdb_oahu_island_hourly_2013_2019.parquet"), index=False)
print("island 2013-2019:", sorted(isl1319.year.unique()), len(isl1319), "rows")

# per-cell midday GHI all years
cm = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(os.path.join(ANA,"_nsrdb_cellmid_*.csv")))],
               ignore_index=True).drop_duplicates(["cell_id","year"])
cm.to_csv(os.path.join(ANA,"nsrdb_oahu_cell_midday_ghi_by_year.csv"), index=False)
print("cell midday years:", sorted(cm.year.unique()), len(cm), "cell-year rows")
print("DONE 11c")
