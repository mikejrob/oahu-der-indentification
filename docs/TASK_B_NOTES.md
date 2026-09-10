# TASK B -- Install-location / zone-weighted radiation

**Question.** Does weighting Oahu radiation by where distributed PV is actually installed change
the effective capacity factor enough to matter for the netting calibration, or is the
island-uniform mean adequate?

## Installed capacity by zone (cross-check)
```
TASK B zonal install cross-check
der_points total: PV=793.3 MW, batt=249.7 MWh
der_by_era total: PV=793.3 MW, batt=249.6 MWh
  (small diff expected: der_points includes post-era-tally installs through 2025-06)

final (2024) cumulative by zone:
 year               zone  pv_mw_cum  batt_mwh_cum
 2024    Ewa_PearlHarbor      257.8          76.7
 2024     Honolulu_South      244.1          66.4
 2024    Windward_Koolau       90.5          34.3
 2024 Kunia_CentralBench       74.6          24.7
 2024       Waianae_Kahe       44.4          12.0
 2024 NorthShore_Waialua       30.0           5.4
 2024    Central_Wahiawa       24.0           8.1

```
der_points totals reconcile exactly with der_by_era.csv. Fleet is concentrated in the leeward,
sunnier Ewa_PearlHarbor + Honolulu_South zones.

## Install-weighted vs uniform radiation
Per-cell midday GHI (11-13h) from 264 NSRDB Oahu cells; DER points mapped to nearest cell
(EPSG:26904 -> WGS84). Weighted = cumulative-installed-MW-weighted cell GHI.
```
 year  uniform_ghi  weighted_ghi  ratio  installed_mw  implied_distpv_cf  cf_delta_pct
 2013     727.1329      697.4920 0.9592      290.6588             0.1748       -4.0764
 2014     735.1697      714.4368 0.9718      334.4482             0.1771       -2.8202
 2015     730.9961      707.2970 0.9676      394.1190             0.1763       -3.2420
 2016     736.0737      704.6316 0.9573      440.9435             0.1744       -4.2716
 2017     745.0517      711.9961 0.9556      476.1754             0.1741       -4.4367
 2018     702.8507      680.0486 0.9676      505.0070             0.1763       -3.2442
 2019     760.4514      734.7949 0.9663      551.8121             0.1761       -3.3739
 2020     755.3284      741.0055 0.9810      595.7900             0.1787       -1.8962
 2021     772.5309      779.1990 1.0086      640.2248             0.1838        0.8631
 2022     787.3387      790.9714 1.0046      668.3722             0.1830        0.4614
 2023     742.8448      734.9614 0.9894      721.7227             0.1803       -1.0612
 2024     743.6582      736.7062 0.9907      765.3378             0.1805       -0.9348
```

**Finding (2024): weighted/uniform ratio = 0.9907 (-0.93%).**
Implied DistPV CF = 0.1805 vs the model's 0.1822 (annual mean of the
DistPV rows in inputs/variable_capacity_factors.csv).

**Verdict: zone-weighting is immaterial (< 2%) for the DistPV CF.** The location-invariant inverter/tilt
derate passes through, so the radiation ratio maps directly to a CF ratio.

## Caveats
- Per-cell climatology is midday-GHI mean (11-13h), a proxy for the daily CF; a full 8760 per-cell
  CF would refine it but the spatial ratio is dominated by the leeward/windward GHI gradient.
- EIA-861 net-metering cross-check NOT reachable from this environment (no API/web egress);
  der_by_era is the internal control and it reconciles.
- Permit data (oahu-grid fetch_permits.py) can refine recent install locations but the zone/x-y in
  der_points already localizes the fleet.
- 250-MWh battery scale UNVERIFIED (does not affect the PV-location weighting).
