# Postfiatd RPC Abuse-Resistance Assessment Pack

Pinned commit: `0085a1ff885d6a446369cf73a4430f75af22be55`
(2026-10-10, "Merge pull request #50 from postfiatorg/hotfix/upstream-hardening-1.0.9").

Assessment of how the postfiatd JSON-RPC and WebSocket interfaces
withstand realistic and abusive load: a runnable harness, a
source-cited control inventory with effectiveness measurements, a
severity-ranked scenario matrix, an operator remediation report, and a
sourced decision memo.

## SIMULATED vs OBSERVED — read this first

- **OBSERVED (code):** every control parameter in this pack is taken
  verbatim from the pinned source, cited with exact file and line, and
  verified blob-by-blob against the GitHub API. See
  `docs/source-inventory.md`.
- **SIMULATED (measured):** every load number comes from the
  protocol-level simulator (`scripts/simulator.py`) running the scenarios
  in `scenarios/`. **No live node was load-tested.** A full postfiatd
  build was out of scope for this pack, and the task allows a faithful
  protocol simulator. Simulator service times are model constants, not
  node measurements; the control-engagement findings (which requests are
  refused, by which control, after how many served) depend on the
  verbatim charge values and arrival rates.
- **UNMEASURED:** the validated-ledger freshness gate and batch-request
  amplification depth are code-verified only and labelled UNMEASURED in
  the inventory. Nothing unmeasured is presented as measured.

## Reproduce

```sh
bash scripts/run_all.sh
bash scripts/verify_digests.sh
```

`run_all.sh` runs all scenarios, measures control effectiveness, builds
the matrix, writes the manifest, regenerates `SHA256SUMS`, verifies it,
and then re-runs the whole harness into a scratch directory and diffs
the outputs — the run passes only if the second run is byte-identical.
Works offline; Python 3 standard library only.

## Headline results (SIMULATED)

| Scenario | Result |
|---|---|
| S0 baseline (7 reference queries/s, 60 s) | 420/420 served, 0 warnings |
| S1 burst flood (500/s, one IP) | First drop 2167 ms; 1297/5003 served, then a 27.19/s trickle |
| S2 slow WebSocket clients | 1/s-drain client closed at 11.2 s; 5/s at 20.0 s; 20/s never closed |
| S3 oversized payloads | 5/5 oversize rejected; boundary exact at 1,000,000 bytes |
| S4 repeated expensive queries | Heavy dropped after 16 served; medium after 90; light never dropped |
| S5 admin bypass | ADMIN 298/298 served, 0 rejected; PUBLIC 16/300 — **CRITICAL** |
| S6 job-queue saturation | 500 served, 100 `rpcTOO_BUSY`; probe 5 s later 10/10 refused 503 |
| S7 per-IP isolation | Benign IPs 21/21 each during the flood |
| S8 page-limit clamping | 5/5 over-range public limits clamped; admin 10000 served unclamped |
| S9 connection limit (limit 3) | 2/2 excess connections refused |
| S10 pathfind cap | 2 served, 3 rejected; second burst 2/2 served |

Severity ranking: 1 CRITICAL (S5 admin bypass), 2 HIGH (S1, S7),
3 MEDIUM (S2, S4, S6), 4 LOW (S3, S8, S9, S10), 1 INFO (S0).
Full matrix: `outputs/matrix.md`.

The single most important finding: the per-endpoint resource balance
stops every flood in the pack, but admin and identified roles bypass
every resource control — the public edge is only as safe as the admin
ports and credentials are out of reach. Second-order finding: the
balance control concedes ~1,100 requests in the first ~2 seconds of a
flood, because charges land at job completion.

## Layout

- `scripts/simulator.py` — the protocol-level node model (verbatim
  control parameters, virtual clock, deterministic).
- `scripts/load_harness.py` — runs the scenarios, writes per-request
  logs, summaries, and unedited run logs.
- `scripts/measure_controls.py` — per-control effectiveness, computed
  from the scenario outputs.
- `scripts/build_matrix.py` — severity-ranked matrix (deterministic
  rubric over the measured numbers).
- `scripts/make_manifest.py`, `scripts/make_sha256sums.sh`,
  `scripts/verify_digests.sh`, `scripts/run_all.sh`.
- `scenarios/` — 11 scenario definitions (S0-S10).
- `docs/environment.md` — pinned commit and test environment.
- `docs/source-inventory.md` — all 22 cited files with blob SHAs and
  line numbers.
- `docs/control-inventory.md` — 12 controls with verbatim parameters
  and measured effectiveness.
- `docs/methodology.md` — model, assumptions, determinism, what is
  UNMEASURED.
- `docs/findings-report.md` — headline findings with evidence links.
- `docs/remediation-report.md` — severity-ranked operator remediations.
- `docs/decision-memo.md` — sourced decision memo.
- `outputs/` — per-scenario CSV/JSON/log, control-effectiveness table,
  matrix, manifest. `SHA256SUMS` covers all of it except the
  wall-clock-bearing `outputs/run_all.log`.

## Claim-to-evidence index

| Claim | Script | Raw output |
|---|---|---|
| S0: 420/420 served, 0 warnings | `scripts/load_harness.py` | `outputs/S0-baseline.csv`, `outputs/S0-baseline.json`, `outputs/S0-baseline.log` |
| S1: first drop 2167 ms; 1297/5003 served; trickle 27.19/s | `scripts/load_harness.py` | `outputs/S1-burst-single-ip.csv`, `outputs/S1-burst-single-ip.json`, `outputs/S1-burst-single-ip.log` |
| S2: slow clients closed 11200 ms / 20000 ms, queue depth 101 | `scripts/load_harness.py` | `outputs/S2-slow-ws-clients.csv`, `outputs/S2-slow-ws-clients.json`, `outputs/S2-slow-ws-clients.log` |
| S3: 5/5 oversize rejected; boundary exact at 1,000,000 bytes | `scripts/load_harness.py` | `outputs/S3-oversized-payloads.csv`, `outputs/S3-oversized-payloads.json`, `outputs/S3-oversized-payloads.log` |
| S4: heavy 16, medium 90 served before drop; light 301/301 | `scripts/load_harness.py` | `outputs/S4-expensive-repeat.csv`, `outputs/S4-expensive-repeat.json`, `outputs/S4-expensive-repeat.log` |
| S5: ADMIN 298/298, PUBLIC 16/300 | `scripts/load_harness.py` | `outputs/S5-admin-bypass.csv`, `outputs/S5-admin-bypass.json`, `outputs/S5-admin-bypass.log` |
| S6: 500 served, 100 too-busy; probe 10/10 refused 503 | `scripts/load_harness.py` | `outputs/S6-job-queue-saturation.csv`, `outputs/S6-job-queue-saturation.json`, `outputs/S6-job-queue-saturation.log` |
| S7: benign 21/21 each during flood | `scripts/load_harness.py` | `outputs/S7-multi-ip-isolation.csv`, `outputs/S7-multi-ip-isolation.json`, `outputs/S7-multi-ip-isolation.log` |
| S8: 5/5 over-range limits clamped | `scripts/load_harness.py` | `outputs/S8-page-limit-clamp.csv`, `outputs/S8-page-limit-clamp.json`, `outputs/S8-page-limit-clamp.log` |
| S9: 2/2 excess connections refused | `scripts/load_harness.py` | `outputs/S9-connection-limit.csv`, `outputs/S9-connection-limit.json`, `outputs/S9-connection-limit.log` |
| S10: 2 served, 3 cap-rejected; second burst 2/2 | `scripts/load_harness.py` | `outputs/S10-pathfind-cap.csv`, `outputs/S10-pathfind-cap.json`, `outputs/S10-pathfind-cap.log` |
| Per-control effectiveness (12 controls; C10, C12 not exercised) | `scripts/measure_controls.py` | `outputs/control-effectiveness.csv`, `outputs/control-effectiveness.json`, `outputs/control-effectiveness.log` |
| Severity-ranked matrix (1 CRITICAL, 2 HIGH, 3 MEDIUM, 4 LOW, 1 INFO) | `scripts/build_matrix.py` | `outputs/matrix.csv`, `outputs/matrix.md`, `outputs/matrix.log` |
| Run manifest (input/output digests) | `scripts/make_manifest.py` | `outputs/run-manifest.json` |
| Digest verification | `scripts/verify_digests.sh` | `SHA256SUMS` |
| Determinism (second run byte-identical) | `scripts/run_all.sh` | `outputs/run_all.log` |
