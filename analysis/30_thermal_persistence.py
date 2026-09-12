#!/usr/bin/env python3
"""30_thermal_persistence.py -- how much of a day's radiation shows up in load
after dark, in years when rooftop PV and storage could not be the reason.

WHY

The weather-split of the PV coefficient (29) found an evening component that
moves with the day's radiation: bright day, higher load after sunset, decaying to
nothing by midnight. That was read as thermal persistence in buildings. If it
is, the same pattern must exist before rooftop PV, and its size then is a
benchmark for what a "thermal" component should look like now. Rooftop PV on
Oahu was under 40 MW through mid-2010 against a system load near 1,000 MW, and
storage was nil, so 2006-2010 is the cleanest window. After dark PV cannot
affect load in any year, so 2011-2019 evening hours are a second benchmark that
tests whether the persistence grew with the PV stock (households that add PV
adding A/C would do that; a constant building stock would not).

DESIGN, per hour of day and per window

  load(h,d) = season spline + weekend + linear trend
              + f(T(h,d)) + GHI(h,d)
              + a * GHI_day(d) + b * GHI_day(d-1) + e

GHI_day is the mean island radiation over 08:00-16:00 of the calendar day. For
hours after sunset, a is the same-day persistence of daytime radiation into
load, conditional on that hour's own temperature and dewpoint. It is the object
a later specification would need as a control. Variants: without the
temperature terms (total weather persistence), and with the outcome anchored on
the 04:00 load as in 28/29. Newey-West, 28 lags, one observation per date.

A tercile contrast (bright third minus dark third of the seasonally-adjusted
GHI_day, in MW) is printed alongside so the numbers can be set against the
bright-minus-dark contrast of the PV coefficient in 29.

Solar water heating pulls the other way: a bright day means less electric
water heating in the evening, so a is a net of building thermal mass (positive)
and solar-thermal substitution (negative), and both belong in the control.
"""
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "raw"
OUT = REPO / "data" / "derived"
LAGS = 28

h = pd.read_parquet(RAW / "panel_hourly_shifted.parquet")
h["date"] = pd.to_datetime(h["date"])
rad = pd.concat([pd.read_parquet(f)[["year", "month", "day", "hour", "ghi"]]
                 for f in sorted(RAW.glob("_nsrdb_isl_*.parquet"))],
                ignore_index=True).drop_duplicates(["year", "month", "day", "hour"])
rad["date"] = pd.to_datetime(rad[["year", "month", "day"]])
h = h.merge(rad[["date", "hour", "ghi"]], on=["date", "hour"], how="inner")
t = pd.read_parquet(REPO / "data/analysis/oahu_temperature_hourly.parquet")
t["date"] = pd.to_datetime(t["date"])
h = h.merge(t[["date", "hour", "t_pv", "td_pv"]], on=["date", "hour"], how="left")

der = pd.read_parquet(RAW / "der_points.parquet")
der["date"] = pd.to_datetime(der["date"], errors="coerce")
pv = (der.dropna(subset=["date"]).groupby(der.date.dt.normalize()).kw_est.sum()
      .sort_index().cumsum() / 1e3)
pv = pv.reindex(pd.date_range("2006-01-01", h.date.max(), freq="D")).ffill().fillna(0)
pv.index.name = "date"
h = h.merge(pv.rename("PV").reset_index(), on="date", how="left")

day = (h[h.hour.between(8, 16)].groupby("date").ghi.mean().rename("ghi_day")
       .to_frame())
day = day.reindex(pd.date_range(day.index.min(), day.index.max(), freq="D"))
day["ghi_day_l1"] = day.ghi_day.shift(1)
day["ghi_day_l2"] = day.ghi_day.shift(2)
day.index.name = "date"
h = h.merge(day.reset_index(), on="date", how="left")
anch = h[h.hour == 4].set_index("date").load_mw.rename("anch")
h = h.merge(anch, on="date", how="left")
h["y_anch"] = h.load_mw - h.anch
h = h.dropna(subset=["load_mw", "t_pv", "td_pv", "ghi", "ghi_day", "ghi_day_l1"])
h["doy"] = h.date.dt.dayofyear
h["we"] = (h.date.dt.dayofweek >= 5).astype(int)

WINDOWS = {"2006-2010": (2006, 2010), "2011-2015": (2011, 2015),
           "2016-2019": (2016, 2019), "2021-2025H1": (2021, 2025)}
SAMPLE_END = pd.Timestamp("2025-06-30")


def fit(s, y, temp=True, pvint=False):
    f = y + " ~ cr(doy, df=5) + C(we) + hs + ghi + ghi_day + ghi_day_l1"
    if temp:
        f += " + t_pv + I(t_pv**2) + td_pv"
    if pvint:
        f += " + PV + ghi_day:PV + ghi:PV"
    return smf.ols(f, data=s).fit(cov_type="HAC",
                                  cov_kwds={"maxlags": LAGS, "use_correction": True})


rows = []
for wname, (y0, y1) in WINDOWS.items():
    w = h[(h.year >= y0) & (h.year <= y1) & (h.date <= SAMPLE_END)].copy()
    w["hs"] = (w.date - w.date.min()).dt.days
    # seasonally adjusted daily radiation -> terciles for the contrast
    d = w[w.hour == 12][["date", "doy", "ghi_day"]].copy()
    sa = smf.ols("ghi_day ~ cr(doy, df=5)", data=d).fit()
    d["ghi_anom"] = sa.resid
    d["terc"] = pd.qcut(d.ghi_anom, 3, labels=["dark", "mid", "bright"])
    dghi = d.groupby("terc", observed=True).ghi_day.mean()
    contrast_wm2 = dghi["bright"] - dghi["dark"]
    w = w.merge(d[["date", "terc"]], on="date", how="left")
    for hh in range(24):
        s = w[w.hour == hh].sort_values("date")
        if len(s) < 400:
            continue
        rA = fit(s, "load_mw", temp=True)
        rB = fit(s, "load_mw", temp=False)
        rC = fit(s[s.hour != 4], "y_anch", temp=True) if hh != 4 else None
        rT = smf.ols("load_mw ~ cr(doy, df=5) + C(we) + hs + ghi + ghi_day_l1"
                     " + t_pv + I(t_pv**2) + td_pv + C(terc, Treatment('mid'))",
                     data=s).fit(cov_type="HAC", cov_kwds={"maxlags": LAGS,
                                                            "use_correction": True})
        rP = fit(s, "load_mw", temp=True, pvint=True) if y0 >= 2011 else None
        rows.append(dict(
            window=wname, hour=hh, n=len(s), load_mean=s.load_mw.mean(),
            pv_mean=s.PV.mean(), contrast_wm2=contrast_wm2,
            a_temp=rA.params.ghi_day, a_temp_se=rA.bse.ghi_day,
            a_l1_temp=rA.params.ghi_day_l1, a_l1_temp_se=rA.bse.ghi_day_l1,
            a_notemp=rB.params.ghi_day, a_notemp_se=rB.bse.ghi_day,
            a_l1_notemp=rB.params.ghi_day_l1, a_l1_notemp_se=rB.bse.ghi_day_l1,
            a_anch=(rC.params.ghi_day if rC is not None else np.nan),
            a_anch_se=(rC.bse.ghi_day if rC is not None else np.nan),
            terc_bright=rT.params["C(terc, Treatment('mid'))[T.bright]"],
            terc_dark=rT.params["C(terc, Treatment('mid'))[T.dark]"],
            terc_bright_se=rT.bse["C(terc, Treatment('mid'))[T.bright]"],
            terc_dark_se=rT.bse["C(terc, Treatment('mid'))[T.dark]"],
            a_pvint=(rP.params["ghi_day:PV"] if rP is not None else np.nan),
            a_pvint_se=(rP.bse["ghi_day:PV"] if rP is not None else np.nan),
            a_main_pvint=(rP.params.ghi_day if rP is not None else np.nan),
        ))

out = pd.DataFrame(rows)
out["contrast_mw_temp"] = out.a_temp * out.contrast_wm2
out["contrast_mw_notemp"] = out.a_notemp * out.contrast_wm2
out["pct_of_load_temp"] = 100 * out.contrast_mw_temp / out.load_mean
out.to_csv(OUT / "thermal_persistence_by_hour.csv", index=False)

pd.set_option("display.width", 200)


def star(b, se):
    return "*" if abs(b) > 1.96 * se else " "


for wname in WINDOWS:
    o = out[out.window == wname].set_index("hour")
    print("\n=== %s   (PV mean %.0f MW; bright-dark tercile gap in GHI_day = %.0f W/m2) ==="
          % (wname, o.pv_mean.mean(), o.contrast_wm2.iloc[0]))
    print("  same-day GHI_day coefficient, MW per 100 W/m2 (NW-28); contrast = bright-dark tercile, MW")
    print(" hour  load  | a|temp   se    | a|noT    se    | a|anch   se    | lag1|temp  se  | terc B-D  (se)  | %load")
    for hh in list(range(17, 24)) + list(range(0, 8)) + [12]:
        if hh not in o.index:
            continue
        r = o.loc[hh]
        bd = r.terc_bright - r.terc_dark
        bdse = np.sqrt(r.terc_bright_se ** 2 + r.terc_dark_se ** 2)
        print(" %4d %5.0f  | %+6.2f%s %5.2f | %+6.2f%s %5.2f | %+6.2f%s %5.2f | %+6.2f%s %5.2f | %+6.1f (%4.1f)%s | %+5.2f"
              % (hh, r.load_mean,
                 100 * r.a_temp, star(r.a_temp, r.a_temp_se), 100 * r.a_temp_se,
                 100 * r.a_notemp, star(r.a_notemp, r.a_notemp_se), 100 * r.a_notemp_se,
                 100 * r.a_anch, star(r.a_anch, r.a_anch_se) if not np.isnan(r.a_anch) else " ", 100 * r.a_anch_se,
                 100 * r.a_l1_temp, star(r.a_l1_temp, r.a_l1_temp_se), 100 * r.a_l1_temp_se,
                 bd, bdse, star(bd, bdse), r.pct_of_load_temp))
    if o.a_pvint.notna().any():
        print("  persistence x PV stock (MW per 100 W/m2 per 100 MW PV; main effect at PV=0):")
        print("   hour: " + "  ".join("%d:%+.2f%s(%.2f)|%+.2f" % (
            hh, 1e4 * o.loc[hh].a_pvint, star(o.loc[hh].a_pvint, o.loc[hh].a_pvint_se),
            1e4 * o.loc[hh].a_pvint_se, 100 * o.loc[hh].a_main_pvint)
            for hh in [17, 18, 19, 20, 21, 22, 23, 0, 2]))

print("\nwrote", OUT / "thermal_persistence_by_hour.csv")
