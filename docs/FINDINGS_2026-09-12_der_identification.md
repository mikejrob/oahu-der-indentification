# Findings, 2026-09-10 to 2026-09-12: identifying rooftop PV and storage effects on Oʻahu load

Record of the identification work in this repository since the standard-error
and territory corrections (see FINDINGS_2026-09-10_standard_errors.md and
FINDINGS_2026-09-10_era_design.md). Scripts 20 to 34. Everything here is
provisional; each result names the check that would overturn it.

## 1. Data, as used in every result below

- Load: FERC 714 respondent 178, Oʻahu only, hourly 2006-01 to 2025-12, clock
  roll +1 h for 2006-2012, 0 for 2013-2020, -1 h for 2021-2025
  (`data/raw/panel_hourly_shifted.parquet`, built by 08). The 2025 year was
  added to the raw pull and carries the -1 h roll. Checked 2026-09-12: the
  pre-dawn ramp hour (6.36), evening peak hour (18.73) and April-September
  midday trough hour (12.40) for 2025 sit with 2021-2024 (6.38-6.42,
  18.69-18.95, 11.8-12.5). One boundary hour in 2013 carries roll +1.
- Radiation: NSRDB GOES v4, 264 Oʻahu cells, unweighted island mean, 2006-2025
  (`data/raw/_nsrdb_isl_YYYY.parquet`). Daytime-mean GHI is the mean over
  08:00-16:00. Bright-day anomalies in an island mean come largely from cloud
  over the mountains where there is little PV; a PV-weighted series is the
  obvious refinement and has not been built.
- Temperature and dewpoint: station-based, PV-weighted (`t_pv`, `td_pv`, 21).
- Stocks: permit records (`der_points.parquet`), cumulative kW by install date
  and vintage. Vintages are date-defined: NEM/CGS to 2016-12, CSS/SmartExport
  2017-01 to 2021-06, BatteryBonus 2021-07 to 2023-12, SmartDER 2024-01 on.
  At 2025-06-30: 441, 175, 105, 72 MW. The `batt_mwh` field in the permit
  records is a constant per vintage and is not used; `batt_text` is a flag
  true for 108 systems and is not usable.
- Battery energy (33): per system 13.5 kWh per 5 kW of PV rounded up (one
  Gen-2 Powerwall per 5 kW), on the storage-era vintages (B1: 576 MWh at
  2025-06-30, 3.25 MWh per MW) or additionally on half the CSS/SmartExport
  vintage (B2: 921 MWh). EIA-861M reports 263 MWh at 2025-06 but re-counts to
  491 MWh in 2026-03 with 5,300 customers added in two months, so its pre-2026
  level is incomplete by roughly 45 percent. Utility-scale storage is not in
  the load series (MJR: 714 demand is HECO sales).
- Vehicles (34): DBEDT Monthly Energy Data, Oʻahu registered passenger EVs,
  7,283 (2019-12), 13,930 (2021-12), 22,214 (2023-12), 31,205 (2025-12).
  `data/analysis/dbedt_oahu_vehicles_monthly.csv`.

## 2. What the weather-anomaly designs could and could not do

Battery Bonus discharge is a contractual obligation, the committed kW for two
consecutive hours in an assigned block inside 18:00-20:30 (Rule 31; Q&A in
`data/raw/programs`). It does not vary with weather, so no design that
identifies storage from radiation anomalies can see it. Four such designs
(22, 23, 24, 26, 27) returned significant storage coefficients overnight
where nothing can happen, and were set aside on that basis.

## 3. The anchored hour profile (28, 29)

Outcome load(h,d) - load(04:00,d); per-hour OLS; day-of-year spline, weekend,
linear trend, temperature, dewpoint, same-hour GHI; PV and storage-era PV as
levels. Newey-West, 28 lags. Sample 2010-01 to 2025-06 (the last permit date;
the storage stock is flat after it).

- Storage-era level at 19:00 and 20:00: -0.211 and -0.103 MW per MW, hour 21
  flat, overnight null. About 37 MW at 19:00 against the 40 MW cap.
- Only the linear trend passes the overnight placebo; spline trends absorb the
  ramp. That choice was made by placebo and a referee will call it selection.
- Weather split (29): notch about 20 percent shallower on dark days; noon
  storage-era coefficient smaller on dark days (solar charging, not grid
  top-up); overnight null.
- COVID-period dummies deepen the notch slightly and cut the evening PV level
  from +0.33 to +0.12 MWh per MW-day; year effects attenuate the notch and
  break the overnight placebo. See `anchored_profile_4am_linear.csv`.

## 4. Thermal persistence before rooftop PV (30)

2006-2010, PV under 40 MW, no storage. Same-day daytime radiation raises load
after dark conditional on the hour's temperature and dewpoint: about 8 MW per
100 W/m² at 20:00-23:00 (1.3-1.7 percent of load), about 3 MW overnight, with
the previous day adding 4-7 MW overnight. Lags 2 and 3 add about 1.5 each. A
lead of next-day radiation is not zero at 21:00-23:00 (about +2.4 to +3.2), so
roughly a third of the late-evening coefficient is weather-regime correlation
rather than persistence. Fine as a control, an upper bound as a structural
estimate. As a share of load the effect rose in 2016-2019 (2.1-2.3 percent)
and fell in 2021-2025 (1.2-1.7), the fall consistent with batteries
discharging more after bright days. `thermal_persistence_by_hour.csv`.

## 5. The combined specification, and the single-shock version (31, 32; R)

31 put the profile levels and the radiation interactions in one equation.
Uncentered radiation gave offsetting level and interaction pairs; same-hour and
daytime-mean GHI correlate at 0.96 at noon and cannot both be interacted.
32 is the working form:

    y ~ ns(doy,7) + we + hs + t_pv + t_pv^2 + td_pv
        + gd_a + gd1_a + gd2_a            uninteracted daily anomaly, today and two lags
        + PV + B                          hour profile per unit of stock
        + gd_a:PV + gd_a:B                radiation x stock

with gd_a the residual of daytime-mean GHI on ns(doy,7), load and radiation on
the same climatology (hour-specific because each hour is its own regression),
sandwich::NeweyWest lag 28. Variants: symmetric (A), bright and dark halves of
the shock (B), four vintage stocks (C), and B in MWh of battery (33).

Results that reproduce their separate estimates inside this one equation:
uninteracted evening response 6-8 MW per 100 W/m² as in 2006-2010; PV
pass-through -0.6 to -0.75 MW per MW per kW/m² through 9:00-16:00, the 0.61
of the report's estimator 2; storage-era pass-through near zero at 12:00-13:00
and about half the ordinary response in the afternoon; level notch -0.20 and
-0.09 at 19:00 and 20:00; notch about 20 percent deeper after a bright day;
storage terms null overnight (max |t| 1.3-1.5). The PV level at 02:00-03:00
is not null (about -0.025 per MW, t near 8); that is a placebo failure carried
from 28 and attributed to the trend. Starting the sample in 2006 breaks the
placebo across the board; the linear trend does not fit the recession years.

Per MWh of battery (33, B1): daylight level +1.54 MWh per MWh-day; 18-20
-0.107; 21-23 +0.082; overnight 0. Morning interaction about +0.3 MW per MWh
per kW/m², evening about -0.1.

Bright/dark split (B): for the average rooftop MW, dark anomalies pass through
at about -0.9 and bright ones at -0.3, which is not physics and is read as
spatial attenuation of the island mean on bright days. For storage-era
capacity, dark mornings LOWER grid draw (dark x BATT +1.5 at 10:00-12:00, net
+0.54): loads that switch on with sunshine and draw more than the PV surplus.
That is MJR's demand-response reading (cars, laundry, freer A/C) and it is the
one piece of evidence for it that does not rest on a level term. A pure
curtailment story predicts the opposite sign. The afternoon does not fit the
same story and is unexplained. In variant C the positive morning interaction
loads on the Smart DER vintage, eighteen months of data.

## 6. Energy account and what the anchor hides

Per MWh of battery per day, level coefficients summed: the grid sees 1.5 MWh
less daytime reduction than from PV alone, against 0.84 that one full charge
can absorb; the residual is about 10-14 kWh per household-day after allowing
for curtailment, one car's charge. The visible evening reduction is the
Battery Bonus block and nothing else: 77 percent of the 40 MW cap read raw,
about 140 percent read net of a +0.03 per MWh late-evening excess as induced
load. Hour 18 is short under any block assignment; a residual half-hour clock
error in 2021-2025 cannot be excluded.

The 04:00 anchor removes any discharge that is the same at hour h and at
04:00. A household with 22 kWh usable is still discharging at 04:00, so the
bulk of a two-Powerwall cycle is invisible to this design by construction. The
evening therefore bounds usable capacity from below at the commitment and
says nothing about the top. The falsifiable implication: raw 02:00-04:00 load
should have fallen 5-12 MW with the non-Battery-Bonus fleet, and it is flat.
Oʻahu EVs grew by 17,000 over 2021-2025; at 0.5-0.8 kW average overnight draw
per home-charging car that is 5-10 MW at 04:00, the same order. The two
cannot be separated in system data; the EV series interacted with hour is
the next control to add.

## 7. Appendix A.11 and A.12 of the report, against this evidence

| Claim | Status |
|---|---|
| 793 MW PV, about 250 MWh storage at mid-2025 | PV holds. Storage is not measured; EIA's re-count implies about 450 MWh and the sizing rule gives 576. |
| Pre-battery 0.79 MW per reported MW, s.e. 0.03 | Holds; Newey-West s.e. 0.031 at 28 lags. |
| Clock correction, 4 am anchor | Correction holds for all years. The anchor is inert to PV but not to overnight battery discharge (section 6). |
| Battery identified from midday radiation × storage, t = -4.9 | Does not hold; t = -1.6 under Newey-West, and the design cannot see contractual discharge. |
| 0.45 MWh per MWh per day, 19:00-22:00, peak 20:00 | Not supported. The notch is at 19:00-20:00 with hour 21 flat, matching Rule 31, and the per-MWh figure rests on a constant regressor. |
| PV 0.61 MW per MW at midday | Holds as a number; the same value reappears as the radiation × PV pass-through in 32. |
| 24 percent wedge; 11 MW low-sun excess | Not retested. Curtailment under non-export tariffs is an alternative to the wedge's interpretation. |
| A.12: 40 percent of new installs' midday output moved to evening, energy-conserving, "calibrated to the metered record" | Not supported. Per storage-era MW the visible evening return is about a tenth of the daytime shortfall, though the anchor hides overnight discharge. The calibration sentence should go. |

## 8. Assessment for publication

As it stands this is not an AEJ paper. The PV result is credible and known.
The storage result is one island, one treatment path, a level identified
against a trend chosen by placebo. The morning asymmetry and the contractual
block are the pieces that do not depend on that. Energy Journal or Energy
Economics are realistic; JAERE if a coordination-value exercise (observed
block versus optimal dispatch of the same fleet against system marginal cost)
is strong. Customer-level interval data from HECO is the paper the referees
will ask for; HECO has resisted sharing. This line is paused as of 2026-09-12
in favour of assessing the other candidate papers (PAPER_CANDIDATES_2026-09-10.md).

## 9. Open items, in order

1. Interact the DBEDT EV stock with hour in 32 (control for one named
   induced-demand channel; bound the overnight offset).
2. PV-weighted radiation anomaly from the 264 cells; re-run variant B. The
   bright-side attenuation should shrink.
3. Rule 31 block assignment: if HECO published the distribution of assigned
   blocks, hour 18 can be predicted rather than assumed.
4. Report repository: the Newey-West patches to 09, 18, 01 and METHODS_NOTES
   are uncommitted there; A.11 lines near 3496 (s.e.), 3518 (t-statistic)
   and 3481 (territory), and the A.12 calibration sentence, await MJR.
