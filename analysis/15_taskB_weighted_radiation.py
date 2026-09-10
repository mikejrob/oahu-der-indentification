#!/usr/bin/env python3
"""
TASK B (part 2) -- install-capacity-weighted island radiation vs uniform mean, and vs the
model's DistPV capacity factors.

Uses per-cell midday-GHI climatology (nsrdb_oahu_cell_midday_ghi_by_year.csv, 2013-2024) and the
DER points mapped to cells (der_points_latlon_cell.parquet). For each year:
  - uniform island radiation = simple mean midday GHI over all Oahu cells
  - install-weighted radiation = cumulative-installed-MW-weighted mean midday GHI over cells
    (weight each cell by the cumulative PV MW installed in that cell up to that year)
Ratio weighted/uniform => whether the fleet sits in sunnier/cloudier-than-average locations, and
whether that materially changes the effective DistPV CF the model uses (0.182 annual mean).

Outputs: taskB_weighted_vs_uniform_radiation.csv, fig_taskB_weighted_radiation.png,
         fig_taskB_zone_installs.png, TASK_B_NOTES.md (numbers filled by 16_notes if needed)
"""
import os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ANA = os.environ.get(
    "OAHU_ANA",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "raw"))
OUT = os.environ.get(
    "OAHU_OUT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "derived"))
os.makedirs(OUT, exist_ok=True)
MODEL_DISTPV_CF = 0.1822   # annual mean of DistPV rows in variable_capacity_factors.csv

cellghi = pd.read_csv(os.path.join(OUT, "nsrdb_oahu_cell_midday_ghi_by_year.csv"))
der = pd.read_parquet(os.path.join(OUT, "der_points_latlon_cell.parquet"))
YEARS = sorted(cellghi.year.unique())

# cumulative installed MW by cell x year
rows = []
for y in YEARS:
    sub = der[der.year <= y]
    cellmw = sub.groupby("cell_id")["mw_inc"].sum()
    cg = cellghi[cellghi.year == y].set_index("cell_id")["ghi_midday_mean"]
    common = cg.index
    uniform = cg.mean()
    w = cellmw.reindex(common).fillna(0.0)
    weighted = (cg * w).sum() / w.sum() if w.sum() > 0 else np.nan
    rows.append(dict(year=int(y), uniform_ghi=float(uniform),
                     weighted_ghi=float(weighted),
                     ratio=float(weighted/uniform) if uniform else np.nan,
                     installed_mw=float(w.sum())))
wr = pd.DataFrame(rows)
# implied CF adjustment: scale the model DistPV CF by the weighted/uniform ratio
wr["implied_distpv_cf"] = MODEL_DISTPV_CF * wr["ratio"]
wr["cf_delta_pct"] = 100 * (wr["ratio"] - 1)
wr.to_csv(os.path.join(OUT, "taskB_weighted_vs_uniform_radiation.csv"), index=False)
print(wr.round(4).to_string(index=False))

# ---- figures
fig, ax = plt.subplots(1, 2, figsize=(13, 5))
ax[0].plot(wr.year, wr.uniform_ghi, "o-", label="island-uniform mean", color="tab:gray")
ax[0].plot(wr.year, wr.weighted_ghi, "s-", label="install-capacity-weighted", color="tab:red")
ax[0].set_xlabel("year"); ax[0].set_ylabel("midday GHI (W/m2, 11-13h)")
ax[0].set_title("Install-weighted vs uniform Oahu radiation")
ax[0].legend(fontsize=9); ax[0].grid(alpha=0.3)
ax2 = ax[0].twinx()
ax2.plot(wr.year, wr.cf_delta_pct, "k--", alpha=0.5)
ax2.set_ylabel("weighted/uniform - 1 (%)")

# zone installs over time
zt = pd.read_csv(os.path.join(OUT, "der_zone_cumulative_by_year.csv"))
for z in zt.zone.unique():
    s = zt[zt.zone == z]
    ax[1].plot(s.year, s.pv_mw_cum, label=z, lw=1.8)
ax[1].set_xlabel("year"); ax[1].set_ylabel("cumulative installed PV (MW)")
ax[1].set_title("Distributed PV by zone over time")
ax[1].legend(fontsize=7); ax[1].grid(alpha=0.3); ax[1].set_xlim(2008, 2024)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig_taskB_weighted_radiation.png"), dpi=130)
print("wrote fig_taskB_weighted_radiation.png")

# summary text
last = wr.iloc[-1]
print("\n2024: weighted/uniform ratio = %.4f (%.2f%%); implied DistPV CF = %.4f vs model %.4f"
      % (last.ratio, last.cf_delta_pct, last.implied_distpv_cf, MODEL_DISTPV_CF))
verdict = ("MATERIAL" if abs(last.cf_delta_pct) > 2 else "immaterial")
print("verdict: zone-weighting is %s for the DistPV CF (threshold ~2%%)." % verdict)
print("DONE 15")
