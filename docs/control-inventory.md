# Control inventory

Pinned commit: `0085a1ff885d6a446369cf73a4430f75af22be55`.
Every control below cites the exact file and line of the pinned source.
Effectiveness numbers are measured by `scripts/measure_controls.py` from
the harness outputs; the full table (machine-readable) is
`outputs/control-effectiveness.csv` and `outputs/control-effectiveness.json`.

## C01 — Per-port connection limit

- Source: `src/libxrpl/server/Port.cpp:265-283` (config key `limit`,
  default "unlimited"); enforced in
  `src/xrpld/rpc/detail/ServerHandler.cpp:175-190` (`onAccept` returns
  false when the per-port count reaches the limit).
- Measured (S9, limit 3): 2 of 2 excess connections refused; 3 of 3
  within-limit connections served. Evidence: `outputs/S9-connection-limit.json`.
- Gap: the control is OFF by default, and the shipped example config
  (`cfg/postfiatd-example.cfg:1435-1478`) sets no `limit` on any port.
  An operator who never sets it has no connection cap at all.

## C02 — Maximum request size (1,000,000 bytes)

- Source: `src/xrpld/rpc/detail/Tuning.h:66` (`maxRequestSize = 1000000`);
  enforced for HTTP in `ServerHandler.cpp:627-637` (HTTP 400) and for
  WebSocket in `ServerHandler.cpp:340-360` (jsonInvalid error, session
  completed).
- Measured (S3): 5 of 5 oversize requests rejected (3x HTTP 400, 1x WS
  jsonInvalid + session close, 1x follow-on `rejected_client_gone`);
  999,999-byte and 1,000,000-byte requests served. Boundary exact.
  Evidence: `outputs/S3-oversized-payloads.csv`.
- Gap: none measured. The 1 MB envelope bounds batch amplification only
  indirectly (see C12).

## C03 — Role gate (admin-only handlers, unlimited roles)

- Source: `src/xrpld/rpc/detail/Role.cpp:125-128` (ADMIN and IDENTIFIED
  are unlimited); `src/xrpld/rpc/detail/RPCHandler.cpp:156-157`
  (admin-only handler from a non-admin role returns `rpcNO_PERMISSION`);
  `src/xrpld/rpc/detail/ServerHandler.cpp:754-768` (FORBID role: HTTP 403
  plus a feeMalformedRPC charge).
- Measured (S8, S5): 1 of 1 admin-only attempts from PUBLIC rejected
  (`rejected_no_permission`); the same method from ADMIN served. ADMIN
  served 298 of 298 heavy ledger requests with 0 rejections in S5, while
  the identical PUBLIC load was dropped after 16 served.
  Evidence: `outputs/S8-page-limit-clamp.csv`,
  `outputs/S5-admin-bypass.json`.
- Gap: the unlimited-role bypass is by design, but it means a compromised
  admin credential, or a misclassified IDENTIFIED endpoint, faces no
  resource control at all.

## C04 — Per-endpoint resource balance (warn 5000 / drop 25000, 32 s decay)

- Source: `include/xrpl/resource/detail/Tuning.h:31-44`
  (warningThreshold 5000, dropThreshold 25000, decayWindowSeconds 32,
  minimumGossipBalance 1000); `include/xrpl/resource/detail/Logic.h:387-398`
  (disposition), `:452-480` (charge), `:492-495` (warning charge),
  `:508-525` (disconnect); `src/libxrpl/resource/Fees.cpp:33-44` (charge
  table); enforced in `ServerHandler.cpp:737-746` (HTTP 503, JSON-RPC
  error -32604) and `ServerHandler.cpp:429-435` (WebSocket close +
  `rpcSLOW_DOWN`, error 429).
- Measured (S1, S4, S5, S7): S1 flood (500 reference queries/s, charge
  20 each) first dropped at 2167 ms; 1297 of 5003 requests served, then
  a post-drop trickle of 27.19 served/s. S4: heavy queries (charge 3000)
  dropped after 16 served (first drop 1011 ms); medium (charge 400)
  after 90 served; light (charge 20) never dropped in 30 s (301/301).
  S7: benign IPs served 21/21 each during the flood — per-endpoint
  isolation holds. 7 warning-threshold crossings recorded across the
  abusive scenarios. Evidence: `outputs/S1-burst-single-ip.json`,
  `outputs/S4-expensive-repeat.json`, `outputs/S7-multi-ip-isolation.json`.
- Gap: charge rate, not request count, is the throttle. With a 32-second
  half-life decay, the drop equilibrium is about 542 charge/s per IP, so
  a sustained 1.35 medium-burden requests/s from one IP eventually trips
  the drop — the control also throttles legitimate sustained use from a
  single IP. After a drop the endpoint serves a trickle (~27/s in S1)
  rather than staying closed, because the balance decays below the
  threshold between requests.

## C05 — Client job-queue cap (maxJobQueueClients 500)

- Source: `src/xrpld/rpc/detail/Tuning.h:64` (500);
  `src/xrpld/rpc/detail/RPCHandler.cpp:132-140` (count of jobs at
  jtCLIENT priority or higher above 500 returns `rpcTOO_BUSY`, unless the
  role is unlimited).
- Measured (S6): a burst of 600 simultaneous heavy requests: 500 served,
  100 rejected `rpcTOO_BUSY` at t=0 ms. A probe 5 s later: 10/10
  rejected 503 — the resource balance, not the job queue, was still
  above the drop threshold. Evidence: `outputs/S6-job-queue-saturation.json`.
- Gap: the cap is a concurrency cap, not a rate cap. 500 concurrent heavy
  jobs is a large amount of admitted work, and the resource-balance charge
  only lands at job completion, so a burst passes the balance check
  before any charge is applied.

## C06 — Pathfind concurrency caps (2 in progress, 50 queued jobs)

- Source: `src/xrpld/rpc/detail/Tuning.h:62-63` (maxPathfindsInProgress 2,
  maxPathfindJobCount 50); `src/xrpld/rpc/detail/LegacyPathFind.cpp:38-48`
  (no new pathfind while 2 are in progress, or while the jtCLIENT job
  count exceeds 50, or while the node is loaded locally).
- Measured (S10): first burst of 5 pathfinds: 2 served, 3 rejected
  (`rejected_pathfind_cap`) at t=0 ms; second burst of 2 after the first
  two completed (t=200 ms): 2 served, 0 rejected. Evidence:
  `outputs/S10-pathfind-cap.csv`.
- Gap: maxPathfindJobCount 50 was not exercised (no scenario queues 50+
  client jobs while pathfinding). The cap silently skips starting a
  pathfind; the exact RPC error surface for a skipped pathfind is
  UNMEASURED.

## C07 — Per-method page limits (LimitRange clamp)

- Source: `src/xrpld/rpc/detail/Tuning.h:37-58` (ranges, e.g.
  accountLines {10, 200, 400}, bookOffers {0, 60, 100}, accountNFTokens
  {20, 100, 400}); `src/xrpld/rpc/detail/RPCHelpers.cpp:701-717`
  (`readLimitField`: non-unlimited roles are clamped to [rmin, rmax];
  unlimited roles are left untouched).
- Measured (S8): 5 of 5 over-range public limits clamped (10000->400,
  5->10, 0->10, 500->100, 1000->400); 1 in-range public limit served as
  asked (400); 1 admin limit of 10000 served unclamped. Evidence:
  `outputs/S8-page-limit-clamp.csv`.
- Gap: unlimited roles bypass clamping entirely, so an admin client can
  request unbounded pages.

## C08 — WebSocket send-queue limit (default 100)

- Source: `src/libxrpl/server/Port.cpp:284-308` (`send_queue_limit`,
  default 100); `include/xrpl/server/detail/BaseWSPeer.h:236-246` (queue
  above the limit closes the session with close code policy_error,
  reason "Policy error: client is too slow.").
- Measured (S2): slow client (drain 1/s vs 10 pushes/s) closed at
  11200 ms with queue depth 101; mid client (drain 5/s) closed at
  20000 ms, queue depth 101; fast client (drain 20/s) never closed in
  30 s. Evidence: `outputs/S2-slow-ws-clients.json` (ws_events).
- Gap: a slow client holds its connection and up to 101 queued messages
  for 11-20 s before the control engages; the limit is per-connection,
  so many slow connections each hold 100 messages.

## C09 — LoadMonitor latency targets (jtCLIENT avg 2000 ms / peak 5000 ms)

- Source: `src/xrpld/core/JobTypes.h:86-92` (jtCLIENT targets);
  `src/xrpld/core/JobTypeData.h:66` (targets wired into the monitor);
  `src/xrpld/core/detail/LoadMonitor.cpp:153-172` (`isOverTarget`,
  `isOver`); `src/xrpld/core/LoadMonitor.h:50-90` (stats, overloaded flag).
- Measured (all scenarios S0-S10): worst average latency 250.00 ms,
  worst peak 250 ms; `is_overloaded` fired in 0 of 11 scenarios.
  Evidence: every `outputs/S*.json` (`load_monitor` block).
- Gap: the monitor watches latency, not queue depth or charge rate.
  Modelled service times (max 250 ms) sit far below the 2000/5000 ms
  targets, so the monitor is a lagging indicator, not a first-line abuse
  control. Its value as an abuse control on a live node is UNMEASURED.

## C10 — Validated-ledger freshness gate (maxValidatedLedgerAge 2 min)

- Source: `src/xrpld/rpc/detail/Tuning.h:65` (2 minutes);
  `src/xrpld/rpc/detail/RPCHelpers.cpp:352,1061` (staleness check);
  `src/xrpld/rpc/detail/Handler.h:109` (WebSocket gate).
- Measured: NOT EXERCISED. No scenario models ledger age, so the gate's
  rejection behaviour is UNMEASURED in this pack.
- Gap (code-verified only): handlers refuse, or mark stale, when the
  validated ledger is older than 2 minutes. Under load that delays
  validation, this gate can turn a consensus slowdown into RPC errors
  for otherwise cheap queries.

## C11 — Warning (4000) and drop (6000) charges

- Source: `src/libxrpl/resource/Fees.cpp:43-44`;
  `include/xrpl/resource/detail/Logic.h:492-495` (warning charge on
  crossing the warning threshold).
- Measured: 7 warning-threshold crossings across the abusive scenarios;
  each charged feeWarning 4000 once per episode. The warning fired
  before the drop in every abusive run that crossed 5000. Evidence:
  `outputs/S1-burst-single-ip.json`, `outputs/S4-expensive-repeat.json`,
  `outputs/S5-admin-bypass.json`, `outputs/S6-job-queue-saturation.json`,
  `outputs/S7-multi-ip-isolation.json` (`warnings` arrays).
- Gap: the warning is a charge, not an alert. Nothing in the pinned code
  surfaces it to the operator except a journal log line; an operator
  watching only RPC responses sees the 503, not the warning that
  preceded it.

## C12 — Batch-request amplification (no explicit batch-count cap)

- Source: `src/xrpld/rpc/detail/ServerHandler.cpp:640-655` (batch size is
  the params array length; no cap is applied); per-sub-request
  role/resource check inside the loop at `:727-746` and charge at `:922`.
- Measured: NOT EXERCISED in the harness. The simulator models single
  requests only.
- Gap (code-verified only): one HTTP request may carry an arbitrarily
  large batch bounded only by the 1,000,000-byte envelope (C02). Each
  sub-request is charged and balance-checked individually, so the balance
  control does engage — but only after enough sub-requests have been
  charged. Batch amplification depth on a live node is UNMEASURED.
