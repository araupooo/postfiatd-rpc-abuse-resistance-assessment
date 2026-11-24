# Findings report

Pinned commit: `0085a1ff885d6a446369cf73a4430f75af22be55`.
All load numbers below are SIMULATED (protocol simulator,
`scripts/simulator.py`); all control parameters are OBSERVED from the
pinned code. Full per-request logs: `outputs/S*.csv`. Severity ranking:
`outputs/matrix.md`.

## Headline findings

1. **The resource balance is the only control that stops a flood — and
   it lets a lot through first.** A single public IP sending cheap
   reference queries at 500/s (S1) was served 1084 requests before the
   first refusal at 2167 ms, and 1297 of 5003 in total (25.92%). After
   the drop the endpoint kept serving a trickle of 27.19 requests/s
   rather than staying closed. Evidence: `outputs/S1-burst-single-ip.json`.
2. **Charge class decides how fast an attacker is stopped, by a factor
   of ~150.** At 10 requests/s from separate IPs (S4), heavy JSON
   `ledger` queries (charge 3000) were dropped after 16 served (first
   drop 1011 ms); medium `account_lines` (charge 400) after 90 served;
   light `server_info` (charge 20) never dropped in 30 s (301/301).
   Evidence: `outputs/S4-expensive-repeat.json`.
3. **Admin and identified roles bypass every resource control.**
   Identical heavy load (S5): the ADMIN client served 298/298 with 0
   rejections; the PUBLIC client served 16/300 and was dropped at
   999 ms. The bypass is by design (`Role.cpp:125-128`), and it also
   bypasses page-limit clamping (S8: admin limit 10000 served
   unclamped). Evidence: `outputs/S5-admin-bypass.json`,
   `outputs/S8-page-limit-clamp.csv`.
4. **Benign traffic is isolated from a flood.** While one IP flooded at
   500/s (S7), four benign IPs at 2/s each served 21/21 requests each
   (100%). The balance is per-endpoint (per IP), and the flood did not
   degrade anyone else. Evidence: `outputs/S7-multi-ip-isolation.json`.
5. **The job-queue cap holds exactly at 500, but 500 concurrent heavy
   jobs is a large admission.** A burst of 600 simultaneous heavy
   requests (S6): 500 served, 100 rejected `rpcTOO_BUSY` at t=0 ms.
   A probe 5 s later was refused 10/10 with 503 — the resource balance,
   charged at job completion, was still above the drop threshold long
   after the jobs drained. Evidence:
   `outputs/S6-job-queue-saturation.json`.
6. **Slow WebSocket clients are closed, but only after holding a full
   queue for 11-20 s.** At 10 pushes/s against a 100-message queue
   (S2), the 1/s-drain client closed at 11200 ms and the 5/s-drain
   client at 20000 ms, both at queue depth 101; the 20/s-drain client
   was never closed. Evidence: `outputs/S2-slow-ws-clients.json`.
7. **The 1 MB request cap is exact.** Requests of 999,999 and 1,000,000
   bytes served; 1,000,001, 2,000,000 and 5,000,000 bytes rejected (S3).
   On WebSocket an oversize message also closes the session, so the
   client's next in-range request was refused as well. Evidence:
   `outputs/S3-oversized-payloads.csv`.
8. **Page limits clamp exactly as documented, for public roles only.**
   5 of 5 over-range public limits clamped (S8: 10000->400, 5->10,
   0->10, 500->100, 1000->400); the admin's 10000 was served unclamped.
   Evidence: `outputs/S8-page-limit-clamp.csv`.
9. **The connection limit works, but it is off by default.** With
   `limit = 3` (S9), 2 of 2 excess connections were refused and 3 of 3
   within-limit connections served. The default is "unlimited", and the
   shipped example config sets no limit on any port. Evidence:
   `outputs/S9-connection-limit.json`.
10. **Pathfind caps work exactly.** A burst of 5 pathfinds (S10): 2
    served, 3 rejected at t=0 ms; a second burst of 2 after completion:
    2 served, 0 rejected. Evidence: `outputs/S10-pathfind-cap.csv`.
11. **The load monitor never fires.** Across all 11 scenarios the worst
    average latency was 250.00 ms and the worst peak 250 ms, against
    targets of 2000/5000 ms; `is_overloaded` fired 0 times. It is a
    lagging indicator, not a first-line abuse control. Evidence: every
    `outputs/S*.json` (`load_monitor` block).
12. **Baseline is clean.** Light realistic load (S0: 7 reference
    queries/s for 60 s): 420/420 served, 0 warnings, 0 rejections.
    Evidence: `outputs/S0-baseline.json`.

## The arithmetic behind the headline

With a 32-second half-life decay, the steady-state balance for a
sustained charge rate r is about r * 46.2. The drop threshold (25000)
is therefore crossed by any sustained rate above ~542 charge/s from one
IP; the warning threshold (5000) above ~108 charge/s. Consequences an
operator should know:

- 27 reference queries/s from one IP eventually trips the drop.
- 1.35 medium-burden queries/s from one IP eventually trips the drop.
- 0.18 heavy queries/s from one IP eventually trips the drop.
- A single IP doing 1 medium query/s gets warned (after ~15 s) but
  never dropped — its equilibrium balance is ~18,500.

This is arithmetic on the pinned constants, confirmed by the harness
(S4 light at 200 charge/s: no warning in 30 s, equilibrium 9,232;
S4 medium at 4000 charge/s: dropped after 90 served).

## What this pack does not establish

- Live-node latencies, throughput, or error rates (service times are
  model constants).
- Behaviour under real ledger-close push rates or real incidents.
- The validated-ledger freshness gate (C10) and batch amplification
  depth (C12): code-verified only, UNMEASURED in the harness.
