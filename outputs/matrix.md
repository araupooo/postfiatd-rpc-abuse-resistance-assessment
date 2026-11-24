# Abuse-scenario matrix (severity-ranked, SIMULATED)

All rows are SIMULATED results from the protocol-level simulator (scripts/simulator.py) at pinned commit 0085a1ff885d6a446369cf73a4430f75af22be55. No live node was load-tested.
Severity is a deterministic function of the measured numbers, using this rubric:

- CRITICAL: attacker success 100% and no control ever rejected the attacker; or a slow WebSocket client never closed; or an oversize request / over-range limit served to a public role.
- HIGH: 100 or more attacker requests served before the attacker's first rejection.
- MEDIUM: a control engaged, but attacker success rate above 5%; or a slow WebSocket client held its connection for more than 10 s before being closed.
- LOW: a control engaged and attacker success rate at or below 5%; or a boundary held with zero bypasses.
- INFO: no abusive traffic in the scenario.

| Scenario | Severity | Total | Served | Rejected | Success % | First drop (ms) | Attacker success % | Benign success % | Served before 1st reject |
|---|---|---|---|---|---|---|---|---|---|
| S5-admin-bypass | CRITICAL | 598 | 314 | 284 | 52.51 | 999 | 100.00 | 5.33 | 298 |
| S1-burst-single-ip | HIGH | 5003 | 1297 | 3706 | 25.92 | 2167 | 25.92 | 100.00 | 1084 |
| S7-multi-ip-isolation | HIGH | 5087 | 1381 | 3706 | 27.15 | 2167 | 25.92 | 100.00 | 1084 |
| S2-slow-ws-clients | MEDIUM | 3 | 3 | 0 | 100.00 | - | 0.00 | 100.00 | 0 |
| S4-expensive-repeat | MEDIUM | 901 | 407 | 494 | 45.17 | 1011 | 17.67 | 100.00 | 21 |
| S6-job-queue-saturation | MEDIUM | 610 | 500 | 110 | 81.97 | 5000 | 81.97 | 100.00 | 0 |
| S10-pathfind-cap | LOW | 7 | 4 | 3 | 57.14 | - | 57.14 | 100.00 | 0 |
| S3-oversized-payloads | LOW | 9 | 4 | 5 | 44.44 | - | 0.00 | 80.00 | 0 |
| S8-page-limit-clamp | LOW | 9 | 8 | 1 | 88.89 | - | 0.00 | 75.00 | 0 |
| S9-connection-limit | LOW | 7 | 3 | 4 | 42.86 | - | 0.00 | 100.00 | 0 |
| S0-baseline | INFO | 420 | 420 | 0 | 100.00 | - | 0.00 | 100.00 | 0 |

## Per-scenario severity basis

- **S5-admin-bypass** (CRITICAL): attacker success 100% (298/298 served) and no control ever rejected the attacker
- **S1-burst-single-ip** (HIGH): 1084 attacker requests served before the attacker's first rejection at 2167 ms
- **S7-multi-ip-isolation** (HIGH): 1084 attacker requests served before the attacker's first rejection at 2167 ms
- **S2-slow-ws-clients** (MEDIUM): slowest client closed at 20000 ms after holding the connection with a full 100-message queue
- **S4-expensive-repeat** (MEDIUM): control engaged at 1011 ms but attacker success rate 17.7%
- **S6-job-queue-saturation** (MEDIUM): control engaged at 5000 ms but attacker success rate 82.0%
- **S10-pathfind-cap** (LOW): control engaged (attacker first rejection 0 ms) and attacker success rate 57.1%; benign success 100.0%
- **S3-oversized-payloads** (LOW): 4/4 oversize requests rejected; 0 served
- **S8-page-limit-clamp** (LOW): 5 over-range public limits clamped, 0 served unclamped
- **S9-connection-limit** (LOW): control engaged (attacker first rejection 0 ms) and attacker success rate 0.0%; benign success 100.0%
- **S0-baseline** (INFO): no abusive traffic; 100% served as expected

## How to reproduce

Run `bash scripts/run_all.sh` from a fresh clone. Every row links to its per-request log (for example outputs/S1-burst-single-ip.csv, and likewise for every scenario), its summary (outputs/S1-burst-single-ip.json, and likewise for every scenario) and its unedited run log (outputs/S1-burst-single-ip.log, and likewise for every scenario). The same numbers are in outputs/matrix.csv.
