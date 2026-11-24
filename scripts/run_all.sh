#!/usr/bin/env bash
# run_all.sh — run the whole pack end to end, offline and deterministically.
#
#   bash scripts/run_all.sh
#
# Steps (every step writes its own unedited log under outputs/; there is
# no manual follow-up step anywhere in this pack):
#   1. run all load scenarios against the protocol simulator
#   2. aggregate per-control effectiveness from the scenario outputs
#   3. build the severity-ranked abuse-scenario matrix
#   4. write run-manifest.json (deterministic, no timestamps)
#   5. regenerate SHA256SUMS over outputs/ and verify it
#   6. re-run the harness a second time into a scratch copy and diff,
#      proving byte-identical reproduction
#
# Outputs that carry wall-clock timestamps (outputs/run_all.log only) are
# excluded from SHA256SUMS; everything else must be byte-identical
# across runs. Invoke helpers with `bash scripts/...` or
# `python3 scripts/...` (never by direct path) so a plain `git clone` —
# which drops executable bits — still runs.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
cd "$(dirname "$0")/.."
mkdir -p outputs

# The whole run is tee'd to outputs/run_all.log. That log is transient
# (it carries a wall-clock start line) and is excluded from SHA256SUMS.
exec > >(tee outputs/run_all.log) 2>&1

echo "=== postfiatd RPC abuse-resistance assessment ==="
echo "run started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "pinned commit: 0085a1ff885d6a446369cf73a4430f75af22be55"
echo "simulated: all load results come from scripts/simulator.py; no live node was load-tested"

python3 scripts/load_harness.py
python3 scripts/measure_controls.py
python3 scripts/build_matrix.py
python3 scripts/make_manifest.py
bash scripts/make_sha256sums.sh
bash scripts/verify_digests.sh

# Determinism proof: re-run the whole harness into a scratch directory and
# diff every output except run_all.log (wall-clock line) and the manifest
# (which records the harness digests, identical by construction).
rm -rf /tmp/rpc-rerun-check
mkdir -p /tmp/rpc-rerun-check
cp -r scripts scenarios docs README.md .gitignore /tmp/rpc-rerun-check/
cp SHA256SUMS /tmp/rpc-rerun-check/ 2>/dev/null || true
cd /tmp/rpc-rerun-check
mkdir -p outputs
export PYTHONDONTWRITEBYTECODE=1
python3 scripts/load_harness.py > /dev/null
python3 scripts/measure_controls.py > /dev/null
python3 scripts/build_matrix.py > /dev/null
python3 scripts/make_manifest.py > /dev/null
cd - > /dev/null
echo "--- determinism check (second run vs first run) ---"
diff -r -x run_all.log outputs /tmp/rpc-rerun-check/outputs && echo "DETERMINISM OK: second run byte-identical"
rm -rf /tmp/rpc-rerun-check

echo "=== run complete ==="
echo "outputs: $(ls outputs | wc -l) files"
