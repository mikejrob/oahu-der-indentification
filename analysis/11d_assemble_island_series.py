#!/usr/bin/env python3
"""11d_assemble_island_series.py -- build the three canonical island-hourly
radiation files the estimators read, from the per-year parts written by 11b.

11c produces the 2013-2019 file and the per-cell midday climatology. The other
two names are historical: 03_load_nsrdb.py originally wrote 2018/2019 from an
on-disk CSV pull, and 07_extract_nsrdb_s3.py wrote 2020-2024 from S3. Both are
reproduced here from the same 11b parts so a clean checkout needs neither the
HPC CSVs nor a separate S3 pass.

Writes to data/raw:
  nsrdb_oahu_island_hourly.parquet             (2018-2019; read by 09)
  nsrdb_oahu_island_hourly_2020_2024.parquet   (read by 08 validation and 09)
  nsrdb_oahu_island_hourly_2013_2019.parquet   (read by 18; also written by 11c)
"""
import glob
import os
import sys
import pandas as pd
from pathlib import Path

ANA = Path(os.environ.get(
    "OAHU_ANA", str(Path(__file__).resolve().parent.parent / "data" / "raw")))

parts = sorted(glob.glob(str(ANA / "_nsrdb_isl_*.parquet")))
if not parts:
    sys.exit("no _nsrdb_isl_*.parquet parts in %s — run 11b first" % ANA)
isl = pd.concat([pd.read_parquet(f) for f in parts], ignore_index=True)
isl = isl.drop_duplicates(["year", "month", "day", "hour"]).sort_values(
    ["year", "month", "day", "hour"]).reset_index(drop=True)

# 09 reads dni/dhi off the 2018/19 file; 11b pulls only ghi+temp to halve the
# transfer, so fill the two unused columns rather than re-reading the bucket.
for c in ("dni", "dhi"):
    if c not in isl.columns:
        isl[c] = pd.NA

SPANS = {
    "nsrdb_oahu_island_hourly.parquet": (2018, 2019),
    "nsrdb_oahu_island_hourly_2020_2024.parquet": (2020, 2024),
    "nsrdb_oahu_island_hourly_2013_2019.parquet": (2013, 2019),
}
print("years present: %s" % sorted(isl.year.unique().tolist()))
for name, (y0, y1) in SPANS.items():
    sub = isl[isl.year.between(y0, y1)].copy()
    if sub.empty:
        print("  SKIP %-46s no years in %d-%d" % (name, y0, y1))
        continue
    sub.to_parquet(ANA / name, index=False)
    print("  %-46s %d rows, %d-%d" % (name, len(sub), y0, y1))
print("DONE 11d")
