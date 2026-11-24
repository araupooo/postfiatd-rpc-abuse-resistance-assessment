# Methodology

## What "measured" means in this pack

Every number in this pack is either:

- **OBSERVED (code)**: a value read verbatim from the pinned source
  (a constant, a threshold, a branch condition), cited with file and line
  and verified blob-by-blob against the GitHub API. These are facts about
  the code.
- **SIMULATED (measured)**: a number produced by running the protocol
  simulator (`scripts/simulator.py`) against a scenario in
  `scenarios/*.json`. These are measurements of the simulator's behaviour,
  not of a live node. They are labelled SIMULATED everywhere they appear.
- **UNMEASURED**: a dimension the pack does not cover. It is labelled
  UNMEASURED, never presented as measured.

No live node was load-tested. No number in this pack is a live-node
measurement.

## The simulator model

The simulator is a discrete-event model of one postfiatd RPC/WebSocket
port. It replays the control pipeline of the pinned code in the order
the code applies it (see docs/environment.md). Time is virtual
(milliseconds since scenario start). All randomness comes from seeded
generators (scenario seed 20261125, plus a per-stream stream number).

### Resource balance and decay

Each endpoint (IP address) carries a balance. The pinned code documents
an exponential decay window of 32 seconds
(`include/xrpl/resource/detail/Tuning.h:40`). The simulator models it
as a half-life decay over that window:

    balance(t) = balance * 0.5 ** ((t - t_last) / 32 s)

Charges are added when a request's job completes, matching the real code
(the charge happens at `ServerHandler.cpp:922`, after the handler runs).
Crossing the warning threshold (5000) charges feeWarning (4000) once per
episode; falling back below 5000 re-arms it. A request is refused when
the decayed balance at dispatch time is at or above the drop threshold
(25000).

A direct consequence of the decay math, worth stating plainly: with a
32-second half-life, the steady-state balance for a sustained charge
rate r (charge/s) is r * 32 / ln(2), about r * 46.2. The drop threshold
(25000) is therefore crossed by any sustained rate above about 542
charge/s from one IP — roughly 27 reference queries/s, 1.35 medium
queries/s, or 0.18 heavy queries/s. The warning threshold (5000) is
crossed above about 108 charge/s. These are arithmetic consequences of
the pinned constants, not simulator artefacts; the harness confirms them
(S4 light at 200 charge/s never dropped in 30 s; S4 medium at 4000
charge/s dropped after 90 served).

### Service times

Service time per method class is a simulator constant, not a measured
node timing:

| Charge class | Charge | Model service time |
|---|---|---|
| feeReferenceRPC | 20 | 5 ms |
| feeMediumBurdenRPC | 400 | 30-50 ms by method (40 ms typical) |
| feeHeavyBurdenRPC | 3000 | 250 ms |
| feeMalformedRPC | 100 | 2 ms |

The absolute latencies in the outputs (p50/p95/p99) are therefore model
outputs, not node measurements. What is robust to the service-time
choice is the *control behaviour*: which requests are refused, by which
control, and after how many served requests — those depend on the charge
values (verbatim from code) and the arrival rates, not on the service
times, except through the job-queue cap (S6) and the pathfind cap (S10),
where service time sets how long a slot is held. The sensitivity there
is documented in the findings report.

### What the simulator does not model

- The overlay network, consensus, ledger close, and transaction queue.
  Ledger age is therefore not simulated (C10 UNMEASURED).
- Batch requests (C12): single requests only.
- TLS, authentication handshakes, and HTTP keep-alive behaviour.
- Multi-threaded scheduling: the simulator is single-threaded and
  deterministic; the real JobQueue runs jobs on a thread pool, so the
  exact interleaving of a 600-request burst on a live node would differ
  in detail (the cap count, 500, would not).

## Determinism and reproduction

- `bash scripts/run_all.sh` runs the harness, the control measurement,
  the matrix build, and the manifest, then regenerates SHA256SUMS and
  verifies it.
- `run_all.sh` then re-runs the whole harness into a scratch directory
  and diffs every output (except `outputs/run_all.log`, which carries a
  wall-clock start line). The run passes only if the second run is
  byte-identical.
- `SHA256SUMS` covers every file under `outputs/` except `run_all.log`
  (full 64-hex SHA-256 per file). Verify with
  `bash scripts/verify_digests.sh`.
- `outputs/run-manifest.json` records the full SHA-256 of every input
  (scenario and script) and every output, so a re-run can be checked
  without trusting any single log line.

## Verification performed by the pack author

- All 22 cited source files: local `git hash-object` equals the GitHub
  API blob SHA at the pinned commit, sizes agree.
- All cited line numbers: read with `grep -n` on the local checkout of
  the pinned commit.
- Fresh-copy reproduction: the pack was copied to a scratch directory
  and `bash scripts/run_all.sh` was run there; the determinism check
  inside `run_all.sh` compares the two runs. (See PACK-READY.md for the
  result.)
- Forbidden-string sweep: no task IDs, no reward values, no framing, no
  links, no handles, no wallet addresses anywhere in the pack.
