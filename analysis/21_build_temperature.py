#!/usr/bin/env python3
"""21_build_temperature.py -- replace the NSRDB reanalysis temperature with a
station-based series, spatially weighted to where panels and buildings are.

Why: NSRDB air temperature over Oahu is a reanalysis field on a grid for which
the island is sub-grid. Its mean diurnal cycle spans 1.85 degC against 6-7 in
the station record, so it under-controls the air-conditioning confound that the
radiation design has to defeat.

Method (anomaly plus climatology, the standard downscaling form):

    T_target(t) = C_target(month, hour) + sum_s w_s * [ T_s(t) - C_s(month, hour) ]

  T_s        hourly observed temperature at ASOS station s (4 Oahu stations)
  C_s        that station's own climatological diurnal cycle, by month and hour
  C_target   the target location's climatological diurnal cycle, built from the
             HCDP 250 m monthly Tmax/Tmin grids for level and range, with the
             hour-shape borrowed from the weighted stations
  w_s        station weights, inverse-distance from the weighted target cells

Stations supply the temporal signal; the 250 m grid supplies the spatial level
and diurnal range. Three targets are produced:

  t_pv      weighted by installed PV kW          (what panels experience)
  t_bldg    weighted by system count             (proxy for where buildings are)
  t_phnl    Honolulu Airport alone               (the naive single-station choice)

Inputs : data/raw/asos/*.csv, data/raw/hcdp/ascii/, data/raw/der_points.parquet
Output : data/analysis/oahu_temperature_hourly.csv (+ parquet), weights report
"""
import glob
import os
import numpy as np
import pandas as pd
from pathlib import Path
from pyproj import Transformer

REPO = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("OAHU_ANA", REPO / "data" / "raw"))
OUTD = REPO / "data" / "analysis"
OUTD.mkdir(parents=True, exist_ok=True)
MON = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]
STA = {"PHNL": (21.3187, -157.9224), "PHJR": (21.3074, -158.0703),
       "PHNG": (21.4509, -157.7629), "PHHI": (21.4776, -158.0443)}
BOX = dict(la0=21.20, la1=21.75, lo0=-158.35, lo1=-157.60)

# ---------------------------------------------------------------- 1. stations
rows = []
for f in sorted(glob.glob(str(RAW / "asos" / "*.csv"))):
    d = pd.read_csv(f, na_values=["M", "T", ""])
    d = d.dropna(subset=["tmpf"])
    d["valid"] = pd.to_datetime(d["valid"])
    d["degC"] = (d["tmpf"] - 32.0) * 5.0 / 9.0
    d["date"] = d["valid"].dt.normalize()
    d["hour"] = d["valid"].dt.hour
    # several reports per hour (routine plus specials): take the hourly mean
    g = d.groupby(["station", "date", "hour"], as_index=False)["degC"].mean()
    rows.append(g)
obs = pd.concat(rows, ignore_index=True)
obs["month"] = obs["date"].dt.month
wide = obs.pivot_table(index=["date", "hour"], columns="station",
                       values="degC").reset_index()
print("station hours: " + ", ".join(
    "%s %d" % (s, int(wide[s].notna().sum())) for s in STA if s in wide))

# station climatology by month and hour
clim_s = {}
for s in STA:
    if s not in wide:
        continue
    t = wide[["date", "hour", s]].dropna().copy()
    t["month"] = t["date"].dt.month
    clim_s[s] = t.groupby(["month", "hour"])[s].mean()

# ---------------------------------------------------------------- 2. HCDP grid
def read_block(path):
    """Read only the Oahu window out of a statewide ESRI ASCII grid."""
    with open(path) as fh:
        hdr = {}
        for _ in range(6):
            k, v = fh.readline().split()
            hdr[k.lower()] = float(v)
        nc, nr = int(hdr["ncols"]), int(hdr["nrows"])
        cs, xll, yll = hdr["cellsize"], hdr["xllcorner"], hdr["yllcorner"]
        ymax = yll + nr * cs
        r0 = int((ymax - BOX["la1"]) / cs); r1 = int((ymax - BOX["la0"]) / cs)
        c0 = int((BOX["lo0"] - xll) / cs);  c1 = int((BOX["lo1"] - xll) / cs)
        out = []
        for i, line in enumerate(fh):
            if i < r0:
                continue
            if i > r1:
                break
            out.append(np.fromstring(line, sep=" ")[c0:c1 + 1])
        a = np.array(out)
        a[a == hdr["nodata_value"]] = np.nan
        lats = ymax - (np.arange(r0, r1 + 1) + 0.5) * cs
        lons = xll + (np.arange(c0, c1 + 1) + 0.5) * cs
        return a, lats, lons

TMAX, TMIN = {}, {}
for mi, mn in enumerate(MON, start=1):
    TMAX[mi], lats, lons = read_block(RAW / "hcdp" / "ascii" / "Tmax_month_ascii" / f"tmax{mn}_250m.txt")
    TMIN[mi], _, _ = read_block(RAW / "hcdp" / "ascii" / "Tmin_month_ascii" / f"tmin{mn}_250m.txt")
land = ~np.isnan(TMAX[1])
print("grid window %s, land cells %d (%.0f%% of window)"
      % (TMAX[1].shape, land.sum(), 100 * land.mean()))

# ---------------------------------------------------------------- 3. PV weights
der = pd.read_parquet(RAW / "der_points.parquet").dropna(subset=["x", "y"])
tr = Transformer.from_crs("EPSG:32604", "EPSG:4326", always_xy=True)
lo, la = tr.transform(der.x.values, der.y.values)
der = der.assign(lat=la, lon=lo)
der = der[(der.lat.between(BOX["la0"], BOX["la1"])) &
          (der.lon.between(BOX["lo0"], BOX["lo1"]))]
ri = np.abs(der.lat.values[:, None] - lats[None, :]).argmin(1)
ci = np.abs(der.lon.values[:, None] - lons[None, :]).argmin(1)
W = {}
W["pv"] = np.zeros_like(TMAX[1]); np.add.at(W["pv"], (ri, ci), der.kw_est.values)
W["bldg"] = np.zeros_like(TMAX[1]); np.add.at(W["bldg"], (ri, ci), 1.0)
for k in W:
    W[k] = np.where(land, W[k], 0.0)
    W[k] = W[k] / W[k].sum()
print("PV systems placed on the grid: %d (%.0f MW)" % (len(der), der.kw_est.sum() / 1000))

# ---------------------------------------------------------------- 4. targets
LA, LO = np.meshgrid(lats, lons, indexing="ij")
def station_weights(w):
    """Inverse-distance station weights for a weighted set of cells."""
    out = {}
    for s, (sla, slo) in STA.items():
        if s not in clim_s:
            continue
        dkm = np.sqrt(((LA - sla) * 111.0) ** 2
                      + ((LO - slo) * 111.0 * np.cos(np.radians(21.45))) ** 2)
        out[s] = float((w / np.maximum(dkm, 1.0) ** 2).sum())
    tot = sum(out.values())
    return {s: v / tot for s, v in out.items()}

targets = {"t_pv": station_weights(W["pv"]), "t_bldg": station_weights(W["bldg"]),
           "t_phnl": {"PHNL": 1.0}}
rep = ["station weights by target:"]
for t, w in targets.items():
    rep.append("  %-7s " % t + "  ".join("%s %.3f" % (s, v) for s, v in sorted(w.items())))

# Target climatology. The HCDP grid is used only for SPATIAL DIFFERENCES, never
# for absolute level: validated against the four stations, its Tmax agrees within
# 0.3 degC but its Tmin runs 0.9 to 3.3 degC too cold, worst at the coastal and
# windward sites, which would inflate the diurnal range. Differencing the target
# cells against the station cells under the same weights cancels a bias that is
# spatially smooth. Level and range are therefore anchored to observed station
# climatology, and the grid supplies only the offset from it.
def grid_at(wt):
    return {m: (float(np.nansum(wt * TMIN[m])), float(np.nansum(wt * TMAX[m])))
            for m in range(1, 13)}

st_cells = {}
for s, (sla, slo) in STA.items():
    if s in clim_s:
        st_cells[s] = (int(np.abs(lats - sla).argmin()), int(np.abs(lons - slo).argmin()))

DELTA = {}
for t, w in targets.items():
    if t == "t_phnl":
        DELTA[t] = {m: (0.0, 0.0) for m in range(1, 13)}
        continue
    wt = W["pv" if t == "t_pv" else "bldg"]
    gt = grid_at(wt)
    # same station weights, evaluated on the grid at the station cells
    gs = {}
    for m in range(1, 13):
        gn = sum(w[s] * TMIN[m][r, c] for s, (r, c) in st_cells.items())
        gx = sum(w[s] * TMAX[m][r, c] for s, (r, c) in st_cells.items())
        gs[m] = (float(gn), float(gx))
    DELTA[t] = {m: ((gt[m][0] + gt[m][1]) / 2 - (gs[m][0] + gs[m][1]) / 2,      # level
                    (gt[m][1] - gt[m][0]) - (gs[m][1] - gs[m][0]))              # range
               for m in range(1, 13)}
rep.append("\ngrid-derived spatial offsets vs the weighted stations (annual mean):")
for t in targets:
    dl = np.mean([DELTA[t][m][0] for m in range(1, 13)])
    dr = np.mean([DELTA[t][m][1] for m in range(1, 13)])
    rep.append("  %-7s level %+.2f degC   diurnal range %+.2f degC" % (t, dl, dr))

out = wide[["date", "hour"]].copy()
out["month"] = out["date"].dt.month
for t, w in targets.items():
    anom = np.zeros(len(out)); wsum = np.zeros(len(out))
    for s, ws in w.items():
        c = out.set_index(["month", "hour"]).index.map(clim_s[s])
        a = wide[s].values - np.asarray(c, dtype=float)
        ok = ~np.isnan(a)
        anom[ok] += ws * a[ok]; wsum[ok] += ws
    anom = np.where(wsum > 0, anom / np.maximum(wsum, 1e-9), np.nan)
    # Observed climatology of the weighted stations, then the grid's spatial
    # offset applied to its level and to its diurnal range.
    shp = sum(ws * clim_s[s] for s, ws in w.items())
    lo_ = shp.groupby("month").transform("min"); hi_ = shp.groupby("month").transform("max")
    unit = ((shp - lo_) / (hi_ - lo_) - 0.5).rename("u").reset_index()
    base = shp.rename("c").reset_index()
    mg = out.merge(unit, on=["month", "hour"], how="left").merge(
        base, on=["month", "hour"], how="left")
    dlev = out["month"].map({m: DELTA[t][m][0] for m in range(1, 13)}).values
    drng = out["month"].map({m: DELTA[t][m][1] for m in range(1, 13)}).values
    # the grid range is a spread of daily extremes; a mean-day cycle spans 0.845
    # of it (measured on the four stations), so the offset is scaled to match.
    out[t] = mg["c"].values + dlev + mg["u"].values * drng * 0.845 + anom

out = out.dropna(subset=list(targets)).sort_values(["date", "hour"])
out["date"] = out["date"].dt.date
out.to_csv(OUTD / "oahu_temperature_hourly.csv", index=False)
out.to_parquet(OUTD / "oahu_temperature_hourly.parquet", index=False)

rep.append("\ndiurnal amplitude of the mean day (degC):")
for t in targets:
    p = out.groupby("hour")[t].mean()
    rep.append("  %-7s %.2f   (mean level %.2f)" % (t, p.max() - p.min(), out[t].mean()))
rep.append("\nrows %d, %s to %s" % (len(out), out.date.min(), out.date.max()))
txt = "\n".join(rep)
open(OUTD / "temperature_weights_report.txt", "w").write(txt + "\n")
print(txt)
print("DONE 21")
