#!/usr/bin/env bash
# Local virtual environment. Kept inside the repo and gitignored.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
python3 -m venv "$REPO/.venv"
"$REPO/.venv/bin/pip" install --quiet --upgrade pip
"$REPO/.venv/bin/pip" install -r "$REPO/requirements.txt"
echo "ready:  source $REPO/.venv/bin/activate"
"$REPO/.venv/bin/python" -c "import numpy,pandas,statsmodels,pyarrow; print('numpy',numpy.__version__,'pandas',pandas.__version__,'statsmodels',statsmodels.__version__)"
