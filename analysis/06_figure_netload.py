#!/usr/bin/env python3
"""06_figure_netload.py — hour-of-day net-load profiles by PV/battery-penetration era,
showing the PV midday-trough deepening then the battery evening-shave.
Output: fig_netload_by_era.png"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ANA = os.environ.get(
    "OAHU_ANA",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "raw"))
OUT = os.environ.get(
    "OAHU_OUT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "derived"))
os.makedirs(OUT, exist_ok=True)
# clock-corrected panel (FERC 714 hour-shift roll +1/0/-1 applied)
pan = pd.read_parquet(os.path.join(ANA, "panel_hourly_shifted.parquet"))

# eras by penetration
def era(y):
    if y <= 2011: return "2006-2011 pre-PV"
    if y <= 2016: return "2012-2016 PV ramp"
    if y <= 2020: return "2017-2020 high PV"
    return "2021-2024 PV+battery"
pan["era"] = pan["year"].apply(era)
order = ["2006-2011 pre-PV", "2012-2016 PV ramp", "2017-2020 high PV", "2021-2024 PV+battery"]

prof = pan.groupby(["era", "hour"])["load_mw"].mean().reset_index()

fig, ax = plt.subplots(1, 2, figsize=(13, 5))
colors = plt.cm.viridis(np.linspace(0, 0.9, len(order)))
for c, e in zip(colors, order):
    s = prof[prof.era == e]
    ax[0].plot(s.hour, s.load_mw, label=e, color=c, lw=2)
ax[0].set_xlabel("hour of day (HST)"); ax[0].set_ylabel("mean load (MW)")
ax[0].set_title("Oahu (HECO-178) hour-of-day load by PV/battery era")
ax[0].legend(fontsize=8); ax[0].grid(alpha=0.3); ax[0].set_xticks(range(0, 24, 3))

# normalized to 3am (clock-corrected night-min anchor) to isolate SHAPE change
a4 = pan[pan.hour == 3].groupby("era")["load_mw"].mean()
prof2 = prof.copy()
prof2["anom"] = prof2.apply(lambda r: r.load_mw - a4[r.era], axis=1)
for c, e in zip(colors, order):
    s = prof2[prof2.era == e]
    ax[1].plot(s.hour, s.anom, label=e, color=c, lw=2)
ax[1].axhline(0, color="k", lw=0.6)
ax[1].axvspan(10, 14, color="gold", alpha=0.12)
ax[1].axvspan(17, 21, color="salmon", alpha=0.12)
ax[1].set_xlabel("hour of day (HST)"); ax[1].set_ylabel("load minus 3am load (MW)")
ax[1].set_title("3am-anchored shape (clock-corrected): midday trough deepens, evening shaves")
ax[1].legend(fontsize=8); ax[1].grid(alpha=0.3); ax[1].set_xticks(range(0, 24, 3))
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig_netload_by_era.png"), dpi=130)
print("wrote fig_netload_by_era.png")
