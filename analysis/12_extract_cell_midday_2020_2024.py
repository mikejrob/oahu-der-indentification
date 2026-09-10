#!/usr/bin/env python3
"""
12_extract_cell_midday_2020_2024.py -- per-cell midday-GHI climatology (11-13h HST) for
2020-2024, appended to nsrdb_oahu_cell_midday_ghi_by_year.csv (which 11_ started for 2013-2019),
so Task B install-weighting spans the full battery era.
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
BOX = dict(la0=21.2, la1=21.75, lo0=-158.35, lo1=-157.60)

fs = s3fs.S3FileSystem(anon=True)
rows = []
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
        ti = pd.to_datetime([t.decode() for t in f["time_index"][:]], utc=True)
        hh = ti.tz_convert("Pacific/Honolulu").hour
        ds = f["ghi"]; sf = ds.attrs.get("scale_factor", 1.0) or 1.0
        per_cell = ds[:, i0:i1].astype("float32")[:, loc] / sf
        midmask = (hh >= 11) & (hh <= 13)
        cell_mid = np.nanmean(per_cell[midmask, :], axis=0)
        for c in range(len(idx)):
            rows.append(dict(cell_id=c, lat=float(cell_lat[c]), lon=float(cell_lon[c]),
                             year=Y, ghi_midday_mean=float(cell_mid[c])))
    print(f"[{Y}] done", flush=True)

new = pd.DataFrame(rows)
fp = ANA/"nsrdb_oahu_cell_midday_ghi_by_year.csv"
if fp.exists():
    old = pd.read_csv(fp)
    out = pd.concat([old, new], ignore_index=True).drop_duplicates(["cell_id", "year"])
else:
    out = new
out.to_csv(fp, index=False)
print(f"DONE. cell-year rows now {len(out)}, years {sorted(out.year.unique())}")
