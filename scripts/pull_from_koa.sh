#!/usr/bin/env bash
# Pull the panels this repository's estimators read from Koa (UH Manoa HPC).
#
# The raw panels are large and are NOT tracked here. They are rebuildable from
# public sources (FERC Form 714 via PUDL; NSRDB via NREL's public S3 bucket),
# so this script is a convenience, not the provenance record. Provenance and
# sha256 for every file are in MANIFEST.md.
#
# Usage:
#   scripts/pull_from_koa.sh              # core: what 09 and 18 need
#   scripts/pull_from_koa.sh --full       # adds the PUDL 714 table + oahu-grid raw
#   scripts/pull_from_koa.sh --dry-run    # list and size, transfer nothing
#
# Transfers go through the data-transfer node, which is the right host for
# bulk copies and does not run the login-node limits.
set -uo pipefail

USER_AT="${KOA_USER:-mjrobert}@koa-dtn.its.hawaii.edu"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$REPO/data/raw"
KOA_ANA="/mnt/lustre/koa/koastore/gtg_group/oahu-electricity-v1-corrected/analysis"
KOA_GRID="/mnt/lustre/koa/koastore/gtg_group/oahu-grid/data/intermediates"
KOA_PUDL="/mnt/lustre/koa/scratch/mjrobert/pudl"

FULL=0; DRY=""
for a in "$@"; do
  case "$a" in
    --full) FULL=1 ;;
    --dry-run) DRY="--dry-run" ;;
    *) echo "unknown option: $a"; exit 2 ;;
  esac
done

mkdir -p "$DEST"

# Core: the inputs 09_estimator2_firmed.py and 18_prebattery_effective_mw.py read.
CORE=(
  panel_hourly_shifted.parquet            # 09: clock-corrected hourly load + installs
  panel_hourly_with_installs.parquet      # 18: pre-correction panel, 2013-2019 window
  nsrdb_oahu_island_hourly.parquet        # radiation 2018-2019
  nsrdb_oahu_island_hourly_2020_2024.parquet
  nsrdb_oahu_island_hourly_2013_2019.parquet
  load_hourly_oahu.parquet                # cleaned 714 load, HST
  der_points_latlon_cell.parquet          # Task B: installs joined to radiation cells
)

echo "== core panels from $KOA_ANA"
printf '%s\n' "${CORE[@]}" > /tmp/koa_core_list.$$
rsync -avhP $DRY --files-from=/tmp/koa_core_list.$$ \
  "$USER_AT:$KOA_ANA/" "$DEST/"
rc=$?
rm -f /tmp/koa_core_list.$$
[ $rc -ne 0 ] && { echo "core pull failed (rc=$rc)"; exit $rc; }

if [ "$FULL" = "1" ]; then
  echo
  echo "== FERC 714 hourly table (PUDL) — only needed to rebuild the panel via 01"
  rsync -avhP $DRY \
    "$USER_AT:$KOA_PUDL/out_ferc714__hourly_planning_area_demand.parquet" "$DEST/"
  echo
  echo "== oahu-grid intermediates — install records behind the capacity series"
  rsync -avhP $DRY \
    "$USER_AT:$KOA_GRID/der_points.parquet" \
    "$USER_AT:$KOA_GRID/der_by_era.csv" "$DEST/"
fi

echo
echo "== local raw tree"
du -sh "$DEST" 2>/dev/null
ls -lh "$DEST" 2>/dev/null | tail -n +2 | awk '{printf "  %-52s %s\n", $9, $5}'
echo
echo "Next: scripts/checksums.sh > MANIFEST.sha256  (pin what you pulled)"
