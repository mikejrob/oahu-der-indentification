# Codebook

Analysis-ready panels in `data/analysis/`, built by
`analysis/20_build_analysis_dataset.py`. Coverage 2013-2024, the years with
continuous island radiation. Verified to reproduce the estimator output: the
noon PV regression run off `oahu_hourly_panel.csv` returns 0.6169 MW/MW
(s.e. 0.0136, n = 2,557), matching `09_estimator2_firmed.py`.

    oahu_hourly_panel.{csv,csv.gz,parquet}   105,183 rows x 39 cols
    oahu_daily_panel.{csv,parquet}             4,383 rows x 26 cols
    der_installs_by_era.csv                    daily cumulative installs by program

## Read this first: two variables are not what their names suggest

**`batt_mwh_cum` is not measured storage capacity.** In the source records
`batt_mwh` takes one flat value per program era, assigned to every system in
that era (NEM/CGS 0.000467 MWh, CSS/SmartExport 0.001738, BatteryBonus
0.006516, SmartDER 0.007819). It is not proportional to system size: regressing
it on era-specific rates times `kw_est` gives an R-squared of 0.034. The
cumulative series is therefore an era-weighted **count of PV systems**, scaled
so the island total reaches an assumed 250 MWh. The only field carrying direct
evidence of a battery, `batt_text`, is true for 108 of 121,246 systems and
0.86 of 249.7 MWh. Treat `batt_mwh_cum` as a program-era index, not a stock;
per-MWh magnitudes derived from it are artifacts of the four constants and the
250 MWh anchor. See `FINDINGS_2026-09-10_standard_errors.md`, addendum.

**`pv_mw_cum` is on an undocumented rating basis.** Neither the permit series
nor the utility's published totals states DC nameplate versus AC. Coefficients
estimated per *reported* MW are internally consistent, because the same series
carries through estimation and projection. Comparisons with outside figures
need the basis stated on both sides.

## Hourly panel — `oahu_hourly_panel`

One row per corrected-clock (date, hour) pair.

### Time and identifiers

| variable | type | definition |
|---|---|---|
| `date` | date | Calendar date, Hawaii Standard Time, **after** the Form 714 clock correction. |
| `year`, `month`, `day` | int | Components of `date`. Derived from the corrected clock, so they can differ from the reported timestamp at a year or month boundary. |
| `hour` | int 0-23 | Hour of day, HST, corrected clock. |
| `dow` | int 0-6 | Day of week, Monday = 0. |
| `ym` | int | `year*100 + month`; convenience key for year-by-month fixed effects. |
| `quarter`, `season` | int 1-4 | Calendar quarter. `season` is a duplicate kept because the estimators refer to it by that name. |
| `is_weekend` | 0/1 | 1 if `dow` >= 5. |
| `dt_hst` | timestamp | Original reported timestamp, HST, **before** correction. Kept so the roll can be undone. |
| `roll_h` | int | Hours added to `dt_hst` to obtain the corrected clock: +1 for 2006-2012, 0 for 2013-2020, -1 for 2021-2024. |
| `era_714` | text | Form 714 reporting format of the source record, `CSV` or `XBRL`. The format changes at 2021, coinciding with the clock shift. |

### Outcome

| variable | units | definition |
|---|---|---|
| `load_mw` | MW | Metered system demand for FERC Form 714 respondent 178, from PUDL's `demand_imputed_pudl_mwh`. Respondent 178 is **Oahu alone**: Maui Electric and Hawaii Electric Light have peak demand below the Form 714 reporting threshold of 200 MW and do not file. |
| `load_anchor3` | MW | That date's `load_mw` at hour 3, the pre-dawn reference. Sun down, batteries at overnight reserve. |
| `load_anom3` | MW | `load_mw - load_anchor3`. Removes demand drift (efficiency, electric vehicles, the economy) without touching the distributed signal. **This is the anchored outcome the design intends.** |
| `load_anchor4`, `load_anom4` | MW | Same at hour 4. Hour 4 was the anchor before the clock correction; hour 3 is its corrected counterpart. Both are provided so the choice can be tested. |

### Radiation and weather

Island mean over the 264 NSRDB grid cells inside the Oahu bounding box
(21.20-21.75 N, 158.35-157.60 W), GOES-aggregated v4.0.0, half-hourly averaged
to clock hour, UTC converted to HST. Radiation is **not** clock-shifted; only
the load series is.

| variable | units | definition |
|---|---|---|
| `ghi` | W/m2 | Global horizontal irradiance, contemporaneous with `hour`. |
| `temp` | deg C | Air temperature, contemporaneous. |
| `ghi_midday` | W/m2 | Mean `ghi` over hours 10-14 of the same date. Constant within a date. |
| `temp_midday` | deg C | Mean `temp` over hours 10-14 of the same date. |
| `temp_evening` | deg C | Mean `temp` over hours 17-20 of the same date. |
| `ghi_daily`, `temp_daily` | W/m2, deg C | 24-hour means for the date. |

### Installed distributed capacity

Cumulative as of the date, from permit and interconnection records.

| variable | units | definition |
|---|---|---|
| `pv_mw_cum` | MW | Cumulative installed rooftop PV, summed from per-system `kw_est`. Genuine per-system capacity. Range 216-765 MW over 2013-2024. |
| `batt_mwh_cum` | "MWh" | Cumulative storage **as allocated by program era**. See the warning above. Range 17-228 over 2013-2024. |
| `sys_<era>` | count | Cumulative number of systems installed under each program era: `NEM_CGS`, `CSS_SmartExport`, `BatteryBonus`, `SmartDER`. |
| `kw_<era>` | kW | Cumulative installed kW under each program era. |

The era columns are the honest storage signal. `BatteryBonus` opened mid-2021
and paid specifically for evening discharge, so `sys_BatteryBonus` and
`kw_BatteryBonus` move on a policy timetable rather than with rooftop PV, which
is the variation an event study would use.

### Constructed interactions

Provided because the estimators use them; all are simple products.

| variable | definition | used for |
|---|---|---|
| `ghi_x_pv` | `ghi * pv_mw_cum` | The PV response. Coefficient times 1,000 is MW of grid-load reduction per reported MW at 1,000 W/m2. |
| `middayghi_x_batt` | `ghi_midday * batt_mwh_cum` | The storage term. Carries the caveat above. |
| `middayghi_x_pv` | `ghi_midday * pv_mw_cum` | Control that separates a storage effect from PV-stock growth. Including it removes the storage term's significance. |
| `middayghi_x_sysBB` | `ghi_midday * sys_BatteryBonus` | Reduced-form storage treatment on a measured system count. |

## Daily panel — `oahu_daily_panel`

One row per date. Radiation, weather and stock variables are the same
definitions as above, taken once per date.

| variable | units | definition |
|---|---|---|
| `load_mean`, `load_peak`, `load_min` | MW | Mean, maximum and minimum `load_mw` across the 24 corrected-clock hours. |
| `load_midday` | MW | Mean `load_mw` over hours 10-14. |
| `load_evening` | MW | Mean `load_mw` over hours 19-22, the sun-down window in which PV output is zero. |
| `lowsun` | 0/1 | 1 if `ghi_midday` is at or below the 20th percentile of the 2013-2024 distribution. 877 of 4,383 days. |
| `lowsun_threshold_wm2` | W/m2 | The threshold itself, 592. Constant; stored so the cut is reproducible. |

## `der_installs_by_era.csv`

Daily cumulative `sys_<era>` and `kw_<era>` from the first install on record to
2024-12-31, forward-filled to a complete daily index. The source of the era
columns merged into both panels.

## Known limits

1. **No cross-island placebo.** Form 714 carries no Maui or Hawaii Island
   respondent, for the threshold reason above.
2. **Air conditioning co-moves with radiation.** Temperature enters the
   estimators as a quadratic. Reduced, not eliminated.
3. **Serial correlation.** Daily residuals are correlated; the score
   autocorrelation is still near 0.27 at 28 lags. Default OLS errors understate.
   Use Newey-West, or Driscoll-Kraay where a regression carries several hours
   per date.
4. **PUDL vintage.** Built from the current stable release, which spans
   2006-2025 with 175,319 hourly rows; an earlier vintage used in the report had
   166,559 rows through 2024. Point estimates shift slightly against published
   figures for this reason.
5. **`dni` and `dhi` are absent.** The fast extractor pulls only `ghi` and
   temperature to halve the transfer.
