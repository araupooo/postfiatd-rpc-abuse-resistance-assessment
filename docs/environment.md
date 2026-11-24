# Test environment

## Pinned commit

- Repository: postfiatorg/postfiatd
- Commit: `0085a1ff885d6a446369cf73a4430f75af22be55`
- Date: 2026-10-10
- Message: "Merge pull request #50 from postfiatorg/hotfix/upstream-hardening-1.0.9"
- Every cited file was verified blob-by-blob: the local checkout's
  `git hash-object` value equals the GitHub API blob SHA for the pinned
  commit, and the sizes agree. See docs/source-inventory.md for the full
  table (22 files).

## What was tested, and what was not

This pack tests the postfiatd JSON-RPC and WebSocket interfaces with a
**faithful protocol-level simulator** (`scripts/simulator.py`), not a live
node. A full postfiatd build was deliberately not attempted: a prior pack
in this series established that a complete build takes hours and is
fragile on this class of machine. The task explicitly allows "a local node
or a faithful protocol-simulator test environment".

The simulator replays the exact control pipeline of the pinned code, in
the order the code applies it:

1. per-port connection limit (`onAccept`)
2. request-size cap (1,000,000 bytes)
3. role gate (admin-only handlers, FORBID role)
4. per-endpoint resource balance (warn 5000 / drop 25000, 32 s decay)
5. client job-queue cap (500 concurrent jtCLIENT jobs)
6. pathfind concurrency caps (2 in progress, 50 queued jobs)
7. per-method page-limit clamping
8. WebSocket send-queue limit (default 100)
9. LoadMonitor latency targets (avg 2000 ms / peak 5000 ms)

Every control parameter is taken verbatim from the pinned source; each
value cites its exact file and line in `scripts/simulator.py`
(`CONTROL_PARAMS`) and in docs/source-inventory.md.

## Simulator environment

- Language: Python 3, standard library only. No network access at run time.
- Clock: virtual, in milliseconds since scenario start. No wall clock is
  read anywhere in the simulation; re-runs are byte-identical.
- Randomness: one seeded generator per scenario (seed 20261125, plus a
  per-stream stream number). Arrival jitter is uniform, +/-10% of the
  inter-arrival interval, drawn from the seeded generator.
- Service times per method class are simulator constants (see
  docs/methodology.md). They are model parameters, not measurements from a
  live node. Every conclusion that depends on them is labelled SIMULATED.
- Charge classes per method are observed from the pinned code, not
  assumed: most query handlers charge feeMediumBurdenRPC (400); JSON
  `ledger` charges feeHeavyBurdenRPC (3000); the default is
  feeReferenceRPC (20). See docs/control-inventory.md.

## Operator configuration modelled

The node configuration in every scenario is the documented default
unless the scenario says otherwise:

- `port_limit`: 0 (unlimited) — the default in
  `src/libxrpl/server/Port.cpp:265` ("unlimited"). Scenario S9 sets it to 3.
- `ws_queue_limit`: 100 — the default in `src/libxrpl/server/Port.cpp:306`.
  The example config (`cfg/postfiatd-example.cfg:1459-1465`) sets
  `send_queue_limit = 500` on the admin WebSocket port and leaves the
  public WebSocket port at the default.
- Example ports (`cfg/postfiatd-example.cfg:1435-1478`): RPC admin local
  5005/http, peer 2559, WS admin local 6006/ws, gRPC 50051, WS public
  6005/wss. No port in the example config sets `limit`.

## UNMEASURED (explicitly not claimed)

- Live-node behaviour under real load: latencies, throughput, and error
  rates on a real postfiatd process. The simulator's service times are
  model constants.
- Real close intervals, real ledger-close push rates, real incidents.
- The validated-ledger freshness gate (C10): no scenario models ledger age.
- Batch-request amplification depth (C12): the simulator models single
  requests; the batch finding is code-verified only.
- The exact RPC error surface for a pathfind skipped by the concurrency
  cap: the real code returns without starting the pathfind; the simulator
  records it as `rejected_pathfind_cap`.
- Any behaviour that depends on the overlay network, the ledger, or the
  transaction queue. This pack covers the RPC/WebSocket edge only.
