# Decision memo

Pinned commit: `0085a1ff885d6a446369cf73a4430f75af22be55`
(2026-10-10, "Merge pull request #50 from postfiatorg/hotfix/upstream-hardening-1.0.9").

## Question

Do the JSON-RPC and WebSocket interfaces of postfiatd at the pinned
commit withstand realistic and abusive load, and what should an operator
do about it?

## Answer in one paragraph

Yes, against the abuses measured here — with one exception. The
per-endpoint resource balance stops every flood and every repeated
expensive query in the pack, benign traffic is fully isolated from a
flood, and the size, page-limit, pathfind, job-queue, connection-limit
and WebSocket-queue controls all engage exactly as coded. The exception
is the unlimited-role bypass: admin and identified roles face no
resource control at all, so the security of the public RPC edge rests
entirely on keeping admin ports and credentials out of reach. The
second-order weakness is timing, not absence: the balance control lets
~1,100 requests through in the first ~2 seconds of a flood, and a slow
WebSocket subscriber holds a full 100-message queue for 11-20 seconds
before being closed.

## Evidence base

All load numbers are SIMULATED (protocol simulator,
`scripts/simulator.py`, virtual clock, fixed seed 20261125). No live
node was load-tested. Control parameters are OBSERVED from the pinned
code (see docs/source-inventory.md for the blob-verified citation table).

| Claim | Evidence |
|---|---|
| Flood stopped, 1084 requests served first (S1) | `outputs/S1-burst-single-ip.json`, `outputs/S1-burst-single-ip.csv` |
| Heavy queries dropped after 16 served; light never dropped (S4) | `outputs/S4-expensive-repeat.json` |
| Admin bypass: 298/298 served vs public 16/300 (S5) | `outputs/S5-admin-bypass.json` |
| Benign isolation: 21/21 each during flood (S7) | `outputs/S7-multi-ip-isolation.json` |
| Job cap holds at exactly 500 (S6) | `outputs/S6-job-queue-saturation.json` |
| Slow WS clients closed at 11.2 s / 20.0 s (S2) | `outputs/S2-slow-ws-clients.json` |
| 1 MB cap exact; 5/5 oversize rejected (S3) | `outputs/S3-oversized-payloads.csv` |
| 5/5 over-range limits clamped (S8) | `outputs/S8-page-limit-clamp.csv` |
| Connection limit: 2/2 excess refused (S9) | `outputs/S9-connection-limit.json` |
| Pathfind cap: 2 served, 3 rejected (S10) | `outputs/S10-pathfind-cap.csv` |
| Baseline: 420/420 served (S0) | `outputs/S0-baseline.json` |
| Severity ranking | `outputs/matrix.md`, `outputs/matrix.csv` |
| Per-control effectiveness | `outputs/control-effectiveness.csv` |

## How the controls work (source-cited)

- **Connection limit.** `Port.cpp:265-283` parses `limit` (default
  "unlimited"); `ServerHandler.cpp:175-190` drops the connection when
  the per-port count reaches it.
- **Request size.** `Tuning.h:66` sets 1,000,000 bytes;
  `ServerHandler.cpp:627-637` (HTTP 400) and `:340-360` (WebSocket
  jsonInvalid + session close) enforce it.
- **Role gate.** `Role.cpp:125-128`: ADMIN and IDENTIFIED are unlimited.
  `RPCHandler.cpp:156-157`: admin-only handlers refuse non-admins.
  `ServerHandler.cpp:754-768`: FORBID role gets HTTP 403 plus a
  malformed-RPC charge.
- **Resource balance.** `Tuning.h (resource):31-44`: warn 5000, drop
  25000, decay window 32 s. `Logic.h:387-398,452-480,508-525`:
  disposition, charge, disconnect. `Fees.cpp:33-44`: reference 20,
  medium 400, heavy 3000, malformed 100, exception 100, warning 4000,
  drop 6000. Refusal is HTTP 503 / error -32604
  (`ServerHandler.cpp:737-746`) or a WebSocket close with `rpcSLOW_DOWN`
  429 (`ServerHandler.cpp:429-435`, `ErrorCodes.cpp:106`).
- **Job queue.** `Tuning.h:64`: 500 client jobs. `RPCHandler.cpp:132-140`:
  above the cap returns `rpcTOO_BUSY` unless the role is unlimited.
- **Pathfind.** `Tuning.h:62-63`: 2 in progress, 50 queued jobs.
  `LegacyPathFind.cpp:38-48`: no new pathfind while either cap is hit.
- **Page limits.** `Tuning.h:37-58`: per-method ranges.
  `RPCHelpers.cpp:701-717`: public roles are clamped to [min, max];
  unlimited roles are not clamped.
- **WebSocket queue.** `Port.cpp:284-308`: default 100.
  `BaseWSPeer.h:236-246`: overflow closes the session (policy_error,
  "Policy error: client is too slow.").
- **Load monitor.** `JobTypes.h:86-92`: jtCLIENT targets avg 2000 ms /
  peak 5000 ms. `LoadMonitor.cpp:153-172`: overloaded flag.
- **Ledger freshness.** `Tuning.h:65`: validated ledger older than
  2 minutes is stale (`RPCHelpers.cpp:352,1061`, `Handler.h:109`).

## What the pack does not decide

- Whether the modelled service times match a live node: they are model
  constants, and the absolute latencies in the outputs are model
  outputs. The control-engagement findings (which requests are refused,
  by which control, after how many served) depend on the verbatim charge
  values and arrival rates, not on the service times, except for the
  job-queue cap (S6) and the pathfind cap (S10), where service time sets
  how long a slot is held.
- The validated-ledger gate (C10) and batch amplification depth (C12):
  code-verified only, UNMEASURED in the harness. Do not cite this pack
  as evidence about either.

## Recommendation

1. Keep admin ports loopback-only and audit the IDENTIFIED
   classification (CRITICAL, S5).
2. Set a `limit` on every public port (S9).
3. Put a per-IP rate limiter at the edge in front of the public port to
   cover the ~2 seconds the balance control concedes (S1).
4. Lower `send_queue_limit` on the public WebSocket port if slow
   subscribers are observed (S2).
5. Alert on warning-threshold crossings, not only on 503s (C11).
6. Measure C10 and C12 on a test node before the next review (see
   docs/remediation-report.md item 6).
