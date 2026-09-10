#!/usr/bin/env bash
# pull_nsrdb_loginnode.sh -- pull Oahu hourly NSRDB (GHI + weather) for the
# battery-era years the on-disk archive is missing. RUN ON A LOGIN NODE
# (compute nodes have filtered DNS and cannot resolve developer.nrel.gov).
#
#   ssh <login node>        # NOT a compute/interactive node
#   bash /mnt/lustre/koa/koastore/gtg_group/oahu-electricity-v1-corrected/analysis/pull_nsrdb_loginnode.sh
#
# Uses the HAWAII dataset endpoint (nsrdb-GOES-aggregated-v4-0-0), matching the
# script that fetched the on-disk 2007/2008/2018/2019 data. The mainland
# psm3 endpoint does NOT serve Hawaii and fails in a way that looks like an
# auth error -- that was the bug in the previous version of this script.
#
# Reads key/email from ~/.nrel_api_key. Saves in the layout the loader expects:
#   analysis/nsrdb_pull/nsrdb oahu YYYY/nsrdb_LAT_LON_YYYY.csv
# Resumable. NREL limits: ~50 cells/hour, 100/day, 1 request/sec per key+IP.
set -u
KEYFILE="$HOME/.nrel_api_key"
KEY=$(grep -E '^NREL_API_KEY='   "$KEYFILE" | head -1 | cut -d= -f2- | tr -d '"'"'"' \r\n ')
EMAIL=$(grep -E '^NREL_API_EMAIL=' "$KEYFILE" | head -1 | cut -d= -f2- | tr -d '"'"'"' \r\n ')
[ ${#KEY} -ge 10 ] || { echo "no key in $KEYFILE"; exit 1; }
# Fallback if your 2018 key is dead: a colleague's key is committed in
#   ehartley/.../download_nsrdb_data_updated.py  (use only if yours fails auth)

OUT="/mnt/lustre/koa/koastore/gtg_group/oahu-electricity-v1-corrected/analysis/nsrdb_pull"
YEARS="2020 2021 2022 2023 2024"          # 2024 may not be published yet; it will 400 and skip
POINTS="21.290,-157.860 21.290,-158.060 21.450,-157.740 21.450,-158.020 21.450,-158.140 21.570,-158.060 21.610,-158.100 21.370,-157.700 21.730,-158.020"
ATTR="ghi,dhi,dni,wind_speed,air_temperature,solar_zenith_angle"
BASE="https://developer.nrel.gov/api/nsrdb/v2/solar/nsrdb-GOES-aggregated-v4-0-0-download.csv"

echo "pulling ${YEARS// /, } for 9 Oahu points (GOES-aggregated-v4) -> $OUT"
first=1
for Y in $YEARS; do
  mkdir -p "$OUT/nsrdb oahu $Y"
  for P in $POINTS; do
    LAT=${P%,*}; LON=${P#*,}
    F="$OUT/nsrdb oahu $Y/nsrdb_${LAT}_${LON}_${Y}.csv"
    [ -s "$F" ] && { echo "  skip $Y $LAT,$LON (exists)"; continue; }
    URL="${BASE}?api_key=${KEY}&email=${EMAIL}&full_name=UH+Researcher&affiliation=University+of+Hawaii&reason=power+system+planning&mailing_list=false&interval=60&utc=false&half_hour=true&leap_day=true&attributes=${ATTR}&names=${Y}&wkt=POINT(${LON}%20${LAT})"
    code=$(curl -s -o "$F" -w "%{http_code}" --max-time 120 "$URL")
    if [ "$code" = "200" ] && [ -s "$F" ] && head -1 "$F" | grep -qi "Source"; then
      echo "  ok   $Y $LAT,$LON ($(wc -l < "$F") lines)"
    else
      echo "  FAIL $Y $LAT,$LON http=$code"
      if [ $first -eq 1 ]; then
        echo "  --- first-error body (key redacted) — tells us key-vs-endpoint-vs-year ---"
        sed "s/${KEY}/REDACTED/g" "$F" 2>/dev/null | head -4
      fi
      rm -f "$F"
    fi
    first=0
    sleep 1.1                              # NREL: 1 request/sec
  done
done
echo "DONE. Files under: $OUT"
echo "If the FIRST-ERROR body says API_KEY_INVALID/403 -> key expired (get a free one at"
echo "  https://developer.nrel.gov/signup/ , or use the fallback key noted in this script)."
echo "If it says the location/year has no data -> that year isn't in the dataset yet."
echo "Otherwise, tell Claude and it will re-run analysis 03->05 with these years."
