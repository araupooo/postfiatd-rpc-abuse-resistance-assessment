# Operator remediation report

Severity-ranked. Each item cites the control, the measured evidence,
and the concrete change. Severity comes from `outputs/matrix.md`
(deterministic rubric over the measured numbers).

## 1. CRITICAL — Audit and constrain unlimited roles (C03, C04, C07)

- **Finding (S5, CRITICAL):** an ADMIN client served 298/298 heavy
  requests with 0 rejections while the identical PUBLIC load was
  dropped after 16 served. ADMIN and IDENTIFIED roles bypass the
  resource balance, the job-queue cap, and page-limit clamping.
  Evidence: `outputs/S5-admin-bypass.json`,
  `outputs/S8-page-limit-clamp.csv`.
- **Remediation:**
  1. Bind admin ports to loopback only (the example config already does
     this for `[port_rpc_admin_local]` and `[port_ws_admin_local]` —
     verify the deployed config matches; do not expose an admin port
     publicly).
  2. Keep the `admin` network list as narrow as possible; review the
     `secure_gateway` / IDENTIFIED classification and remove any
     endpoint that does not need it.
  3. Treat admin credentials as the highest-value secret on the node:
     a compromised admin credential faces no resource control at all.
- **Priority:** first. This is the only finding where a control is
  absent rather than merely slow.

## 2. HIGH — Set a per-port connection limit (C01)

- **Finding (S9, LOW in isolation):** the limit works (2/2 excess
  refused at limit 3), but the default is "unlimited" and the example
  config sets no limit on any port.
- **Remediation:** set `limit` on every public port (`[port_ws_public]`,
  any public HTTP port) to a value the operator has actually measured
  against legitimate peak connections — e.g. start from 2x observed
  peak and tighten from there. Record the chosen value and the reason;
  an unset limit is not a default, it is a missing control.
- **Priority:** second. Cheap to set, closes the cheapest flood vector
  (connection exhaustion) before the balance control is even reached.

## 3. HIGH — Reduce the work admitted before the balance engages (C04, C05)

- **Finding (S1, HIGH):** 1084 requests served before the first refusal
  of a 500/s flood; (S6, MEDIUM) 500 concurrent heavy jobs admitted
  before `rpcTOO_BUSY` engaged. Both gaps share a cause: charges land
  at job completion, so a burst passes the balance check before any
  charge is applied.
- **Remediation:**
  1. Consider charging an estimated cost at dispatch (before the job
     runs) in addition to the completion charge, so a burst is throttled
     while it is still arriving. This is a code change; validate it
     against the same scenarios in this pack before deploying.
  2. Until then, lower the effective exposure with a reverse proxy or
     load balancer in front of the public port: per-IP request-rate
     limiting at the edge (e.g. 50 requests/s per IP, well above the
     ~27/s reference-query drop equilibrium) absorbs the first 2 seconds
     that the balance control currently concedes.
  3. Do not rely on the job-queue cap as a rate control: it is a
     concurrency cap, and 500 concurrent heavy jobs is a large admission.
- **Priority:** third. Requires either a code change or edge tooling;
  the edge limiter is the faster mitigation.

## 4. MEDIUM — Slow WebSocket clients hold a full queue too long (C08)

- **Finding (S2, MEDIUM):** a client draining at 1/s held its
  connection for 11.2 s, and at 5/s for 20.0 s, each with 101 queued
  messages, before being closed.
- **Remediation:** lower `send_queue_limit` on the public WebSocket port
  (the default is 100; the example admin port uses 500). A limit of
  25-50 on a public port closes a stalled subscriber in ~3-5 s at
  10 pushes/s instead of 11-20 s, at the cost of closing legitimate
  slow consumers sooner — measure the legitimate drain rate first.
- **Priority:** fourth. Bounded impact per connection; the per-connection
  nature of the limit means the total exposure scales with connection
  count, which item 2 bounds.

## 5. MEDIUM — Make the warning visible (C11)

- **Finding:** 7 warning-threshold crossings were recorded across the
  abusive scenarios, and the warning fired before the drop in every run
  that crossed 5000. But the warning is only a charge plus a journal
  log line; an operator watching RPC responses sees the 503, not the
  warning that preceded it.
- **Remediation:** alert on the resource-manager journal lines that
  record warning-threshold crossings, and on `server_overloaded`
  (-32604) / `slowDown` (429) responses. The warning is a ~2-second
  early signal in the S1 flood (warning at ~5000 balance, drop at
  25000) — enough to page before the drop, not after it.
- **Priority:** fifth. Observability only; no behaviour change.

## 6. LOW — Close the remaining gaps by measurement (C10, C12, C06)

- **Validated-ledger gate (C10):** measure the gate's behaviour under
  a stale validated ledger (2-minute threshold) on a test node; confirm
  which cheap queries start failing when validation stalls.
- **Batch amplification (C12):** measure how deep a batch can go inside
  the 1 MB envelope on a test node, and whether a per-batch sub-request
  cap is warranted. Until measured, treat large batches from public
  clients as suspicious.
- **Pathfind job cap (C06):** the 50-job cap was not exercised; confirm
  it engages under a 50+ job backlog.
- **Priority:** sixth. These are measurement tasks, not emergencies;
  none of them produced a bypass in this pack.

## What NOT to change

- Do not raise the drop threshold to "fix" legitimate single-IP
  throttling (finding: ~1.35 medium queries/s eventually trips the
  drop). Raising it weakens the flood control proportionally. If a
  legitimate single-IP client needs sustained medium-burden access,
  give it its own identified endpoint with an explicit rate agreement
  at the edge, and monitor it — do not weaken the shared threshold.
- Do not raise `maxRequestSize` above 1,000,000 bytes: the boundary is
  exact and the cap is doing its job (S3: 5/5 oversize rejected).
- Do not raise `ws_queue_limit` on the public port: it is the only
  control that closes a stalled subscriber.
