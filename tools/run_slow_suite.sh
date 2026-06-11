#!/usr/bin/env bash
# Review-Runde 2 (Punkt 7): lokaler Runner fuer die slow-Suite (nightly-CI-Aequivalent).
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$(pwd)"
python -m tools.verify_data_manifest
python -m pytest -q -m "slow" -p no:cacheprovider --durations=20 --tb=short "$@"
