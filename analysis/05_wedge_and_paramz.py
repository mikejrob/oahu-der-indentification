#!/usr/bin/env python3
"""
05_wedge_and_paramz.py
 (A) Evening battery load-shift parameterization for the Switch net-load model.
 (B) The g - beta induced-demand wedge (behind-the-meter true-demand growth).

(A) EVENING-SHIFT PARAMETERIZATION
  SHAPE: from Estimator-1 battery coefficients in the clean evening window (16-21h), which
  the prior work found well-identified. We take the NEGATIVE (discharge = load reduction)
  part, normalize to weights summing to 1 -> discharge shape by hour.
  TOTAL shifted energy per installed MWh: bounded by physics, NOT by the collinear coef.
    E_shift/MWh = round_trip_eff * (1 - reserve) * usable_fraction
  Report a physics band and compare to the raw regression-implied evening energy.

(B) g - beta WEDGE
  g = physical rooftop generation per installed MW over the day (MWh/day per MW) from
      island GHI x conversion efficiency (derate). Computed from NSRDB years.
  beta = grid-load reduction per installed MW per day (MWh/day per MW), integrated from the
      radiation-identified PV term (Estimator 2) over daylight hours.
  At island level exports net out, so  g - beta ~= induced demand + battery/inverter losses
  per MW = new behind-the-meter consumption that never hits grid load.

Outputs: evening_shift_parameterization.csv, g_minus_beta_wedge.csv, paramz_summary.txt
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

# ---------------- (A) evening shift shape from Estimator 1 ----------------
e1 = pd.read_csv(os.path.join(OUT, "estimator1_coeffs_by_hour.csv"))
eve = e1[e1.hour.between(16, 21)].copy()
# discharge = negative battery coef (load reduction). Positive coefs (charging/EV) -> 0.
eve["discharge_mw_per_mwh"] = (-eve["beta_batt"]).clip(lower=0)
tot = eve["discharge_mw_per_mwh"].sum()
eve["shape_weight"] = eve["discharge_mw_per_mwh"] / tot if tot > 0 else 0.0
eve_out = eve[["hour", "beta_batt", "se_batt", "discharge_mw_per_mwh", "shape_weight"]]

# raw regression-implied evening discharge energy per installed MWh (MWh/MWh)
# = sum over evening hours of (-beta_batt, MW/MWh) * 1 hour
E_raw = eve["discharge_mw_per_mwh"].sum()  # MWh discharged per evening per MWh installed

# physics band for TOTAL shifted energy per installed MWh
rte = 0.86          # round-trip efficiency (AC-AC, typical Li-ion PV+storage)
reserve = 0.20      # backup reserve fraction held (BatteryBonus required 0; residential ~0.1-0.3)
usable = 0.90       # usable DoD fraction of nameplate MWh
E_phys = rte * (1 - reserve) * usable   # MWh delivered per installed MWh per cycle
out.append("(A) EVENING-SHIFT PARAMETERIZATION")
out.append(eve_out.round(4).to_string(index=False))
out.append("  discharge SHAPE weights (16-21h): " +
           ", ".join(f"{int(r.hour)}h={r.shape_weight:.3f}" for _, r in eve_out.iterrows()))
out.append("  raw regression-implied evening energy  = %.3f MWh delivered / MWh installed" % E_raw)
out.append("  physics cap  rte*(1-reserve)*usable    = %.3f MWh / MWh installed "
           "(rte=%.2f reserve=%.2f usable=%.2f)" % (E_phys, rte, reserve, usable))
out.append("  RECOMMENDED for Switch: energy = %.2f MWh/MWh, distributed over evening by the "
           "shape weights above." % min(E_raw, E_phys))
out.append("  battery-scale sensitivity: all per-MWh numbers are invariant to the 250-MWh island "
           "calibration; only the ISLAND-TOTAL shifted energy (= per-MWh * installed MWh) scales "
           "with it (linearly).")
eve_out.assign(E_recommended_mwh_per_mwh=min(E_raw, E_phys),
               E_physics_cap=E_phys).to_csv(
    os.path.join(OUT, "evening_shift_parameterization.csv"), index=False)

# ---------------- (B) g - beta wedge ----------------
# g: physical generation per installed MW per day.
# 1 MW nameplate DC at STC (1000 W/m2). AC energy/day = integral GHI(t)/1000 * PR dt (hours).
# PR (performance ratio incl inverter, temp, soiling, tilt vs GHI) ~ 0.80 for fixed rooftop.
isl = pd.read_parquet(os.path.join(OUT, "nsrdb_oahu_island_hourly.parquet"))
PR = 0.80
# daily generation MWh per MW = sum_hour (GHI/1000)*PR ; average across all days
isl["gen_mwh_per_mw_hr"] = (isl["ghi"] / 1000.0) * PR
g_daily = isl.groupby(isl[["year", "month", "day"]].apply(tuple, axis=1))[
    "gen_mwh_per_mw_hr"].sum()
g = g_daily.mean()   # MWh/day per MW installed (physical rooftop generation)

# beta: grid-load reduction per MW per day, from Estimator 2 PV term integrated over daylight.
pv = pd.read_csv(os.path.join(OUT, "estimator2_pv_term.csv"))
# per hour: load reduction MW per MW installed = -b_ghi_x_pv * GHI[hour]. Use mean GHI by hour.
ghi_by_hour = isl.groupby("hour")["ghi"].mean()
pv = pv.merge(ghi_by_hour.rename("ghi_mean"), left_on="hour", right_index=True, how="left")
pv["beta_mw_per_mw_hr"] = -pv["b_ghi_x_pv"] * pv["ghi_mean"]   # MW load-reduction per MW, that hour
beta = pv["beta_mw_per_mw_hr"].sum()   # MWh/day per MW (integrate 1h steps over daylight)

wedge = g - beta
out.append("\n(B) g - beta INDUCED-DEMAND WEDGE (per installed MW, daily energy)")
out.append("  g (physical rooftop gen, PR=%.2f) = %.3f MWh/day/MW" % (PR, g))
out.append("  beta (grid load reduction, radiation-identified) = %.3f MWh/day/MW" % beta)
out.append("  g - beta = %.3f MWh/day/MW = behind-the-meter induced demand + storage/inverter "
           "losses per MW that never appears in grid load." % wedge)
out.append("  as a fraction of generation: (g-beta)/g = %.1f%%" % (100 * wedge / g))
# uncertainty: propagate PV-term se (integrated) and a PR band 0.75-0.85
pv["beta_se_hr"] = pv["se"] * pv["ghi_mean"]
beta_se = np.sqrt((pv["beta_se_hr"] ** 2).sum())
g_lo = g * (0.75 / PR); g_hi = g * (0.85 / PR)
out.append("  uncertainty: beta = %.3f +/- %.3f (regression); g band (PR 0.75-0.85) = "
           "[%.3f, %.3f]; wedge band ~ [%.3f, %.3f] MWh/day/MW"
           % (beta, beta_se, g_lo, g_hi, g_lo - beta - beta_se, g_hi - beta + beta_se))

# time series: scale wedge per-MW by cumulative installed MW by year -> island-total induced demand
inst = pd.read_csv(os.path.join(OUT, "installs_cumulative_daily.csv"))
inst["date"] = pd.to_datetime(inst["date"])
rows = []
for y in range(2010, 2025):
    sub = inst[inst["date"] <= f"{y}-12-31"]
    if not len(sub):
        continue
    pv_mw = sub["pv_mw_cum"].iloc[-1]
    rows.append(dict(year=y, pv_mw_installed=pv_mw,
                     wedge_mwh_per_mw_per_day=wedge,
                     island_induced_gwh_per_year=pv_mw * wedge * 365 / 1000.0))
wt = pd.DataFrame(rows)
wt.to_csv(os.path.join(OUT, "g_minus_beta_wedge.csv"), index=False)
out.append("\n  ISLAND induced-demand time series (per-MW wedge x installed MW x 365d):")
out.append(wt.round(1).to_string(index=False))
out.append("  NOTE: wedge per-MW is estimated on 2007/08/18/19 radiation+PV-term and held "
           "constant across years (no battery-era radiation to re-estimate it). The rising "
           "island total is driven by rising installed MW, not a re-estimated per-MW wedge.")

txt = "\n".join(out)
with open(os.path.join(OUT, "paramz_summary.txt"), "w") as fh:
    fh.write(txt + "\n")
print(txt)
print("\nDONE 05")
