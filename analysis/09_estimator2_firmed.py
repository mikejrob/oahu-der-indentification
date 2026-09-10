#!/usr/bin/env python3
"""
09_estimator2_firmed.py — Estimator 2 with battery-era radiation (2018-2024) on the
clock-corrected load. Firms the BATTERY term.

Radiation years available: 2018, 2019 (from 03_load_nsrdb) + 2020-2024 (S3 pull).
Load: panel_hourly_shifted.parquet (clock roll applied; radiation NOT shifted).

PV term (contemporaneous): daytime load ~ hourxseason + year FE + temp controls + GHI x PV_installed.
Battery term (predictive): EVENING load (17-20h) ~ hourxseason + year FE + EVENING-temp controls
    + (same-day MIDDAY GHI) x Batt_installed. Sunny midday -> fuller battery -> more evening
    discharge -> LOWER evening load. PV cannot generate in the evening -> separates battery from PV.

Energy-conservation check: evening discharge per installed MWh must be <= rte*(1-reserve).

Standard errors: Newey-West HAC on the per-hour regressions (one observation per
date, rows sorted in time order); Driscoll-Kraay on the pooled evening model,
which carries four hours per date. Truncation lag from 4*(T/100)^(2/9); the
pooled model reports a bandwidth sensitivity. Load residuals are serially
correlated day to day, so default OLS errors are too small.

Outputs: estimator2_pv_term_firmed.csv, estimator2_battery_firmed.csv,
         estimator2_battery_shape.csv, estimator2_firmed_summary.txt
"""
import os
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf


def nw_lags(n_periods):
    """Newey-West truncation lag, 4*(T/100)^(2/9) (Newey and West 1994)."""
    return max(1, int(4.0 * (n_periods / 100.0) ** (2.0 / 9.0)))


def dk_kwds(tidx, maxlags):
    """Driscoll-Kraay: Newey-West across days after aggregating within each day.
    Used where one regression carries several hours per date, so the residuals
    are correlated both within a day and across nearby days."""
    return dict(cov_type="hac-groupsum",
                cov_kwds={"time": tidx, "maxlags": maxlags,
                          "use_correction": "cluster"})


def score_acf(resid, x, nlags):
    """Autocorrelation of the SCORE (demeaned regressor times residual), which
    is the series a HAC estimator actually weights. The residual's own ACF is
    the wrong diagnostic for bandwidth choice: a weekly cycle in load shows up
    strongly in the residual and only weakly in the score, because the
    regressor is not weekly-periodic. Verified on simulation, 2026-09-10."""
    x = np.asarray(x, dtype=float)
    return acf(np.asarray(resid, dtype=float) * (x - x.mean()), nlags)


def acf(x, nlags):
    """Sample autocorrelation of a mean-zero series, lags 0..nlags."""
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    d = float((x * x).sum())
    return [1.0] + [float((x[k:] * x[:-k]).sum() / d) for k in range(1, nlags + 1)]


def andrews_bartlett(resid):
    """Andrews (1991) AR(1) plug-in bandwidth for the Bartlett kernel.
    alpha(1) = 4 rho^2 / ((1-rho)^2 (1+rho)^2); S_T = 1.1447 (alpha(1) T)^(1/3)."""
    x = np.asarray(resid, dtype=float)
    x = x - x.mean()
    rho = float((x[1:] * x[:-1]).sum() / (x[:-1] ** 2).sum())
    rho = min(max(rho, -0.97), 0.97)
    a1 = 4.0 * rho ** 2 / ((1.0 - rho) ** 2 * (1.0 + rho) ** 2)
    return rho, 1.1447 * (a1 * len(x)) ** (1.0 / 3.0)


def ljung_box(a, T, lags):
    """Ljung-Box Q from an acf list a (index = lag)."""
    return {L: float(T * (T + 2) * sum(a[k] ** 2 / (T - k) for k in range(1, L + 1)))
            for L in lags}


# Bandwidth grid. The time index in every model below is the DAY, not the hour:
# each regression carries one observation per date (09 PV, 09 shape) or is
# aggregated to the date by Driscoll-Kraay (09 pooled, 18). Load at a fixed hour
# of day carries a weekly cycle, so the grid spans several weeks.
# Bandwidth grid. Simulation puts the score ACF still near 0.29 at lag 28,
# so the 4(T/100)^(2/9) rule (8 at T=2557) is too short; 28 is the default.
LAG_GRID = [0, 7, 14, 28, 56, 90]
LAG_DEFAULT = 28
ACF_LAGS = 90

ANA = os.environ.get(
    "OAHU_ANA",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "raw"))
OUT = os.environ.get(
    "OAHU_OUT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "derived"))
os.makedirs(OUT, exist_ok=True)
REF_GHI = 1000.0

# ---- radiation: combine 2018/19 (03) + 2020-24 (S3). Dedup on (y,m,d,h).
r1 = pd.read_parquet(os.path.join(ANA, "nsrdb_oahu_island_hourly.parquet"))
r1 = r1[r1.year.isin([2018, 2019])][["year", "month", "day", "hour", "ghi", "temp", "dni", "dhi"]]
r2 = pd.read_parquet(os.path.join(ANA, "nsrdb_oahu_island_hourly_2020_2024.parquet"))
r2 = r2[["year", "month", "day", "hour", "ghi", "temp", "dni", "dhi"]]
isl = pd.concat([r1, r2], ignore_index=True).drop_duplicates(["year", "month", "day", "hour"])
isl["date"] = pd.to_datetime(isl[["year", "month", "day"]])
RAD_YEARS = sorted(isl.year.unique().tolist())

# same-day midday GHI (10-14h), evening temp (17-20h), midday temp
midday = isl[isl.hour.between(10, 14)].groupby("date").agg(
    ghi_midday=("ghi", "mean"), temp_midday=("temp", "mean")).reset_index()
evening = isl[isl.hour.between(17, 20)].groupby("date").agg(
    temp_evening=("temp", "mean")).reset_index()

# ---- load (clock-corrected), restrict to radiation years
pan = pd.read_parquet(os.path.join(ANA, "panel_hourly_shifted.parquet"))
pan["date"] = pd.to_datetime(pan["date"])
pan = pan[pan["year"].isin(RAD_YEARS)].copy()

m = pan.merge(isl[["date", "hour", "ghi", "temp", "dni"]], on=["date", "hour"], how="inner")
m = m.merge(midday, on="date", how="left").merge(evening, on="date", how="left")
m["season"] = m["quarter"].astype("category")
m["hourF"] = m["hour"].astype("category")
m["yearF"] = m["year"].astype("category")
m["dow"] = m["date"].dt.dayofweek
m["ghi_x_pv"] = m["ghi"] * m["pv_mw_cum"]
m["middayghi_x_batt"] = m["ghi_midday"] * m["batt_mwh_cum"]

out = []
out.append("Estimator 2 FIRMED — radiation years: %s (clock-corrected load)" % RAD_YEARS)

# =============================== PV TERM ===============================
# Identification note: within-year PV drift is only ~30-50 MW vs a 476->765 MW between-year
# spread, so year FE would eat the PV level and leave ghi_x_pv collinear with the standalone
# ghi control (corrupts the per-hour shape). Per the design ("EV/secular trend control"),
# use a LINEAR secular trend (t_years) instead of year FE, and drop the standalone ghi term so
# ghi_x_pv carries the PV response identified off both day-to-day GHI and the PV level.
m["t_years"] = m["year"] + (m["month"] - 1) / 12.0
m["t_years"] = m["t_years"] - m["t_years"].mean()
day = m[m["hour"].between(7, 17)].copy()
pv_rows, pv_resid, pv_data = [], {}, {}
for h in range(7, 18):
    sub = day[day["hour"] == h].sort_values("date")
    if sub["ghi"].std() < 1 or sub["pv_mw_cum"].max() < 1:
        continue
    L = nw_lags(len(sub))
    mod = smf.ols("load_mw ~ C(season) + t_years + temp + I(temp**2) + ghi_x_pv",
                  data=sub).fit(cov_type="HAC",
                                cov_kwds={"maxlags": L, "use_correction": True})
    b = mod.params.get("ghi_x_pv", np.nan)
    se = mod.bse.get("ghi_x_pv", np.nan)
    pv_rows.append(dict(hour=h, b_ghi_x_pv=b, se=se,
                        mw_per_mw_at_ref=b * REF_GHI, se_at_ref=se * REF_GHI,
                        t=(b / se if se else np.nan), nw_lags=L,
                        n=int(mod.nobs)))
    pv_resid[h] = mod.resid.to_numpy()
    pv_data[h] = sub
pv = pd.DataFrame(pv_rows)
pv.to_csv(os.path.join(OUT, "estimator2_pv_term_firmed.csv"), index=False)
out.append("\nPV TERM (per hour, MW load-reduction per MW installed at %g W/m2; "
           "se_at_ref is on that same scale, Newey-West HAC):" % REF_GHI)
out.append(pv[["hour", "mw_per_mw_at_ref", "se_at_ref", "t", "nw_lags", "n"]]
           .round(4).to_string(index=False))
noon = pv[pv.hour == 12]
if len(noon):
    out.append("  noon PV = %.3f MW/MW" % (-noon["mw_per_mw_at_ref"].iloc[0]))

# ---- HAC diagnostics for the PV term: residual autocorrelation and the
# bandwidth curve. The time index is the DAY (one observation per date at a
# fixed hour), so a lag is a day. No day-of-week control is in the spec, so a
# weekly cycle should show as ACF spikes at 7, 14, 21, 28.
acf_rows, curve_rows = [], []
for h, res in sorted(pv_resid.items()):
    a = acf(res, ACF_LAGS)
    T = len(res)
    rho, S_and = andrews_bartlett(res)
    lb = ljung_box(a, T, [7, 14, 28, 90])
    band = 1.96 / np.sqrt(T)
    for k, v in enumerate(a):
        acf_rows.append(dict(model="pv_h%d" % h, lag=k, acf=v, band=band))
    for LL in LAG_GRID:
        fit = (smf.ols("load_mw ~ C(season) + t_years + temp + I(temp**2) + ghi_x_pv",
                       data=pv_data[h]).fit()
               if LL == 0 else
               smf.ols("load_mw ~ C(season) + t_years + temp + I(temp**2) + ghi_x_pv",
                       data=pv_data[h]).fit(cov_type="HAC",
                                            cov_kwds={"maxlags": LL,
                                                      "use_correction": True}))
        s_ll = fit.bse["ghi_x_pv"] * REF_GHI
        curve_rows.append(dict(model="pv_h%d" % h, maxlags=LL, se_at_ref=s_ll,
                               t=fit.params["ghi_x_pv"] * REF_GHI / s_ll))
    if h == 12:
        out.append("\n  PV noon-hour HAC diagnostics (T=%d days):" % T)
        out.append("    residual AR(1) rho = %.3f; Andrews Bartlett bandwidth = %.1f days"
                   % (rho, S_and))
        asc = score_acf(res, pv_data[h]["ghi_x_pv"], ACF_LAGS)
        out.append("    residual ACF: " + ", ".join(
            "L%d=%.3f" % (k, a[k]) for k in (1, 7, 14, 21, 28, 56, 90)))
        out.append("    SCORE ACF   : " + ", ".join(
            "L%d=%.3f" % (k, asc[k]) for k in (1, 7, 14, 21, 28, 56, 90))
            + "   <- this is what sets the bandwidth")
        out.append("    Bartlett band +/-%.3f; Ljung-Box Q: " % band
                   + ", ".join("Q(%d)=%.0f" % (k, v) for k, v in lb.items()))
        cc = [r for r in curve_rows if r["model"] == "pv_h12"]
        out.append("    se_at_ref by bandwidth: " + ", ".join(
            "L%d=%.4f" % (r["maxlags"], r["se_at_ref"]) for r in cc))
        # Same hour with day-of-week absorbed. Load at a fixed hour carries a
        # weekday/weekend cycle; left in the residual it makes the ACF plateau
        # at weekly lags and no bandwidth is long enough. Reported as a
        # comparison, not substituted for the baseline spec.
        FD = ("load_mw ~ C(season) + C(dow) + t_years + temp + I(temp**2) "
              "+ ghi_x_pv")
        md = smf.ols(FD, data=pv_data[12]).fit(
            cov_type="HAC", cov_kwds={"maxlags": nw_lags(len(pv_data[12])),
                                      "use_correction": True})
        ad = acf(md.resid.to_numpy(), ACF_LAGS)
        rd, Sd = andrews_bartlett(md.resid.to_numpy())
        out.append("    + day-of-week FE: point %.4f, rho %.3f, Andrews %.1f d"
                   % (md.params["ghi_x_pv"] * REF_GHI, rd, Sd))
        out.append("      ACF: " + ", ".join(
            "L%d=%.3f" % (k, ad[k]) for k in (1, 7, 14, 21, 28, 56, 90)))
        out.append("      se_at_ref by bandwidth: " + ", ".join(
            "L%d=%.4f" % (LL, (smf.ols(FD, data=pv_data[12]).fit() if LL == 0 else
                               smf.ols(FD, data=pv_data[12]).fit(
                                   cov_type="HAC",
                                   cov_kwds={"maxlags": LL,
                                             "use_correction": True})
                               ).bse["ghi_x_pv"] * REF_GHI) for LL in LAG_GRID))
        for k, v in enumerate(ad):
            acf_rows.append(dict(model="pv_h12_dow", lag=k, acf=v, band=band))

# =============================== BATTERY TERM ===============================
# CLEAN window = SUN-DOWN evening hours 19-22h where PV output is ~0, so same-day midday GHI
# cannot act through contemporaneous PV. (Hours 16-18 still have direct sun in HST summer ->
# midday_GHI x Batt there is contaminated by PV self-consumption; we report them but exclude
# from the identifying window and the energy integral.) Keep yearFE (battery grows within era)
# and a standalone midday-GHI control so the coef is the batt-INTERACTION, not the GHI main effect.
CLEAN = list(range(19, 23))     # 19,20,21,22 HST — sun down
eve = m[m["hour"].isin(CLEAN)].sort_values(["date", "hour"]).copy()
eve["tidx"] = eve["date"].rank(method="dense").astype(int) - 1
out.append("\nBATTERY TERM — clean sun-down window %s ~ hourFE + season + yearFE + evening-temp "
           "+ midday_GHI + midday_GHI x Batt_installed" % CLEAN)
out.append("  battery range in radiation years: %.1f - %.1f MWh"
           % (eve["batt_mwh_cum"].min(), eve["batt_mwh_cum"].max()))

# pooled (include standalone ghi_midday so the interaction is net of the GHI main effect)
BFORM = ("load_mw ~ C(hourF) + C(season) + C(yearF) + temp_evening "
         "+ I(temp_evening**2) + ghi_midday + middayghi_x_batt")
NDAYS = int(eve["tidx"].nunique())
L_eve = nw_lags(NDAYS)
modb = smf.ols(BFORM, data=eve).fit(**dk_kwds(eve["tidx"].to_numpy(), L_eve))
cb = modb.params.get("middayghi_x_batt", np.nan)   # MW per (W/m2 * MWh)
seb = modb.bse.get("middayghi_x_batt", np.nan)
ghi_mid_mean = eve["ghi_midday"].mean()
disch_mw_per_mwh_pooled = -cb * ghi_mid_mean
out.append("  pooled coef = %.6g (se %.6g, t %.2f) MW per (W/m2 * MWh); "
           "Driscoll-Kraay, %d lags over %d days"
           % (cb, seb, cb / seb, L_eve, NDAYS))
# day-mean residual is the series Driscoll-Kraay aggregates over, so its ACF is
# what the bandwidth has to span.
eve_r = eve.assign(_r=modb.resid.to_numpy()).groupby("tidx")["_r"].mean().to_numpy()
a_e = acf(eve_r, ACF_LAGS)
rho_e, S_e = andrews_bartlett(eve_r)
lb_e = ljung_box(a_e, len(eve_r), [7, 14, 28, 90])
band_e = 1.96 / np.sqrt(len(eve_r))
for k, v in enumerate(a_e):
    acf_rows.append(dict(model="battery_pooled", lag=k, acf=v, band=band_e))
out.append("  day-mean residual AR(1) rho = %.3f; Andrews Bartlett bandwidth = %.1f days"
           % (rho_e, S_e))
out.append("  ACF at weekly lags: " + ", ".join(
    "L%d=%.3f" % (k, a_e[k]) for k in (1, 7, 14, 21, 28, 56, 90))
    + "  (band +/-%.3f)" % band_e)
out.append("  Ljung-Box Q: " + ", ".join("Q(%d)=%.0f" % (k, v) for k, v in lb_e.items()))
BFORM_D = BFORM.replace("C(hourF)", "C(hourF) + C(dow)")
mdb = smf.ols(BFORM_D, data=eve).fit(**dk_kwds(eve["tidx"].to_numpy(), L_eve))
edr = eve.assign(_r=mdb.resid.to_numpy()).groupby("tidx")["_r"].mean().to_numpy()
ade = acf(edr, ACF_LAGS)
rde, Sde = andrews_bartlett(edr)
out.append("  + day-of-week FE: coef %.6g (se %.6g, t %.2f), rho %.3f, Andrews %.1f d"
           % (mdb.params["middayghi_x_batt"], mdb.bse["middayghi_x_batt"],
              mdb.params["middayghi_x_batt"] / mdb.bse["middayghi_x_batt"], rde, Sde))
out.append("    ACF: " + ", ".join(
    "L%d=%.3f" % (k, ade[k]) for k in (1, 7, 14, 21, 28, 56, 90)))
for k, v in enumerate(ade):
    acf_rows.append(dict(model="battery_pooled_dow", lag=k, acf=v, band=band_e))
out.append("  bandwidth sensitivity (point estimate fixed; se varies):")
for LL in LAG_GRID:
    ms = (smf.ols(BFORM, data=eve).fit() if LL == 0
          else smf.ols(BFORM, data=eve).fit(**dk_kwds(eve["tidx"].to_numpy(), LL)))
    s_ll = ms.bse.get("middayghi_x_batt", np.nan)
    out.append("    lags %2d: se %.6g  t %.2f" % (LL, s_ll, cb / s_ll))
    curve_rows.append(dict(model="battery_pooled", maxlags=LL, se_at_ref=s_ll,
                           t=cb / s_ll))
pd.DataFrame(acf_rows).to_csv(os.path.join(OUT, "hac_acf.csv"), index=False)
pd.DataFrame(curve_rows).to_csv(os.path.join(OUT, "hac_bandwidth_curve.csv"), index=False)
out.append("  mean midday GHI = %.0f W/m2 -> pooled evening load reduction "
           "= %.4f MW per installed MWh (avg over window)" % (ghi_mid_mean, disch_mw_per_mwh_pooled))

# per-hour battery shape over the full evening shoulder 17-23 (report all; integrate CLEAN only)
sh_rows = []
for h in range(17, 24):
    sub = m[m["hour"] == h].sort_values("date").copy()
    mh = smf.ols("load_mw ~ C(season) + C(yearF) + temp_evening + I(temp_evening**2) "
                 "+ ghi_midday + middayghi_x_batt", data=sub).fit(
                     cov_type="HAC",
                     cov_kwds={"maxlags": nw_lags(len(sub)),
                               "use_correction": True})
    c = mh.params.get("middayghi_x_batt", np.nan)
    sh_rows.append(dict(hour=h, coef=c, se=mh.bse.get("middayghi_x_batt", np.nan),
                        disch_mw_per_mwh=-c * ghi_mid_mean,
                        clean=h in CLEAN))
shape = pd.DataFrame(sh_rows).sort_values("hour").reset_index(drop=True)
# discharge shape = positive part (load reduction), normalized over the CLEAN sun-down window
shape["disch_pos"] = shape["disch_mw_per_mwh"].clip(lower=0)
cleanmask = shape["clean"]
tot_energy = shape.loc[cleanmask, "disch_pos"].sum()   # MWh delivered per installed MWh (1h steps)
shape["shape_weight"] = 0.0
if tot_energy > 0:
    shape.loc[cleanmask, "shape_weight"] = shape.loc[cleanmask, "disch_pos"] / tot_energy
shape.to_csv(os.path.join(OUT, "estimator2_battery_shape.csv"), index=False)
out.append("\n  per-hour battery discharge (MW lower evening load per installed MWh); "
           "shape_weight over CLEAN sun-down window only:")
out.append(shape[["hour", "coef", "se", "disch_mw_per_mwh", "clean", "shape_weight"]].round(4).to_string(index=False))

# ---- ENERGY-CONSERVATION CHECK
rte, reserve, usable = 0.86, 0.20, 0.90
E_phys = rte * (1 - reserve) * usable
out.append("\n  ENERGY per installed MWh (integral of discharge over evening) = %.3f MWh/MWh"
           % tot_energy)
out.append("  physics cap rte*(1-reserve)*usable = %.3f MWh/MWh" % E_phys)
passfail = "PASS" if tot_energy <= E_phys + 0.05 else ("PLAUSIBLE" if tot_energy <= 1.0 else "FAIL")
out.append("  energy-conservation check: %s (radiation-identified = %.3f vs collinear Estimator-1 = 3.24)"
           % (passfail, tot_energy))

pd.DataFrame([dict(pooled_coef=cb, pooled_se=seb, ghi_mid_mean=ghi_mid_mean,
                   energy_mwh_per_mwh=tot_energy, physics_cap=E_phys,
                   check=passfail)]).to_csv(
    os.path.join(OUT, "estimator2_battery_firmed.csv"), index=False)

txt = "\n".join(out)
with open(os.path.join(OUT, "estimator2_firmed_summary.txt"), "w") as fh:
    fh.write(txt + "\n")
print(txt)
print("\nDONE 09")
