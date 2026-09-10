#!/usr/bin/env python3
"""
03_load_nsrdb.py — build an island-mean hourly radiation/weather series from the
on-disk NSRDB CSVs (2007, 2008, 2018, 2019 only; 234 Oahu grid points each).

NSRDB CSV: 2 header rows then columns Year,Month,Day,Hour,Minute,GHI,DHI,DNI,
Wind Speed,Temperature,Solar Zenith Angle. Times are local-standard (HST, tz-offset -10,
minute=30 -> hour-centered). We average across all grid points to get one island series,
then attach hour/season and a same-day MIDDAY GHI (mean of 10:00-14:00) for the battery term.

Outputs: nsrdb_oahu_island_hourly.parquet  (year, month, day, hour, ghi, temp, dni, dhi, ws)
         nsrdb_oahu_daily_midday.csv        (date, ghi_midday, temp_midday, temp_evening)
"""
import os
import glob
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
BASE = ("/mnt/lustre/koa/koastore/gtg_group/ehartley/_Hawaii_NG_Switch/data/"
        "Resource Assessment/NSRDB Hourly Irradiance Data")
YEARS = [2007, 2008, 2018, 2019]

frames = []
for y in YEARS:
    files = sorted(glob.glob(os.path.join(BASE, f"nsrdb oahu {y}", "*.csv")))
    if not files:
        print("WARN no files for", y); continue
    acc = None
    n = 0
    for f in files:
        df = pd.read_csv(f, skiprows=2,
                         usecols=["Year", "Month", "Day", "Hour", "GHI", "DNI",
                                  "DHI", "Temperature", "Wind Speed"])
        df = df.rename(columns={"Year": "year", "Month": "month", "Day": "day",
                                "Hour": "hour", "GHI": "ghi", "DNI": "dni",
                                "DHI": "dhi", "Temperature": "temp",
                                "Wind Speed": "ws"})
        if acc is None:
            acc = df.set_index(["year", "month", "day", "hour"])[
                ["ghi", "dni", "dhi", "temp", "ws"]].astype(float)
        else:
            acc = acc.add(df.set_index(["year", "month", "day", "hour"])[
                ["ghi", "dni", "dhi", "temp", "ws"]].astype(float), fill_value=0)
        n += 1
    acc = (acc / n).reset_index()
    print(f"{y}: {n} grid points, {len(acc)} island-hours, "
          f"mean GHI={acc.ghi.mean():.0f} W/m2, max noon GHI={acc[acc.hour==12].ghi.mean():.0f}")
    frames.append(acc)

isl = pd.concat(frames, ignore_index=True)
isl.to_parquet(os.path.join(ANA, "nsrdb_oahu_island_hourly.parquet"), index=False)

# daily midday GHI (10-14h), midday temp, evening temp (17-20h) for the battery/AC controls
isl["date"] = pd.to_datetime(isl[["year", "month", "day"]])
midday = isl[isl.hour.between(10, 14)].groupby("date").agg(
    ghi_midday=("ghi", "mean"), temp_midday=("temp", "mean")).reset_index()
evening = isl[isl.hour.between(17, 20)].groupby("date").agg(
    temp_evening=("temp", "mean")).reset_index()
daily = midday.merge(evening, on="date", how="outer")
daily.to_csv(os.path.join(OUT, "nsrdb_oahu_daily_midday.csv"), index=False)
print("nsrdb_oahu_daily_midday.csv:", len(daily), "days across years", YEARS)
print("DONE 03")
