#!/usr/bin/env python3
"""Pre-battery calibration: effective usable AC MW per reported installed MW.

Purpose (see Appendix A.11): the installed-capacity series (pv_mw_cum,
compiled from permit/interconnection records) does not document its rating
basis (DC nameplate vs AC). All of the report's distributed-solar
coefficients are estimated per *reported* MW on this same series, so the
net-load projections are internally consistent whatever the basis. This
script pins the physical interpretation: in the pre-battery, NEM era
(2013-2019), when essentially all rooftop generation appeared on the meter,
the grid-load reduction per reported MW at reference irradiance (1 kW/m2)
measures usable AC output per reported MW, bundling tilt, aspect, soiling,
and inverter conversion.

Design: 4-hour blocks (averaging reduces measurement noise and attenuation
bias); day-to-day island-mean GHI variation within block x season x year
identifies the response; temperature controls; Newey-West standard errors
(Driscoll-Kraay, since each date carries three daylight blocks).
Zone-weighting of radiation by installed MW is immaterial for this fleet
(weighted/uniform ratio 0.9907; analysis/TASK_B_NOTES.md).

Result (written to prebattery_effective_mw.txt): about 0.79 usable AC MW per
reported MW, consistent with a DC-nameplate reported series and
standard derates. Not directly comparable to the battery-era 0.61 MW/MW
grid-load coefficient, which additionally nets the behind-the-meter wedge
and post-NEM tariff structures.
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
LAG_GRID = [0, 7, 14, 28, 56, 90]
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

p = pd.read_parquet(f"{ANA}/panel_hourly_with_installs.parquet")
r = pd.read_parquet(f"{ANA}/nsrdb_oahu_island_hourly_2013_2019.parquet")
r = r[["year", "month", "day", "hour", "ghi", "temp"]].drop_duplicates(
    ["year", "month", "day", "hour"])

p["dt"] = pd.to_datetime(p.dt_hst).dt.tz_localize(None)
p["y"], p["m"], p["d"], p["h"] = p.dt.dt.year, p.dt.dt.month, p.dt.dt.day, p.dt.dt.hour
d = p.merge(r, left_on=["y", "m", "d", "h"],
            right_on=["year", "month", "day", "hour"], how="inner")
d = d[(d.y >= 2013) & (d.y <= 2019)]           # pre-battery, NEM era; also the
                                               # FERC-714 reference clock era
d["blk"] = (d.h // 4) * 4
d["ghi_kw"] = d.ghi / 1000.0

g = (d.groupby(["y", "m", "d", "blk"])
       .agg(load=("load_mw", "mean"), ghi=("ghi_kw", "mean"),
            temp=("temp", "mean"), pv=("pv_mw_cum", "mean"),
            batt=("batt_mwh_cum", "mean")).reset_index())
g["ghi_pv"] = g.ghi * g.pv
g["season"] = (g.m % 12) // 3
g["dow"] = pd.to_datetime(dict(year=g.y, month=g.m, day=g.d)).dt.dayofweek

day = g[g.blk.isin([8, 12, 16])].copy()        # daylight blocks
day["blk_s"] = day.blk.astype(str) + "_" + day.season.astype(str)
day["date"] = pd.to_datetime(dict(year=day.y, month=day.m, day=day.d))
day = day.sort_values(["date", "blk"])
day["tidx"] = day["date"].rank(method="dense").astype(int) - 1

FORM = "load ~ ghi_pv + ghi + temp + C(blk_s) + C(y)"
NDAYS = int(day["tidx"].nunique())
L = nw_lags(NDAYS)
mod = smf.ols(FORM, data=day).fit(**dk_kwds(day["tidx"].to_numpy(), L))

b, se = mod.params["ghi_pv"], mod.bse["ghi_pv"]
dr = day.assign(_r=mod.resid.to_numpy()).groupby("tidx")["_r"].mean().to_numpy()
a = acf(dr, ACF_LAGS)
rho, S_and = andrews_bartlett(dr)
lb = ljung_box(a, len(dr), [7, 14, 28, 90])
band = 1.96 / np.sqrt(len(dr))
pd.DataFrame([dict(lag=k, acf=v, band=band) for k, v in enumerate(a)]).to_csv(
    f"{OUT}/hac_acf_prebattery.csv", index=False)
FORM_D = FORM + " + C(dow)"
mdw = smf.ols(FORM_D, data=day).fit(**dk_kwds(day["tidx"].to_numpy(), L))
drd = day.assign(_r=mdw.resid.to_numpy()).groupby("tidx")["_r"].mean().to_numpy()
ad = acf(drd, ACF_LAGS)
rd, Sd = andrews_bartlett(drd)
dow_line = (f"+ day-of-week FE: coef {mdw.params['ghi_pv']:.4f} "
            f"(se {mdw.bse['ghi_pv']:.4f}, t {mdw.params['ghi_pv']/mdw.bse['ghi_pv']:.2f}), "
            f"rho {rd:.3f}, Andrews {Sd:.1f} d\n"
            "  ACF: " + ", ".join(f"L{k}={ad[k]:.3f}" for k in (1, 7, 14, 21, 28, 56, 90)))
sens = []
for LL in LAG_GRID:
    ms = (smf.ols(FORM, data=day).fit() if LL == 0
          else smf.ols(FORM, data=day).fit(**dk_kwds(day["tidx"].to_numpy(), LL)))
    sens.append("  lags %2d: se %.4f  t %.2f"
                % (LL, ms.bse["ghi_pv"], b / ms.bse["ghi_pv"]))
out = (
    f"Pre-battery effective usable AC MW per reported installed MW\n"
    f"window 2013-2019 (NEM era; max batt/PV ratio "
    f"{g.batt.max()/g.pv.max():.3f} MWh/MW)\n"
    f"4-hour daylight blocks, N={len(day)}\n"
    f"GHI x PV coefficient: {b:.4f} (se {se:.4f}, t {b/se:.2f})\n"
    f"Newey-West (Driscoll-Kraay), {L} lags over {NDAYS} days\n"
    f"day-mean residual AR(1) rho {rho:.3f}; "
    f"Andrews Bartlett bandwidth {S_and:.1f} days\n"
    f"ACF: " + ", ".join(f"L{k}={a[k]:.3f}" for k in (1, 7, 14, 21, 28, 56, 90))
    + f"  (band +/-{band:.3f})\n"
    + "Ljung-Box: " + ", ".join(f"Q({k})={v:.0f}" for k, v in lb.items()) + "\n"
    f"bandwidth sensitivity (lag 0 = plain OLS):\n" + "\n".join(sens) + "\n"
    + dow_line + "\n"
    f"-> {-b:.3f} MW grid-load reduction per reported MW at 1 kW/m2\n"
    f"Interpretation: usable AC output per reported MW incl. tilt/aspect/\n"
    f"soiling/inverter; consistent with a DC-nameplate reported series.\n"
)
open(f"{OUT}/prebattery_effective_mw.txt", "w").write(out)
print(out)
