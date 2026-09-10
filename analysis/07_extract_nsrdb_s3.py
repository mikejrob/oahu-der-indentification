#!/usr/bin/env python3
"""07_extract_nsrdb_s3.py -- pull Oahu hourly NSRDB radiation/weather for the
battery-era years (2020-2024) DIRECTLY from the NREL public S3 bucket.

Koa compute/login nodes cannot reach developer.nrel.gov (the API), but the NREL
Open-Data S3 bucket IS reachable, so we read the national GOES-aggregated v4.0.0
HDF5 files over S3 with byte-range reads and extract only the 264 Oahu grid
cells -- no API key, no login node, no full-file download.

Output (matches 03_load_nsrdb.py schema, extended to 2020-2024):
  analysis/nsrdb_oahu_island_hourly_2020_2024.parquet  (year,month,day,hour,ghi,temp,dni,dhi)
  analysis/nsrdb_oahu_daily_midday_2020_2024.csv        (date, ghi_midday, temp_midday, temp_evening)
Island mean over Oahu cells, half-hourly averaged to clock-hour, UTC -> HST.
"""
import os
import s3fs, h5py, numpy as np, pandas as pd
from pathlib import Path

ANA = Path(os.environ.get(
    "OAHU_ANA", str(Path(__file__).resolve().parent.parent / "data" / "raw")))
OUT = Path(os.environ.get(
    "OAHU_OUT", str(Path(__file__).resolve().parent.parent / "data" / "derived")))
OUT.mkdir(parents=True, exist_ok=True)
BUCKET = "nrel-pds-nsrdb/GOES/aggregated/v4.0.0"
YEARS = [2020, 2021, 2022, 2023, 2024]
VARS = ["ghi", "air_temperature", "dni", "dhi"]
BOX = dict(la0=21.2, la1=21.75, lo0=-158.35, lo1=-157.60)

fs = s3fs.S3FileSystem(anon=True)
frames = []
for Y in YEARS:
    key = f"{BUCKET}/nsrdb_{Y}.h5"
    print(f"[{Y}] opening {key} ...", flush=True)
    with h5py.File(fs.open(key, "rb", cache_type="bytes", block_size=16*1024*1024), "r") as f:
        meta = f["meta"][:]
        lat, lon = meta["latitude"], meta["longitude"]
        m = (lat>=BOX["la0"])&(lat<=BOX["la1"])&(lon>=BOX["lo0"])&(lon<=BOX["lo1"])
        idx = np.where(m)[0]; i0, i1 = idx.min(), idx.max()+1
        loc = idx - i0
        ti = pd.to_datetime([t.decode() for t in f["time_index"][:]], utc=True)
        ti_hst = ti.tz_convert("Pacific/Honolulu")
        cols = {}
        for v in VARS:
            ds = f[v]; sf = ds.attrs.get("scale_factor", 1.0) or 1.0
            block = ds[:, i0:i1].astype("float32")          # contiguous slice
            cols[v] = (block[:, loc] / sf).mean(axis=1)      # island mean over Oahu cells
            print(f"  [{Y}] {v}: island mean {np.nanmean(cols[v]):.1f}", flush=True)
    d = pd.DataFrame(cols)
    d["dt"] = ti_hst
    d["year"], d["month"], d["day"], d["hour"] = ti_hst.year, ti_hst.month, ti_hst.day, ti_hst.hour
    # half-hourly -> clock-hour mean (HST)
    hourly = d.groupby(["year","month","day","hour"], as_index=False)[VARS].mean()
    hourly = hourly.rename(columns={"air_temperature":"temp"})
    frames.append(hourly)
    print(f"[{Y}] {len(hourly)} clock-hours", flush=True)

isl = pd.concat(frames, ignore_index=True)
isl.to_parquet(ANA/"nsrdb_oahu_island_hourly_2020_2024.parquet", index=False)

# daily midday/evening summaries (match 03 schema)
isl["date"] = pd.to_datetime(isl[["year","month","day"]])
midday = isl[isl.hour.between(11,13)].groupby("date").agg(
    ghi_midday=("ghi","mean"), temp_midday=("temp","mean")).reset_index()
evening = isl[isl.hour.between(18,21)].groupby("date").agg(
    temp_evening=("temp","mean")).reset_index()
daily = midday.merge(evening, on="date", how="left")
daily.to_csv(ANA/"nsrdb_oahu_daily_midday_2020_2024.csv", index=False)
print(f"\nDONE. {len(isl)} hourly rows {YEARS[0]}-{YEARS[-1]}; {len(daily)} days.")
print("wrote nsrdb_oahu_island_hourly_2020_2024.parquet + nsrdb_oahu_daily_midday_2020_2024.csv")