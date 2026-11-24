#!/usr/bin/env bash
# make_sha256sums.sh — regenerate SHA256SUMS over outputs/ (full 64-hex
# SHA-256 per file), excluding outputs/run_all.log, which carries a
# wall-clock start line and is therefore not reproducible byte-for-byte.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -f SHA256SUMS
find outputs -type f ! -name run_all.log -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
echo "SHA256SUMS written: $(wc -l < SHA256SUMS) entries"
