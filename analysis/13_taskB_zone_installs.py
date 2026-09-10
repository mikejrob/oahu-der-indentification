#!/usr/bin/env python3
"""
TASK B (part 1) -- installed distributed capacity BY ZONE over time + map DER points to
nearest NSRDB grid cells.

Uses switch-pg python (has pyproj) to convert der_points x/y (EPSG:26904, NAD83/UTM 4N)
to lat/lon, then nearest-NSRDB-cell assignment.

Outputs:
  der_zone_cumulative_by_year.csv   (year, zone, pv_mw_cum, batt_mwh_cum)
  der_points_latlon_cell.parquet    (date,year,zone,mw_inc,batt_inc,lat,lon,cell_id)
  taskB_zone_install_totals.txt      cross-check vs der_by_era.csv
"""
import os
import numpy as np, pandas as pd
from pathlib import Path
from pyproj import Transformer

ANA = Path(os.environ.get(
    "OAHU_ANA", str(Path(__file__).resolve().parent.parent / "data" / "raw")))
OUT = Path(os.environ.get(
    "OAHU_OUT", str(Path(__file__).resolve().parent.parent / "data" / "derived")))
OUT.mkdir(parents=True, exist_ok=True)
DER = os.path.join(OUT, "der_points.parquet")
ERA = os.path.join(OUT, "der_by_era.csv")

d = pd.read_parquet(DER)
d["date"] = pd.to_datetime(d["date"])
d["mw_inc"] = d["kw_est"] / 1000.0
d["batt_inc"] = d["batt_mwh"].fillna(0.0)

# UTM 4N (EPSG:26904) -> WGS84 lon/lat
tr = Transformer.from_crs(26904, 4326, always_xy=True)
lon, lat = tr.transform(d["x"].values, d["y"].values)
d["lon"] = lon; d["lat"] = lat

# nearest NSRDB cell
cells = pd.read_csv(ANA/"nsrdb_oahu_cells.csv")
cl_lat = cells["lat"].values; cl_lon = cells["lon"].values
# simple nearest by squared degrees (fine at this latitude/scale)
def nearest(la, lo):
    dd = (cl_lat - la)**2 + (cl_lon - lo)**2
    return int(np.argmin(dd))
d["cell_id"] = [nearest(la, lo) for la, lo in zip(d["lat"].values, d["lon"].values)]

d[["date","year","zone","mw_inc","batt_inc","lat","lon","cell_id"]].to_parquet(
    ANA/"der_points_latlon_cell.parquet", index=False)

# zonal cumulative by year
rows = []
for y in range(2006, 2025):
    sub = d[d["year"] <= y]
    g = sub.groupby("zone").agg(pv_mw_cum=("mw_inc","sum"),
                                batt_mwh_cum=("batt_inc","sum")).reset_index()
    g["year"] = y
    rows.append(g)
zt = pd.concat(rows, ignore_index=True)[["year","zone","pv_mw_cum","batt_mwh_cum"]]
zt.to_csv(ANA/"der_zone_cumulative_by_year.csv", index=False)

# cross-check totals vs der_by_era.csv
era = pd.read_csv(ERA)
out = []
out.append("TASK B zonal install cross-check")
out.append("der_points total: PV=%.1f MW, batt=%.1f MWh" % (d.mw_inc.sum(), d.batt_inc.sum()))
out.append("der_by_era total: PV=%.1f MW, batt=%.1f MWh" % (era.mw.sum(), era.batt_mwh.sum()))
out.append("  (small diff expected: der_points includes post-era-tally installs through 2025-06)")
out.append("\nfinal (2024) cumulative by zone:")
z24 = zt[zt.year==2024].sort_values("pv_mw_cum", ascending=False)
out.append(z24.round(1).to_string(index=False))
txt = "\n".join(out)
(ANA/"taskB_zone_install_totals.txt").write_text(txt + "\n")
print(txt)
print("\nDONE 13")
