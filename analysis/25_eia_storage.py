#!/usr/bin/env python3
"""25_eia_storage.py -- measured distributed storage capacity for Oahu.

Replaces the era-allocated `batt_mwh` with reported capacity.

Source: EIA-861M, monthly, Utility_Level-States sheet of net_metering*.xlsx and
non_netmetering*.xlsx. "Hawaiian Electric Co Inc" is OAHU ALONE in EIA -- Maui
Electric and Hawaii Electric Light are separate utility numbers -- so this is
island-specific without any allocation step.

Fields used:
  Photovoltaic | Capacity MW | Total                     net-metered PV, AC
  Number and Capacity (MW) | Total Capacity              non-net-metered PV
  Battery | PV-Paired Energy Capacity (MWh) | Total      MEASURED storage energy
  Battery | PV-Paired Battery Capacity (MW) | Total      storage power
  Battery | PV-Paired Installations | Total              systems with storage

Coverage: PV from 2023-01, battery from 2023-08. EIA did not collect PV-paired
battery capacity before then, so the 2021-2023 Battery Bonus ramp -- where most
of the storage-era variation sits -- is not covered.

Writes data/analysis/eia861m_oahu_monthly.csv
"""
import glob
import warnings
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings("ignore")
REPO = Path(__file__).resolve().parent.parent


def read_utility_sheet(f, nhdr):
    xl = pd.ExcelFile(f)
    sh = [s for s in xl.sheet_names if s.startswith("Utility_Level-States")][0]
    hdr = pd.read_excel(f, sheet_name=sh, header=None, nrows=nhdr)
    g = [hdr.iloc[i].ffill() for i in range(1, nhdr - 1)] + [hdr.iloc[nhdr - 1]]
    names = [" | ".join([str(x[i]) for x in g if str(x[i]) != "nan"])
             for i in range(hdr.shape[1])]
    d = pd.read_excel(f, sheet_name=sh, header=None, skiprows=nhdr)
    d.columns = names
    un = [c for c in names if c.endswith("Utility Name")][0]
    return d[d[un].astype(str).str.contains("Hawaiian Electric", case=False, na=False)], names


def col(hi, names, pref, suffix="Total"):
    c = [x for x in names if x.startswith(pref) and x.endswith(suffix)]
    return pd.to_numeric(hi[c[0]], errors="coerce") if c else np.nan


rows = []
for f in sorted(glob.glob(str(REPO / "data/raw/eia861m/net_metering*.xlsx"))):
    hi, names = read_utility_sheet(f, 4)
    rows.append(pd.DataFrame({
        "year": pd.to_numeric(hi[[c for c in names if c.endswith("Year")][0]], errors="coerce"),
        "month": pd.to_numeric(hi[[c for c in names if c.endswith("Month")][0]], errors="coerce"),
        "nem_pv_mw": col(hi, names, "Photovoltaic | Capacity MW"),
        "batt_mw": col(hi, names, "Battery | PV-Paired Battery Capacity (MW)"),
        "batt_mwh": col(hi, names, "Battery | PV-Paired Energy Capacity (MWh)"),
        "batt_n": col(hi, names, "Battery | PV-Paired Installations")}))
nem = pd.concat(rows, ignore_index=True)

rows = []
for f in sorted(glob.glob(str(REPO / "data/raw/eia861m/non_netmetering*.xlsx"))):
    hi, names = read_utility_sheet(f, 3)
    rows.append(pd.DataFrame({
        "year": pd.to_numeric(hi[[c for c in names if c.endswith("Year")][0]], errors="coerce"),
        "month": pd.to_numeric(hi[[c for c in names if c.endswith("Month")][0]], errors="coerce"),
        "nonnem_pv_mw": col(hi, names, "Number and Capacity (MW)", "Total Capacity")}))
non = pd.concat(rows, ignore_index=True)

t = (nem.dropna(subset=["year", "month"])
        .merge(non.dropna(subset=["year", "month"]), on=["year", "month"], how="left")
        .drop_duplicates(["year", "month"], keep="last")
        .sort_values(["year", "month"]))
t["pv_mw_ac"] = t.nem_pv_mw.fillna(0) + t.nonnem_pv_mw.fillna(0)
t["mwh_per_mw"] = t.batt_mwh / t.pv_mw_ac
t.to_csv(REPO / "data/analysis/eia861m_oahu_monthly.csv", index=False)
b = t[t.batt_mwh.notna()]
print("PV months %d; battery months %d (%d-%02d to %d-%02d)"
      % (len(t), len(b), b.year.iloc[0], b.month.iloc[0], b.year.iloc[-1], b.month.iloc[-1]))
print("storage intensity %.3f -> %.3f MWh per AC MW"
      % (b.mwh_per_mw.iloc[0], b.mwh_per_mw.iloc[-1]))
print("DONE 25")
