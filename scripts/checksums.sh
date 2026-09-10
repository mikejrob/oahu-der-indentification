#!/usr/bin/env bash
# sha256 for every raw panel, so a re-pull can be checked against what the
# estimates were produced from. Same convention as the report repository's
# sources/ vendoring.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO/data/raw" 2>/dev/null || { echo "no data/raw — run pull_from_koa.sh first"; exit 1; }
for f in *; do
  [ -f "$f" ] || continue
  printf '%s  %s  %s\n' "$(shasum -a 256 "$f" | cut -d' ' -f1)" \
    "$(du -h "$f" | cut -f1)" "$f"
done
