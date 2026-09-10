#!/usr/bin/env python3
"""
11_extract_nsrdb_2013_2019.py -- extend NSRDB radiation coverage to 2013-2019 via the same
NREL public-S3 byte-range method as 07_extract_nsrdb_s3.py, giving a continuous 2013-2024
radiation panel synchronized to the 714 load.

Also saves, once, the Oahu NSRDB grid-cell lat/lon and a per-cell midday-GHI climatology
(needed for Task B install-capacity-weighted radiation). Per-cell full-year hourly is large,
so for Task B we save per-cell MIDDAY-mean GHI by year (enough to weight the fleet's effective CF).

Outputs:
  nsrdb_oahu_island_hourly_2013_2019.parquet   (year,month,day,hour,ghi,temp,dni,dhi) island mean
  nsrdb_oahu_cells.csv                          (cell_id, lat, lon) -- the 264 Oahu cells
  nsrdb_oahu_cell_midday_ghi_by_year.csv        (cell_id, lat, lon, year, ghi_midday_mean)
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
YEARS = [2013, 2014, 2015, 2016, 2017, 2018, 2019]
VARS = ["ghi", "air_temperature", "dni", "dhi"]
BOX = dict(la0=21.2, la1=21.75, lo0=-158.35, lo1=-157.60)

fs = s3fs.S3FileSystem(anon=True)
frames = []
cell_year_rows = []
cells_saved = False
for Y in YEARS:
    key = f"{BUCKET}/nsrdb_{Y}.h5"
    print(f"[{Y}] opening {key} ...", flush=True)
    with h5py.File(fs.open(key, "rb", cache_type="bytes", block_size=16*1024*1024), "r") as f:
        meta = f["meta"][:]
        lat, lon = meta["latitude"], meta["longitude"]
        m = (lat>=BOX["la0"])&(lat<=BOX["la1"])&(lon>=BOX["lo0"])&(lon<=BOX["lo1"])
        idx = np.where(m)[0]; i0, i1 = idx.min(), idx.max()+1
        loc = idx - i0
        cell_lat = lat[idx]; cell_lon = lon[idx]
        if not cells_saved:
            pd.DataFrame({"cell_id": np.arange(len(idx)), "lat": cell_lat,
                          "lon": cell_lon}).to_csv(ANA/"nsrdb_oahu_cells.csv", index=False)
            cells_saved = True
            print(f"  saved {len(idx)} Oahu cells", flush=True)
        ti = pd.to_datetime([t.decode() for t in f["time_index"][:]], utc=True)
        ti_hst = ti.tz_convert("Pacific/Honolulu")
        cols = {}
        ghi_block = None
        for v in VARS:
            ds = f[v]; sf = ds.attrs.get("scale_factor", 1.0) or 1.0
            block = ds[:, i0:i1].astype("float32")
            per_cell = block[:, loc] / sf                  # (time, ncell)
            cols[v] = per_cell.mean(axis=1)                # island mean
            if v == "ghi":
                ghi_block = per_cell
            print(f"  [{Y}] {v}: island mean {np.nanmean(cols[v]):.1f}", flush=True)
        # per-cell midday GHI climatology (11-13h HST) for Task B
        hh = ti_hst.hour
        midmask = (hh >= 11) & (hh <= 13)
        cell_mid = np.nanmean(ghi_block[midmask, :], axis=0)   # (ncell,)
        for c in range(len(idx)):
            cell_year_rows.append(dict(cell_id=c, lat=float(cell_lat[c]),
                                       lon=float(cell_lon[c]), year=Y,
                                       ghi_midday_mean=float(cell_mid[c])))
    d = pd.DataFrame(cols)
    d["year"], d["month"], d["day"], d["hour"] = ti_hst.year, ti_hst.month, ti_hst.day, ti_hst.hour
    hourly = d.groupby(["year","month","day","hour"], as_index=False)[VARS].mean()
    hourly = hourly.rename(columns={"air_temperature":"temp"})
    frames.append(hourly)
    print(f"[{Y}] {len(hourly)} clock-hours", flush=True)

isl = pd.concat(frames, ignore_index=True)
isl.to_parquet(ANA/"nsrdb_oahu_island_hourly_2013_2019.parquet", index=False)
pd.DataFrame(cell_year_rows).to_csv(ANA/"nsrdb_oahu_cell_midday_ghi_by_year.csv", index=False)
print(f"\nDONE. {len(isl)} island-hourly rows {YEARS[0]}-{YEARS[-1]}; "
      f"per-cell midday climatology for {len(cell_year_rows)} cell-years.")
