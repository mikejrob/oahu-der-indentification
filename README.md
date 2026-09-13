# Oʻahu distributed solar and storage: identification from daily radiation variation

Estimates of what rooftop photovoltaics and home batteries do to grid load on an
isolated system, identified from day-to-day variation in solar radiation rather
than from installation trends.

This repository is the canonical home of the estimators. The policy report
(`oahu-electricity-v1-corrected`, Appendix A.11) consumes the derived constants
and cites a commit here; it does not carry its own copy of the code. One
producer, hashed artifacts downstream.

## Layout

    analysis/       estimators and data preparation; 01-27 Python (early designs),
                    28-34 the anchored-profile line; 31-33 in R are the reference
                    estimators (lib_panel.R assembles the panel)
    data/raw/       panels pulled from Koa; not tracked (see Data)
    data/derived/   estimator outputs; tracked, these are the results
    docs/           methods log, findings records (read FINDINGS_2026-09-12_* first),
                    handoff, codebook, program taxonomy, candidate papers
    scripts/        environment setup, data pull, checksums
    paper/          manuscript

## Getting set up

    scripts/setup_env.sh          # virtual environment
    scripts/pull_from_koa.sh      # panels from the HPC (needs your Koa login)
    scripts/checksums.sh > MANIFEST.sha256

Then, from the repository root:

    .venv/bin/python analysis/09_estimator2_firmed.py
    .venv/bin/python analysis/18_prebattery_effective_mw.py

Scripts read `data/raw` and write `data/derived`. Both are overridable with
`OAHU_ANA` and `OAHU_OUT`, so the same scripts run unchanged on Koa against the
Lustre tree.

## Data

Three sources, all public or public-derivable:

- **Hourly system load** — FERC Form 714, respondent 178, via the PUDL
  compilation, 2006-2024. Respondent 178 is Oʻahu alone: Maui Electric and
  Hawaiʻi Electric Light have peak demand below Form 714's 200 MW reporting
  threshold and do not file, so nothing from the other islands enters the
  series. The load territory and the install territory therefore match.
- **Solar radiation** — NREL NSRDB, GOES-aggregated v4, island mean over 264
  Oʻahu grid cells, continuous 2013-2024, pulled from NREL's public S3 bucket
  (`07_extract_nsrdb_s3.py`, `11b`, `11c`). `03_load_nsrdb.py` reads an older
  on-disk CSV pull for 2007/2008/2018/2019 that exists only on the HPC; the S3
  path supersedes it.
- **Installed distributed capacity** — permit and interconnection records,
  compiled in the `oahu-grid` project. Public records, no privacy restriction.
  The estimators consume only island-level cumulative sums, so a replication
  archive can ship `installs_cumulative_daily.csv` (5,432 rows) rather than the
  per-system file.

Raw panels are not tracked here. They are large and reproducible, and
`MANIFEST.sha256` pins the copies the current estimates were produced from.

## Two measurement corrections applied before estimation

- **Form 714 clock alignment.** The series reads one hour early in 2006-2012 and
  one hour late in 2021-2024 relative to 2013-2020, coinciding with reporting
  format changes. Detected on pre-dawn hours, which neither technology can
  affect, and validated against astronomical solar noon. `08_rebuild_panel_hourshift.py`.
- **Pre-dawn anchor.** Each day's pre-dawn load is subtracted from every hour,
  removing demand drift without touching the distributed signal.

## Standard errors

Load residuals are serially correlated day to day, so default OLS errors
understate. Per-hour regressions carry one observation per date and use
Newey-West (`cov_type="HAC"`, rows in time order). Regressions carrying several
hours per date use Driscoll-Kraay (`cov_type="hac-groupsum"`, `time` = date
index), which is Newey-West across days after aggregating within a day. Both
scripts report a residual autocorrelation function, the Andrews (1991) AR(1)
plug-in bandwidth, and a standard error curve across truncation lags, so the
bandwidth is chosen from evidence rather than convention.

## Status

Pre-publication. `docs/METHODS_NOTES.md` is the running log, including the
blockers that are cleared and the ones that are not.
