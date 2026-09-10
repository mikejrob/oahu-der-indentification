# Oʻahu behind-the-meter demand reshaping — methods notes (running log)

Author: automated analysis, session 2026-07. Feeds a battery load-shift parameterization
for a Switch capacity-expansion model and an estimate of behind-the-meter true-demand growth.
**Do not overclaim precision the identification cannot support.** Every assumption flagged.

## Data
- **Load:** PUDL FERC 714 hourly, `respondent_id_ferc714_csv == 178` (only Pacific/Honolulu
  respondent). `demand_imputed_pudl_mwh`. `datetime_utc` (tz-naive UTC) → localize UTC →
  convert `Pacific/Honolulu`. Coverage **2006–2024** (166,559 hourly rows after cleaning).
  Mean load ≈ 839 MW.
- **Installs:** `oahu-grid .../der_points.parquet`. `kw_est` per-system kW → cumsum/1000 = installed MW.
  `batt_mwh` per-system → cumsum = installed MWh. Final cumulative (2025-06-30):
  **PV ≈ 793 MW, battery ≈ 249.7 MWh.**
- **Radiation:** NSRDB hourly. On disk only for **2007, 2008, 2018, 2019** (~13 grid points each,
  hourly GHI/DHI/DNI/Temperature, HST local-standard, 30-min-centered). Full 2006–2024 needs the
  NREL PSM3 API.

## BLOCKERS (read first)
1. **NSRDB radiation coverage.** Only 2007/2008/2018/2019 on disk. **NREL_API_KEY is NOT SET**
   (checked env, `~/.nrel`, `~/.config`, oahu-grid tree, gtg_group tree — none found). The API
   is also unreachable from the Bash sandbox (HTTP 000). **The battery-era years 2021–2024 —
   the critical window for identifying the battery evening-shave — have NO on-disk radiation.**
   The radiation-identified battery coefficient (Estimator 2, battery term) therefore CANNOT be
   estimated yet. Estimator 2's PV term and the full pipeline are validated on 2018/2019.
   → ACTION NEEDED: obtain an NREL API key and pull GHI for **2020–2024** (and ideally 2006,
   2009–2017 to fill the panel), ~13 Oʻahu grid points, hourly.
2. **Cross-island placebo BLOCKED.** FERC 714 parquet has no separate Maui Electric / Hawaii
   Electric Light respondent in Pacific/Honolulu tz — only 178, which is Oahu alone.
   MECO and HELCO fall under the Form 714 reporting threshold (peak demand below
   200 MW), so neither files. The falsification test on other islands cannot be run
   from this dataset. Would need island-level load from HECO filings / EIA-930
   balancing-area data.
3. **714 format break at 2021** (CSV→XBRL). Flagged per-row (`era_714`). Level shifts across the
   break are absorbed by year effects but any hour-shape artifact of the reformat is a caveat.
4. **Battery absolute scale UNVERIFIED.** oahu-grid calibrated batt MWh to a 250 MWh island total
   (our cumsum = 249.7, era totals sum to 245 — internally consistent but the 250 anchor is the
   assumption). All battery-per-MWh results scale inversely with this; report sensitivity.

## Panel construction
(quarter × hour-of-day × year) cells. 4am-anchor: subtract each (year, day) 4am HST load from every
hour before aggregating, per prior finding that 4am is a clean no-PV / batteries-at-reserve anchor
(naive coefs there ≈ 0). Files: `panel_qtr_hour_anchored.csv`, `panel_hourly_with_installs.parquet`.

## RESULTS

### Estimator 1 — slow-trend dose-response (BIASED baseline) [estimator1_coeffs_by_hour.csv]
4am-anchored anomaly ~ C(quarter) + PV_cum + Batt_cum, per hour.
- 4am anchor confirmed clean (coefs = 0 by construction).
- **Noon PV = -0.65 MW/MW** (h=12); sensible capacity factor < 1.
- Evening battery discharge concentrated **16-21h, peak -0.61 at 20h**; shape well-identified.
- Collinearity pathology visible and expected: midday battery coef strongly POSITIVE
  (+0.87 at 11h = impossible "charging", really PV self-consumption); late-night positive
  battery coefs (00-03h +0.14..+0.22, 22-23h +0.26) = EV charging misattributed. This is
  the biased baseline the design exists to fix.

### Estimator 2 — radiation-identified (PRIMARY) [estimator2_pv_term.csv, estimator2_summary.txt]
Identified off day-to-day (cloud-driven) GHI variation; years 2007,2008,2018,2019.
- **PV term is clean and stable: -0.60 to -0.65 MW load-reduction per MW installed at 1000 W/m2**,
  flat across midday hours (h=9-15). This is identified WITHOUT the slow install trend and is
  not confounded by EV growth.
- **Cross-validation win:** this exogenous estimate (-0.60 @ noon) MATCHES Estimator 1's
  collinear noon coef (-0.65). Mutual corroboration -> the PV conversion coefficient is trustworthy.
  Recommended PV conversion for the net-load model: **beta_PV ~ 0.61-0.65 MW/MW** (per MW installed
  at full sun; equivalently the daily capacity-factor-weighted integral below).
- **Battery term NOT identifiable here (BLOCKER):** by 2018/19 only ~49-59 MWh of the eventual
  ~250 MWh was installed (73% installed after 2019). The battery term coef came out small,
  wrong-signed and marginally significant (+0.00025, se 0.00013) = residual PV-self-consumption
  leakage, exactly as expected with near-zero battery-era radiation. Estimating the battery
  evening-shave per MWh REQUIRES 2020-2024 NSRDB radiation (Blocker 1).

### Evening-shift parameterization for Switch [evening_shift_parameterization.csv, paramz_summary.txt]
- **Discharge SHAPE (hourly weights, 16-21h), from the clean Estimator-1 evening signal:**
  16h=0.127, 17h=0.184, 18h=0.182, 19h=0.159, 20h=0.187, 21h=0.161  (sum=1).
- **TOTAL shifted energy per installed MWh:** the raw regression implies 3.24 MWh/MWh, which
  VIOLATES the physics cap (a battery cannot deliver >1 MWh per installed MWh per cycle). The
  design's own sanity check rejects the raw number (it is inflated by PV self-consumption + load
  growth in the collinear coef). Use the physics bound:
  **E_shift = rte*(1-reserve)*usable = 0.86*0.80*0.90 = 0.62 MWh delivered per installed MWh per day.**
  RECOMMENDED for Switch: 0.62 MWh/MWh distributed over the evening by the shape weights above.
- Residential vs commercial: der_by_era.csv program mix is overwhelmingly residential rooftop
  (NEM/CGS + CSS/SmartExport + BatteryBonus are residential DER programs); the evening-shave is a
  residential-storage phenomenon. No commercial-storage split is separable from these data.
- Battery-scale (250 MWh UNVERIFIED) sensitivity: per-MWh numbers are INVARIANT to the calibration;
  only the ISLAND-TOTAL shifted energy (= per-MWh x installed MWh) scales linearly with it.

### g - beta induced-demand wedge [g_minus_beta_wedge.csv, paramz_summary.txt]
Per installed MW, daily energy:
- g (physical rooftop generation, PR=0.80, from NSRDB GHI) = **4.35 MWh/day/MW**
- beta (grid load reduction, radiation-identified PV term integrated over daylight) = **3.23 MWh/day/MW**
- **g - beta = 1.12 MWh/day/MW = 25.7% of generation** = behind-the-meter induced demand
  (EVs/appliances charged from own solar) + inverter/storage losses that never appear in grid load.
- Uncertainty: beta 3.23 +/- 0.07 (regression); g band (PR 0.75-0.85) [4.07, 4.62];
  **wedge band ~ [0.78, 1.45] MWh/day/MW.**
- Island total induced demand rises 21 -> 312 GWh/yr (2010->2024), driven by rising installed MW
  (per-MW wedge held constant — no battery-era radiation to re-estimate it year-by-year).

## FILES
- 01_build_panel.py -> load_hourly_oahu.parquet, installs_cumulative_daily.csv,
  panel_hourly_with_installs.parquet, panel_qtr_hour_anchored.csv
- 02_estimator1_baseline.py -> estimator1_coeffs_by_hour.csv
- 03_load_nsrdb.py -> nsrdb_oahu_island_hourly.parquet, nsrdb_oahu_daily_midday.csv
- 04_estimator2_radiation.py -> estimator2_pv_term.csv, estimator2_battery_term.csv, estimator2_summary.txt
- 05_wedge_and_paramz.py -> evening_shift_parameterization.csv, g_minus_beta_wedge.csv, paramz_summary.txt
- 06_figure_netload.py -> fig_netload_by_era.png

## IDENTIFICATION CAVEATS (do not overclaim)
1. PV term is credible (exogenous cloud variation, cross-validated). Battery term is NOT yet
   estimated for lack of battery-era radiation; the evening SHAPE is trusted, the per-MWh ENERGY
   is set by physics not by the (collinear) regression.
2. AC confound handled by flexible temp + temp^2 + wind controls, and EVENING temp specifically
   for the battery term; not fully eliminated (cloud dips co-move with temp somewhat).
3. EV growth confounds the slow-trend battery coef (late-night positive coefs); the radiation
   design is what removes it, once battery-era radiation exists.
4. Respondent 178 is Oahu alone (MECO and HELCO are below the 200 MW Form 714
   reporting threshold and do not file), so the load series and the Oahu install series
   cover the same territory; cross-island placebo impossible for the same reason
   (Blocker 2). 714 CSV->XBRL break at 2021 (Blocker 3). 250 MWh battery calibration
   UNVERIFIED (Blocker 4) - could not corroborate against EIA-861 (API/web unreachable from this
   environment); per-MWh results are robust to it, island totals are not.
5. g-beta per-MW wedge estimated on 2007/08/18/19 only and held constant over time.

---
## UPDATE (2026-07-25): BATTERY-ERA RADIATION ADDED — BATTERY TERM FIRMED

Battery-era NSRDB radiation (2020-2024) was pulled from NREL's public S3 bucket (bypassing the
API), file `nsrdb_oahu_island_hourly_2020_2024.parquet` (built by `07_extract_nsrdb_s3.py`).
Combined with on-disk 2018/2019 -> **continuous radiation 2018-2024**. Blocker 1 is CLEARED for
the battery-era window (2006-2017 radiation still absent, but that is the pre-battery baseline).

### FERC 714 clock-shift correction (NEW, applied before radiation alignment)
Per `oahu-grid/notes/oahu-ferc714-hourshift.md`: integer-hour roll on the LOAD, calibrated on
battery-INERT hours (night-min / morning ramp), NOT the evening peak (which would absorb the
battery signal). Roll: **+1h 2006-2012, 0 2013-2020, -1h 2021-2024.** Radiation NOT shifted.
- INDEPENDENTLY VALIDATED here (`08_..`, `hourshift_validation.txt`):
  - night-min hour was 2/3/4 by block -> after roll aligns to **3/3/3**.
  - 2021-24 corrected net-load midday trough sits at **hour 12 = NSRDB solar noon** (un-corrected
    was 13h, +1h late). The -1h roll fixes it; residual trough drift with installed MWh is the
    PRESERVED battery signal.
- NOTE: the earlier "4am clean anchor" was the SHIFTED 3am reference-block anchor in 2021-24 data.
- Also supersedes an earlier caveat: the hourshift note documents respondent 178 as HECO Oahu-only
  (not consolidated). Cross-island placebo still BLOCKED (no Maui/Hawaii-Island respondents in 714).

### Estimator 2 FIRMED [09_estimator2_firmed.py, estimator2_*_firmed.csv, estimator2_battery_shape.csv]
Radiation years 2018-2024, clock-corrected load.
- **PV term (firmed): noon = -0.61 MW/MW**, smooth & near-symmetric around solar noon (-0.41 @7h
  to -0.70 @15h; mild afternoon skew = real temp/tilt). Matches the 2007/08/18/19 estimate (-0.60)
  and Estimator-1 (-0.65). Spec: hour-by-hour, C(season)+linear secular trend+temp+temp^2+ghi_x_pv.
  (Year FE was DROPPED for the PV term: within-year PV drift is only ~30-50 MW vs 476->765 between
  years, so year FE would eat the PV level and leave ghi_x_pv collinear with the ghi control and
  corrupt the shape. A linear secular/EV trend replaces it.)
- **Battery term (FIRMED, the key new result):** evening load in the CLEAN sun-down window
  **19-22h** (PV output ~0, so same-day midday GHI acts only through the battery) ~ hourFE +
  season + yearFE + evening-temp + evening-temp^2 + ghi_midday + midday_GHI x Batt_installed.
  - pooled coef **-1.60e-4 MW per (W/m2 * MWh), t = -4.86** (correct sign: sunny midday -> fuller
    battery -> lower evening load). Every clean-window hour significant (t = -2.0 to -3.1).
  - at mean midday GHI 711 W/m2 -> **0.114 MW lower evening load per installed MWh (window avg)**.
  - **Discharge SHAPE (sun-down 19-22h weights):** 19h=0.219, 20h=0.322, 21h=0.250, 22h=0.209.
  - hours 16-18 excluded from the shape/energy (still have direct sun in HST summer -> midday-GHI
    contaminated by contemporaneous PV).

### ENERGY-CONSERVATION CHECK — NOW PASSES
Radiation-identified evening discharge = **0.454 MWh delivered per installed MWh per day**,
<= physics cap rte*(1-reserve)*usable = 0.86*0.80*0.90 = 0.619. **PASS.**
(The collinear Estimator-1 gave 3.24 MWh/MWh, which FAILED the cap by 5x; radiation identification
removes the PV-self-consumption + load-growth contamination. This is the headline validation.)

### Evening-shift parameterization for Switch (FIRMED) [evening_shift_parameterization_firmed.csv]
- **Energy: 0.45 MWh delivered per installed MWh per day** (radiation-identified, passes physics).
- **Shape (sun-down 19-22h):** 0.219 / 0.322 / 0.250 / 0.209, peak at 20h.
- Residential: der_by_era mix is residential rooftop DER; evening-shave is residential storage.
- Per-MWh energy & shape INVARIANT to the 250-MWh (UNVERIFIED) calibration; island totals scale
  linearly with it.

### g - beta wedge FIRMED (time-varying) [g_minus_beta_wedge_firmed.csv]
Now computed per YEAR (2018-2024) with battery-era radiation; g uses each year's GHI, beta the
firmed PV term.
- g ~ 4.1-4.7 MWh/day/MW; beta ~ 3.1-3.6; **wedge g-beta ~ 0.99-1.13 MWh/day/MW = ~24% of
  generation, stable across years.**
- Island induced demand **182 -> 292 GWh/yr (2018 -> 2024)**, driven by installed MW.
- CAVEAT: g-beta mixes induced demand with inverter/storage losses -> UPPER bound on net new
  behind-the-meter consumption. PR=0.80 moves g +/-6%.

### FILES (added this update)
07_extract_nsrdb_s3.py, nsrdb_oahu_island_hourly_2020_2024.parquet (provided);
08_rebuild_panel_hourshift.py -> panel_hourly_shifted.parquet, hourshift_validation.txt;
09_estimator2_firmed.py -> estimator2_pv_term_firmed.csv, estimator2_battery_firmed.csv,
  estimator2_battery_shape.csv, estimator2_firmed_summary.txt;
10_wedge_paramz_firmed.py -> evening_shift_parameterization_firmed.csv,
  g_minus_beta_wedge_firmed.csv, paramz_firmed_summary.txt;
fig_netload_by_era.png (regenerated on clock-corrected panel, 3am-anchored).

### REMAINING CAVEATS
1. Battery term identified over 2018-2024 with battery 42->228 MWh; credible (t=-4.86) but the
   pre-2018 battery era has no radiation (immaterial: battery was ~0 then).
2. AC confound handled by evening-temp + temp^2 controls in the battery window; cloud-driven GHI
   dips co-move slightly with temp -> residual, not eliminated.
3. Cross-island placebo still BLOCKED (no Maui/Hawaii-Island 714 respondents).
4. 250-MWh battery calibration UNVERIFIED (could not reach EIA-861 from this environment);
   per-MWh results robust, island totals scale with it.
5. g-beta is an UPPER bound (includes inverter/storage losses); 2006-2017 radiation absent so the
   wedge is 2018-2024 only.

---
## UPDATE (2026-07-25b): RADIATION EXTENDED 2013-2024 + TWO NEW ANALYSES

Radiation coverage extended to a CONTINUOUS 2013-2024 island series via the S3 byte-range method
(11b_extract_nsrdb_fast.py, one year per process run 12-way parallel; merged by 11c). Validation:
S3 2018 island GHI mean (217) matches the independent on-disk 2018 CSVs (214). Per-cell midday-GHI
climatology saved for all 264 Oahu cells x 12 years (Task B).

### TASK A -- low-sun-day grid-defection [14_taskA_lowsun_defection.py, TASK_A_NOTES.md, fig_taskA_lowsun_excess.png]
PRIMARY spec = year-FE + low-sun kink by era (within-year identified; secular/EV trend absorbed,
cannot leak into the low-sun coefficient):
- low-sun-day excess load: **-27 MW (2013-16) -> +4.4 MW (2017-20) -> +11.3 MW (2021-24, t=2.81).**
  Cloudy days flipped from load-SUPPRESSED to load-ELEVATED as behind-the-meter PV+storage grew =
  the grid-defection convexity the hypothesis predicts.
- Reliability: the +11.3 MW low-sun excess OFFSETS ~16% of the naive 69 MW "low sun = low daytime
  demand" relief. Net daytime load on a dark day is still below a sunny day, but the grid sees ~11 MW
  MORE than a linear-in-CF netting predicts, and the gap grows with the fleet -> a firm-capacity
  stress that a linear net-load model understates.
- SKEPTICAL CAVEATS: the pooled linear-trend spec gives a larger lowsun_x_pv (+0.096 MW/MW,
  t=7.53) but that t OVERSTATES confidence (monotone-with-time confound); the per-year residual
  pass is noisy (corr +0.20, ns). The year-FE era result (+11.3 MW) is the defensible number.
  Temperature/AC on cloudy days controlled (temp+temp^2), not eliminated.

### TASK B -- install-location / zone-weighted radiation [13_+15_, TASK_B_NOTES.md, fig_taskB_weighted_radiation.png]
- Installed distributed PV by zone built and cross-checked EXACTLY vs der_by_era.csv (793.3 MW).
  Fleet concentrated in Ewa_PearlHarbor (258 MW) + Honolulu_South (244 MW).
- Per-cell midday GHI (264 cells) x cumulative-installed-MW weighting vs island-uniform mean:
  **2024 weighted/uniform ratio = 0.9907 (-0.93%).** Install-weighted resource is ~1% BELOW uniform
  (the big install zones are not the sunniest; leeward-sunny intuition did NOT hold).
- Implied DistPV CF = 0.1805 vs the model's 0.1822 (annual mean of DistPV rows in
  inputs/variable_capacity_factors.csv). **Difference 0.9% < 2% -> zone-weighting is IMMATERIAL;
  island-uniform radiation is adequate for the netting calibration.**
- CAVEATS: per-cell metric is midday-GHI mean (11-13h), a CF proxy; EIA-861 net-metering
  cross-check NOT reachable from this environment (der_by_era is the internal control, reconciles);
  250-MWh battery scale UNVERIFIED (does not affect PV-location weighting).

### FILES (this update)
11b_extract_nsrdb_fast.py, 11c_merge_nsrdb.py -> nsrdb_oahu_island_hourly_2013_2019.parquet,
  nsrdb_oahu_cell_midday_ghi_by_year.csv, nsrdb_oahu_cells.csv;
13_taskB_zone_installs.py -> der_zone_cumulative_by_year.csv, der_points_latlon_cell.parquet,
  taskB_zone_install_totals.txt;
14_taskA_lowsun_defection.py -> taskA_daily_panel.csv, taskA_regression.txt,
  taskA_lowsun_by_year.csv, fig_taskA_lowsun_excess.png;
15_taskB_weighted_radiation.py -> taskB_weighted_vs_uniform_radiation.csv,
  fig_taskB_weighted_radiation.png; 16_write_task_notes.py -> TASK_A_NOTES.md, TASK_B_NOTES.md.

---
## UPDATE (2026-07-25c): FORECAST-VS-ACTUAL APPENDIX EVIDENCE [17_appendix_forecast_vs_actual.py]

Assembled HECO distributed-PV forecast vintages vs realized Oahu adoption
(appendix_forecast_vs_actual.csv, fig_heco_forecast_vs_actual.png, APPENDIX_forecast_evidence.md).

VERIFIED HEADLINE: PSIP 2016 (docket 2014-0183, digitized chart; 2016 anchor validates against
actuals to 0.7%) projected 770 MW by 2034; actual Oahu hit 765 MW at end-2024 = a DECADE early.
Slopes with windows attached: PSIP steady-phase (2021-45) 11.2 MW/yr vs realized (2020-24)
42.4 MW/yr = 3.8x; same-window (2016-24) 27.1 vs 40.5 = 1.5x. (The "4x" shorthand needs the
2021-45-vs-recent framing; same-window is 1.5x.)

IGP "DER_BESS" SERIES RESOLVED AS NON-COMPARABLE: 2024 value 1,115 MW exceeds Oahu-only PV
(765) by 1.46x; scale consistent with ALL-TERRITORIES DER and/or PV+BESS bundle (HECO 2025 comms
cite 1,186 MW forecast by 2030 all-territories vs series' 1,293 @2030). Working label "IGP 2020"
(Compare_Loads.ipynb); citable vintage = 2023 IGP Final Report (docket 2018-0165, D&O 40651).
Presented separately with caveat, EXCLUDED from headline. On its own terms the IGP vintage is
far more realistic than PSIP 2016 (stated plainly in the appendix).

OUR TRAJECTORIES VERIFIED AGAINST INPUTS: dgb/dgs/dga = conservative/realistic/accelerated;
2027 starts 800/820/840 exact; 2050 OPERATING (net 30-yr retirements) 1000/1560/2120 exact
(= cumulative builds 1674/2234/2794 minus 674 MW pre-2020 base); accelerated = 2*realistic -
conservative exact. Gross build rates 2028-50: 38.0/61.5/85.0 MW/yr = ~1x/1.5x/2x the realized
2020-24 rate (42.4) -- stated plainly in the appendix (conservative continues the recent rate
in gross terms; accelerated assumes double it).

DATA CAVEATS FLAGGED: (i) coordinator-referenced heco_pv_summary_series.csv does NOT exist on
disk (no oahu-grid/data/raw/heco/ at all) -- der_points is the actuals, corroborated by HECO
comms (+61 MW 2024 all-territories ~ Oahu +44); (ii) der_points system COUNTS (118k Oahu
end-2024) exceed HECO's active-system count (114k all-territories) -> records are permits/events,
not active interconnections; MW used, counts not; (iii) WebSearch WORKS from this environment
(WebFetch/DNS does not); verification limited to press-release-level numbers, PSIP chart values
not re-verified against PSIP PDF tables.

---
## UPDATE (2026-09-10): STANDARD ERRORS ON A NEWEY-WEST BASIS + TERRITORY SETTLED

**Territory.** Respondent 178 is Oahu ALONE. Maui Electric and Hawaii Electric Light
fall below the Form 714 reporting threshold (peak demand under 200 MW) and do not
file, so nothing from the other islands enters 178. Earlier notes in this file and
the docstring of `01_build_panel.py` described 178 as a consolidated, Oahu-dominant
series at roughly 75 percent of statewide load. That reading was wrong and is
corrected in both places. The load series and the Oahu install series cover the same
territory, so the per-MW coefficients carry no attenuation from a territory mismatch,
and the island totals in the wedge section are Oahu totals.

**Standard errors.** The estimators previously reported default OLS errors (09) and
month-clustered errors (18). Daily load residuals are serially correlated, so both
were the wrong basis: OLS errors are too small, and clustering by month imposes an
arbitrary block boundary on a process that decays continuously. Both scripts now use
Newey-West:

- Per-hour regressions (PV term in 09, battery shape in 09): one observation per
  date, rows sorted in time order, `cov_type="HAC"`.
- Regressions carrying several hours per date (pooled battery window in 09, the
  three daylight blocks in 18): Driscoll-Kraay, `cov_type="hac-groupsum"` with
  `time` the date index — Newey-West across days after aggregating within a day,
  which handles the within-day correlation the plain HAC estimator would miss.
- Truncation lag from 4*(T/100)^(2/9) (Newey and West 1994). At T = 2,557 days this
  gives 8 lags. Both scripts print a bandwidth sensitivity at 4, 8, 14, and 30 lags.

Point estimates are unchanged; only the errors move. Expect them to widen.

**Display bug fixed.** `estimator2_firmed_summary.txt` printed `se` on the
coefficient scale beside `mw_per_mw_at_ref`, which is 1,000 times larger, so the
column rounded to 0.0000 and read as impossible precision. The summary now prints
`se_at_ref` on the same scale as the point estimate, with a t-statistic and the lag
count. The CSV always held the right numbers.

**To regenerate** (Koa; the panels are on Lustre, not in the repository):
    python3 analysis/09_estimator2_firmed.py
    python3 analysis/18_prebattery_effective_mw.py
Then update Appendix A.11's two reported errors: the pre-battery s.e. on 0.79 and
the battery t-statistic.
