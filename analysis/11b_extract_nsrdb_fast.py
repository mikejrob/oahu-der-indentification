#!/usr/bin/env python3
"""
11b_extract_nsrdb_fast.py YEAR -- fast single-year Oahu NSRDB extract from NREL public S3.
Reads ONLY ghi + air_temperature (the two vars Tasks A/B need), for the Oahu bounding box,
so the byte-range transfer is half of 07/11. One year per invocation -> run several in parallel.

Writes per-year files (merged later by 11c):
  _nsrdb_isl_{YEAR}.parquet          island-mean hourly (year,month,day,hour,ghi,temp)
  _nsrdb_cellmid_{YEAR}.csv          per-cell midday GHI (cell_id,lat,lon,year,ghi_midday_mean)
Also writes nsrdb_oahu_cells.csv once (cell_id,lat,lon).
"""
import os
import sys, s3fs, h5py, numpy as np, pandas as pd
from pathlib import Path

Y = int(sys.argv[1])
ANA = Path(os.environ.get(
    "OAHU_ANA", str(Path(__file__).resolve().parent.parent / "data" / "raw")))
OUT = Path(os.environ.get(
    "OAHU_OUT", str(Path(__file__).resolve().parent.parent / "data" / "derived")))
OUT.mkdir(parents=True, exist_ok=True)
BUCKET = "nrel-pds-nsrdb/GOES/aggregated/v4.0.0"
BOX = dict(la0=21.2, la1=21.75, lo0=-158.35, lo1=-157.60)

fs = s3fs.S3FileSystem(anon=True)
key = f"{BUCKET}/nsrdb_{Y}.h5"
print(f"[{Y}] open {key}", flush=True)
with h5py.File(fs.open(key, "rb", cache_type="bytes", block_size=8*1024*1024), "r") as f:
    meta = f["meta"][:]
    lat, lon = meta["latitude"], meta["longitude"]
    m = (lat>=BOX["la0"])&(lat<=BOX["la1"])&(lon>=BOX["lo0"])&(lon<=BOX["lo1"])
    idx = np.where(m)[0]; i0, i1 = idx.min(), idx.max()+1
    loc = idx - i0
    cell_lat = lat[idx]; cell_lon = lon[idx]
    cf = ANA/"nsrdb_oahu_cells.csv"
    if not cf.exists():
        pd.DataFrame({"cell_id": np.arange(len(idx)), "lat": cell_lat,
                      "lon": cell_lon}).to_csv(cf, index=False)
    ti = pd.to_datetime([t.decode() for t in f["time_index"][:]], utc=True).tz_convert("Pacific/Honolulu")
    def rd(v):
        ds = f[v]; sf = ds.attrs.get("scale_factor", 1.0) or 1.0
        return ds[:, i0:i1].astype("float32")[:, loc] / sf
    print(f"[{Y}] reading ghi", flush=True); ghi = rd("ghi")
    print(f"[{Y}] reading temp", flush=True); temp = rd("air_temperature")

d = pd.DataFrame({"ghi": ghi.mean(1), "temp": temp.mean(1)})
d["year"], d["month"], d["day"], d["hour"] = ti.year, ti.month, ti.day, ti.hour
hourly = d.groupby(["year","month","day","hour"], as_index=False)[["ghi","temp"]].mean()
hourly.to_parquet(ANA/f"_nsrdb_isl_{Y}.parquet", index=False)

hh = ti.hour; midmask = (hh>=11)&(hh<=13)
cell_mid = np.nanmean(ghi[midmask,:], axis=0)
pd.DataFrame(dict(cell_id=np.arange(len(idx)), lat=cell_lat, lon=cell_lon,
                  year=Y, ghi_midday_mean=cell_mid)).to_csv(ANA/f"_nsrdb_cellmid_{Y}.csv", index=False)
print(f"[{Y}] DONE. {len(hourly)} hours, island mean GHI {hourly.ghi.mean():.0f}", flush=True)
