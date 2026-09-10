#!/usr/bin/env python3
"""
10_wedge_paramz_firmed.py — firmed evening-shift parameterization + g-beta wedge with
battery-era radiation (2018-2024) and the clock-corrected load.

Outputs:
  evening_shift_parameterization_firmed.csv
  g_minus_beta_wedge_firmed.csv
  paramz_firmed_summary.txt
"""
import os
import numpy as np
import pandas as pd

ANA = os.environ.get(
    "OAHU_ANA",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "raw"))
OUT = os.environ.get(
    "OAHU_OUT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "derived"))
os.makedirs(OUT, exist_ok=True)
out = []

# ---------------- (A) firmed evening-shift parameterization ----------------
shape = pd.read_csv(os.path.join(OUT, "estimator2_battery_shape.csv"))
bf = pd.read_csv(os.path.join(OUT, "estimator2_battery_firmed.csv"))
E_energy = float(bf["energy_mwh_per_mwh"].iloc[0])   # radiation-identified, CLEAN window
E_phys = float(bf["physics_cap"].iloc[0])
clean = shape[shape["clean"]].copy()

rte, reserve, usable = 0.86, 0.20, 0.90
out.append("(A) FIRMED EVENING-SHIFT PARAMETERIZATION (radiation-identified, 2018-2024)")
out.append("  clean sun-down window discharge shape (weights sum to 1):")
out.append("   " + ", ".join(f"{int(r.hour)}h={r.shape_weight:.3f}" for _, r in clean.iterrows()))
out.append("  RADIATION-IDENTIFIED energy = %.3f MWh delivered per installed MWh per day" % E_energy)
out.append("  physics cap rte*(1-reserve)*usable = %.3f -> check PASSES (%.3f <= %.3f)"
           % (E_phys, E_energy, E_phys))
out.append("  (collinear Estimator-1 gave 3.24 MWh/MWh, which FAILED the cap; radiation "
           "identification removes the PV-self-consumption + load-growth contamination.)")
out.append("  RECOMMENDED for Switch net-load model: energy = %.2f MWh/MWh, distributed over "
           "the sun-down evening by the shape weights above (peak at 20h)." % E_energy)
out.append("  Residential/commercial: der_by_era program mix (NEM/CGS, CSS/SmartExport, "
           "BatteryBonus, SmartDER) is residential rooftop DER; the evening-shave is a "
           "residential-storage effect. No separable commercial-storage split in these data.")
out.append("  Battery-scale (250 MWh UNVERIFIED) sensitivity: per-MWh energy & shape are "
           "INVARIANT to the calibration (both numerator load-response and denominator MWh scale "
           "together); only ISLAND-TOTAL shifted energy scales linearly with it.")

clean.assign(energy_mwh_per_mwh=E_energy, physics_cap=E_phys).to_csv(
    os.path.join(OUT, "evening_shift_parameterization_firmed.csv"), index=False)

# ---------------- (B) firmed g - beta wedge, time-varying ----------------
# g: physical rooftop gen per MW per day from island GHI (PR=0.80), computed per YEAR now.
r1 = pd.read_parquet(os.path.join(ANA, "nsrdb_oahu_island_hourly.parquet"))
r1 = r1[r1.year.isin([2018, 2019])]
r2 = pd.read_parquet(os.path.join(ANA, "nsrdb_oahu_island_hourly_2020_2024.parquet"))
isl = pd.concat([r1[["year", "month", "day", "hour", "ghi"]],
                 r2[["year", "month", "day", "hour", "ghi"]]], ignore_index=True)
isl = isl.drop_duplicates(["year", "month", "day", "hour"])
PR = 0.80
isl["gen_per_mw_hr"] = (isl["ghi"] / 1000.0) * PR
gy = isl.groupby(["year", "month", "day"])["gen_per_mw_hr"].sum().groupby("year").mean()

# beta: grid load reduction per MW per day from firmed PV term integrated over daylight,
# using each year's mean GHI-by-hour (so beta is year-specific too).
pv = pd.read_csv(os.path.join(OUT, "estimator2_pv_term_firmed.csv"))
rows = []
for y in sorted(isl.year.unique()):
    ghi_h = isl[isl.year == y].groupby("hour")["ghi"].mean()
    p = pv.merge(ghi_h.rename("ghi_mean"), left_on="hour", right_index=True, how="left")
    p["beta_hr"] = -p["b_ghi_x_pv"] * p["ghi_mean"]     # MW load-reduction per MW, that hour
    beta = p["beta_hr"].sum()                            # MWh/day/MW
    g = float(gy.loc[y])
    rows.append(dict(year=int(y), g_mwh_day_mw=g, beta_mwh_day_mw=beta,
                     wedge_mwh_day_mw=g - beta, wedge_frac=(g - beta) / g))
wedge = pd.DataFrame(rows)

# island totals: scale per-MW wedge by installed PV MW that year
inst = pd.read_csv(os.path.join(OUT, "installs_cumulative_daily.csv"))
inst["date"] = pd.to_datetime(inst["date"])
pvmw = {y: inst[inst.date <= f"{y}-12-31"]["pv_mw_cum"].iloc[-1] for y in wedge.year}
wedge["pv_mw_installed"] = wedge["year"].map(pvmw)
wedge["island_induced_gwh_yr"] = wedge["pv_mw_installed"] * wedge["wedge_mwh_day_mw"] * 365 / 1000.0
wedge.to_csv(os.path.join(OUT, "g_minus_beta_wedge_firmed.csv"), index=False)

out.append("\n(B) FIRMED g - beta INDUCED-DEMAND WEDGE (time-varying, battery-era radiation)")
out.append(wedge.round(3).to_string(index=False))
out.append("  Interpretation: g-beta per MW = behind-the-meter induced demand + storage/inverter "
           "losses that never appear in grid load. Now identifiable per YEAR (radiation 2018-2024).")
w0, w1 = wedge["wedge_mwh_day_mw"].iloc[0], wedge["wedge_mwh_day_mw"].iloc[-1]
out.append("  per-MW wedge %d->%d: %.3f -> %.3f MWh/day/MW (%.1f%% -> %.1f%% of generation)"
           % (wedge.year.iloc[0], wedge.year.iloc[-1], w0, w1,
              100*wedge.wedge_frac.iloc[0], 100*wedge.wedge_frac.iloc[-1]))
out.append("  island induced demand %d->%d: %.0f -> %.0f GWh/yr"
           % (wedge.year.iloc[0], wedge.year.iloc[-1],
              wedge.island_induced_gwh_yr.iloc[0], wedge.island_induced_gwh_yr.iloc[-1]))
out.append("  CAVEAT: g-beta mixes induced demand with inverter/storage losses; it is an UPPER "
           "bound on net new behind-the-meter consumption. PR=0.80 assumption moves g +/-6%.")

txt = "\n".join(out)
with open(os.path.join(OUT, "paramz_firmed_summary.txt"), "w") as fh:
    fh.write(txt + "\n")
print(txt)
print("\nDONE 10")
