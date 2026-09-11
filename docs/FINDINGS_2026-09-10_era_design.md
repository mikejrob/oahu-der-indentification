# The program-era design: a storage signature without the fabricated stock

MJR's insight, 2026-09-10: the near-zero contemporaneous coefficients on
BatteryBonus and SmartDER capacity are not a failure of the design. They are
what storage looks like. A battery absorbs midday generation, so it does not
appear as midday grid-load reduction; it reappears after sunset.

That converts a nuisance into the test. It also replaces `batt_mwh_cum`, which
is an era-weighted count of systems rather than a measured stock, with
`kw_<era>`, which is measured per-system capacity summed by program.

## Design

One cloud shock per day, measured at midday, traced across every hour:

    load(h,d) = f(season, hour, weekend, trend, temperature)
                + sum_era beta_era(h) * anomaly_mid(d) * kW_era(d)

`anomaly_mid` is the residual from regressing GHI on a natural spline in day of
year interacted with hour, averaged over 10:00-14:00. Temperature is the
station-based `t_pv`. Standard errors are Driscoll-Kraay at 28 lags.

Eras, with their growth windows, form a partition of the fleet:

    NEM/CGS          441 MW   grows 2013-2016, flat after   mostly PV only
    CSS/SmartExport  175 MW   grows 2017-2021               storage-bearing
    Storage era      149 MW   grows 2021-2024               BatteryBonus + SmartDER

Differences against NEM/CGS net out any channel common to all rooftop capacity.

## Result

Per installed MW, per 1,000 W/m2 of midday anomaly:

    window            NEM/CGS         CSS - NEM        Storage - NEM
    midday  9-16    -0.785 (0.123)   +0.547 (0.245)   +0.776 (0.309)
    evening 18-22   +0.209 (0.089)   -0.328 (0.170)   -0.184 (0.207)

Storage-era capacity gives 0.78 MW per MW LESS midday grid-load reduction than
PV-only capacity (t = 2.5), and more evening reduction, with the sign flipping
at sunset. Both windows are driven by the same midday shock, so the flip cannot
come from contemporaneous generation. The evening differences carry the right
sign but are imprecise on their own; the midday differences are significant.

The hour-by-hour profile (`data/derived/era_intraday_profile.csv`) shows the
sign flip landing exactly at sunset: the storage-minus-NEM difference runs
+0.18 at 17:00 and -0.15 at 18:00.

## Two things worth noting

**The PV-only response corroborates the pre-battery calibration.** NEM/CGS
midday is -0.785, against -0.791 from `18_prebattery_effective_mw.py` on
2013-2019 daylight blocks. Two designs with different samples, windows and
identifying variation agree to 0.006 MW per MW.

**The era gap has a simpler explanation than the report gives.** Appendix A.11
reads the difference between the pre-battery 0.79 and the battery-era 0.61 as
the behind-the-meter wedge plus post-net-metering tariffs. On this evidence it
is composition: the fleet average falls as storage-era capacity, which delivers
almost no midday grid-load reduction, takes a larger share. PV-only capacity
still returns 0.79 in the battery era.

**Only about a quarter of what storage absorbs comes back to the grid.**
Midday absorption of +0.78 against evening release of -0.18. The remainder is
behind-the-meter self-consumption and round-trip loss, which never crosses the
meter in either direction. That is the wedge, located in the era that generates
it.

## Limits

- Era is not randomly assigned. Households enrolling in Battery Bonus differ
  from 2013 net-metering adopters in house age, income and cooling equipment.
  The differencing removes channels common to rooftop capacity, not selection.
- CSS/SmartExport behaves like a storage program because it is one: Customer
  Self-Supply cannot export and Smart Export pays for evening delivery. Reading
  it as a PV-only era would be wrong.
- SmartDER holds 44 MW in a single year and cannot be separated; it is folded
  into the storage era.
- The NEM/CGS evening coefficient is +0.209 and significant: a sunny day leaves
  a warm evening and more air conditioning. It is differenced out, which assumes
  the channel is common across eras.
