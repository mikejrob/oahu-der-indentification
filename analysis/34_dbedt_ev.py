#!/usr/bin/env python3
"""34_dbedt_ev.py -- Oahu registered vehicles from DBEDT's Monthly Energy Data.

Source: https://dbedt.hawaii.gov/economic/data_reports/energy-trends/
        Monthly_Energy_Data_a.xlsx, sheet "Oahu", block "Registered Vehicles,
        Taxable" (passenger and freight, by fuel). Monthly from 2006-01.
Purpose: the storage-era load results leave an overnight offset unexplained:
if batteries of the assumed size serve the house through the night, raw
2-4 am load should have fallen with the fleet, and it is flat. Home car
charging in the same households is the candidate offset. This series lets
that be bounded, and interacted with hour it is a direct control for one
named induced-demand channel.
Writes data/analysis/dbedt_oahu_vehicles_monthly.csv
"""
import pandas as pd
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
f = REPO / "data/raw/dbedt/Monthly_Energy_Data_a.xlsx"
df = pd.read_excel(f, sheet_name="Oahu", header=None)
dates = pd.to_datetime(df.iloc[3, 2:], errors="coerce")
lab = df.iloc[:, 0].astype(str).str.strip()
i0 = lab[lab.str.startswith("Registered Vehicles")].index[0]
rows = {}
for i in range(i0 + 1, i0 + 12):
    name = lab[i]
    if name in ("nan", "") or name.startswith("Electricity"):
        break
    rows[name] = pd.to_numeric(df.iloc[i, 2:], errors="coerce").values
out = pd.DataFrame(rows, index=dates).dropna(how="all")
out.index.name = "month"
out.columns = [c.replace(", ", "_").replace(" ", "_").lower() for c in out.columns]
out.to_csv(REPO / "data/analysis/dbedt_oahu_vehicles_monthly.csv")
print("columns:", list(out.columns))
print("units row:", df.iloc[i0 + 1:i0 + 4, 1].tolist())
ye = out[(out.index.month == 12) | (out.index == out.index.max())]
print(ye.loc[ye.index.year >= 2015].to_string())
