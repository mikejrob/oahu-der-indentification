# Newey-West standard errors on the rebuilt panel: what survives

Run 2026-09-10 on a panel rebuilt from public sources (PUDL FERC 714 stable
release; NSRDB via NREL's public S3). No HPC input.

## Reproduction

The rebuilt pipeline matches the published record where it should:

| Quantity | Published | Rebuilt |
|---|---|---|
| Installed PV / storage at 2025-06-30 | 793 MW / ~250 MWh | 793.3 MW / 249.7 MWh |
| Clock-shift validation, night-min hour by block | 3 / 3 / 3 | 3 / 3 / 3 |
| Corrected 2021-24 midday trough vs solar noon | 12 vs 12 | 12 vs 12 |
| Pre-battery GHI x PV coefficient | -0.7913 | -0.7913 |
| Noon PV response | 0.613 | 0.617 |

One difference to carry: the current PUDL release spans 2006-2025 with 175,319
hourly rows, against 166,559 through 2024 in the earlier methods log. The
estimators filter to radiation years, so the effect is small, but the battery
point estimate does move (below) and this is a candidate reason.

## 1. The PV response survives everything

Noon 0.617 MW per reported MW at 1,000 W/m2. Newey-West at 8 lags gives a
standard error of 0.0136 at reference scale (t = -45). The score
autocorrelation runs 0.19 at lag 1, 0.32 at lag 7, 0.27 at lag 28, 0.20 at
lag 56, and dies by lag 90, so the 4(T/100)^(2/9) rule (8 lags) is too short.
The standard error rises monotonically with bandwidth:

    lags      0      7     14     28     56     90
    se   0.0122 0.0135 0.0143 0.0160 0.0189 0.0212

At 90 lags the error is 74 percent above OLS and t is still 29. Day-of-week
effects move the point estimate by 0.002, confirming orthogonality to weather,
and cut the residual autocorrelation at lag 7 from 0.564 to 0.191.

## 2. The pre-battery calibration survives

-0.7913 (published), and the month-clustered standard error of 0.033 sits
where a 28-to-56 day Newey-West bandwidth lands (0.031 to 0.035). Appendix
A.11's reported "s.e. 0.03" stands. With day-of-week effects the coefficient
is -0.7716 and the residual autocorrelation at lag 7 falls from 0.772 to 0.302.

## 3. The battery result does NOT survive

The published t of -4.9 was computed with OLS standard errors. The day-mean
residual carries an AR(1) coefficient of 0.55 and remains at 0.35 by lag 56.
With Driscoll-Kraay errors the t-statistic on the current specification is:

    lags      0      8     14     28     56     90
    t     -4.34  -1.57  -1.40  -1.23  -1.05  -0.95

The coefficient is not distinguishable from zero at any defensible bandwidth.

Richer specifications do not rescue it. Adding day-of-week leaves t at -1.29
(28 lags). Adding year-by-month effects raises the coefficient from
-1.42e-4 to -3.03e-4 and t to -3.31, but the implied evening delivery becomes
0.864 MWh per installed MWh per day, which exceeds the physical bound of 0.619
(round-trip efficiency 0.86, reserve 0.20, usable depth 0.90). The
specification that attains significance is the one that fails the energy check.

The reason is collinearity. Installed PV and installed storage correlate at
0.95 in levels and at 0.95 across year-month means over 2018-2024. Controlling
for midday radiation interacted with the PV stock alongside the battery
interaction returns t = -0.95 at 28 lags. The evening channel does not separate
the two stocks.

    spec                                  coef x1e4   t(OLS)   t(28 lags)   MWh/MWh
    current (hour + season + year FE)        -1.42     -4.34        -1.23     0.405
    + day-of-week                            -1.48     -5.22        -1.29     0.422
    + dow + year-by-month FE                 -3.03     -8.57        -3.31     0.864  <- over cap
    + dow + ym FE + midday GHI x PV stock    -2.68     -2.28        -0.95     0.763

## Three readings, and how to choose

1. **The storage denominator is understated.** The 250 MWh island calibration
   is recorded as unverified. If the year-by-month estimate is the right
   coefficient, the implied stock is about 1.4 times the assumed one. Testable
   against EIA-861 and the Battery Bonus enrollment record.
2. **The battery interaction absorbs PV-stock growth.** Supported by the fourth
   row: significance disappears when the PV interaction enters.
3. **The design cannot separate the two.** Then the result is a bound, not an
   estimate.

The decisive test needs variation that moves storage without moving rooftop PV.
Hawaii's Battery Bonus program, which opened mid-2021 and paid for
evening discharge specifically, is the natural candidate: an enrollment step
that shifts storage adoption on its own timetable. `der_by_era.csv` carries the
program mix that would support an event study.

## Consequences for the report

- Appendix A.11's "(t = -4.9)" on the battery term does not hold and must change.
- The 0.45 MWh per installed MWh figure rests on the same coefficient. The
  net-load model's 40 percent midday-to-evening shift is calibrated separately
  against the metered record (A.12) and A.11 is cited as corroboration, so the
  model input is not directly derived from this coefficient. The corroboration
  claim is what weakens.
- Nothing here touches the PV coefficients, the wedge, the clock correction, or
  the low-sun-day result, which rest on the PV term and on within-year
  comparisons.
