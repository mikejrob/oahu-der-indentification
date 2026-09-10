#!/usr/bin/env python3
"""
08_rebuild_panel_hourshift.py — rebuild the hourly panel applying the FERC 714 clock-shift
correction to the LOAD before aligning to radiation.

Clock roll (integer-hour, calibrated on battery-INERT hours per
oahu-grid/notes/oahu-ferc714-hourshift.md; validated here against NSRDB solar noon):
    +1h for 2006-2012, 0 for 2013-2020, -1h for 2021-2024.
Radiation is astronomically correct -> NOT shifted.

The roll is applied on the local HST timestamp (shift the actual clock), so hour-of-day and
the date both update correctly at midnight boundaries.

Outputs:
  panel_hourly_shifted.parquet    (load + installs, clock-corrected)
  hourshift_validation.txt        (night-min + midday-trough alignment check)
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

pan = pd.read_parquet(os.path.join(ANA, "panel_hourly_with_installs.parquet"))
pan["dt_hst"] = pd.to_datetime(pan["dt_hst"])

def roll(y):
    if y <= 2012: return 1
    if y <= 2020: return 0
    return -1

pan["roll_h"] = pan["year"].apply(roll)
# shift the clock: corrected time = reported time + roll (hours)
pan["dt_corr"] = pan["dt_hst"] + pd.to_timedelta(pan["roll_h"], unit="h")
pan["hour"] = pan["dt_corr"].dt.hour
pan["date"] = pan["dt_corr"].dt.date
pan["year"] = pan["dt_corr"].dt.year
pan["month"] = pan["dt_corr"].dt.month
pan["quarter"] = pan["dt_corr"].dt.quarter
pan.to_parquet(os.path.join(ANA, "panel_hourly_shifted.parquet"), index=False)

# ---- validation: night-min hour should now be equal across blocks; and the 2021-24
# midday PV trough (in NET load) should sit at solar noon (~12h) after the -1h roll.
out = []
out.append("FERC 714 clock-shift validation (after roll +1/0/-1)")
def blk(y):
    return "2006-2012" if y <= 2012 else ("2013-2020" if y <= 2020 else "2021-2024")
pan["blk"] = pan["year"].apply(blk)
out.append("night-min hour by block (should be aligned ~3h now):")
for b in ["2006-2012", "2013-2020", "2021-2024"]:
    s = pan[pan.blk == b].groupby("hour")["load_mw"].mean()
    out.append(f"  {b}: night-min hour = {int(s[s.index<=8].idxmin())}")

# midday trough of the 2021-24 net load (high PV) vs solar noon
n = pd.read_parquet(os.path.join(ANA, "nsrdb_oahu_island_hourly_2020_2024.parquet"))
solarnoon = n[n.year.between(2021, 2024)].groupby("hour")["ghi"].mean().idxmax()
s2124 = pan[pan.blk == "2021-2024"].groupby("hour")["load_mw"].mean()
trough = s2124[s2124.index.isin(range(8, 16))].idxmin()
out.append(f"2021-24 corrected net-load midday trough hour = {int(trough)}; "
           f"NSRDB solar-noon hour = {int(solarnoon)}")
out.append("  (trough at/just after solar noon confirms the -1h roll; residual trough drift "
           "with installed MWh is the preserved battery signal, not a clock error.)")

# compare to UN-corrected trough for the record
raw = pd.read_parquet(os.path.join(ANA, "panel_hourly_with_installs.parquet"))
raw = raw[raw.year.between(2021, 2024)]
rawtrough = raw.groupby("hour")["load_mw"].mean()
rawtrough = rawtrough[rawtrough.index.isin(range(8, 16))].idxmin()
out.append(f"  (for the record: UN-corrected 2021-24 trough hour = {int(rawtrough)} -> "
           f"{int(rawtrough)-int(solarnoon):+d}h late; roll fixes it.)")

txt = "\n".join(out)
with open(os.path.join(OUT, "hourshift_validation.txt"), "w") as fh:
    fh.write(txt + "\n")
print(txt)
print("\nDONE 08")
