#!/usr/bin/env python3
"""load_harness.py — run abuse scenarios against the protocol simulator.

Usage:
    python3 scripts/load_harness.py [SCENARIO_ID ...]
    (no arguments: run every scenario in scenarios/*.json)

For each scenario this script writes, under outputs/:
    S0-baseline.csv   — per-request log (one row per request, virtual time)
    S0-baseline.json  — summary: outcome/control counts, latency percentiles,
                 throughput, per-client and per-endpoint breakdowns,
                 time-to-first-rejection, time-to-drop, ws events, warnings
    S0-baseline.log   — unedited run log, including the full SHA-256 of the scenario
                 file and of scripts/simulator.py, and the summary numbers
(the same three files exist for every scenario id S0-baseline .. S10-pathfind-cap)

All outputs are deterministic: virtual clock, fixed seeds, no wall clock,
no network. Re-running produces byte-identical files (verified by
run_all.sh, which diffs a second run).

Scenario file format (scenarios/S0-baseline.json and likewise):
    id, title, seed, duration_ms, node {port_limit, ws_queue_limit},
    clients [{id, ip, role, transport, drain_per_s}],
    streams [{client, method, kind: rate|burst|fixed, ...}],
    pushes [{client, interval_ms, duration_ms, message}]
"""

import csv
import hashlib
import json
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from simulator import Simulator, CONTROL_PARAMS, PINNED_COMMIT  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
SCENARIOS_DIR = os.path.join(PACK, "scenarios")
OUTPUTS_DIR = os.path.join(PACK, "outputs")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def percentile(sorted_values, pct):
    if not sorted_values:
        return 0
    idx = (pct / 100.0) * (len(sorted_values) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = idx - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def run_scenario(scenario_path):
    with open(scenario_path, "rb") as f:
        scenario_bytes = f.read()
    scenario_sha = hashlib.sha256(scenario_bytes).hexdigest()
    sc = json.loads(scenario_bytes.decode("utf-8"))
    sid = sc["id"]
    duration_ms = sc["duration_ms"]
    sim = Simulator(node_config=sc.get("node", {}), seed=sc.get("seed", 20261125))

    for cspec in sc.get("clients", []):
        sim.add_client(cspec)

    # Subscription handshake: a push stream models a client that has already
    # completed `subscribe` (the subscribe request itself is one of the
    # scenario streams and is charged/served by the pipeline).
    for push in sc.get("pushes", []):
        sim.subscribe(push["client"])

    rng = random.Random(sc.get("seed", 20261125))
    stream_no = 0
    for stream in sc.get("streams", []):
        stream_no += 1
        s_rng = random.Random(sc.get("seed", 20261125) * 1000 + stream_no)
        client_id = stream["client"]
        method = stream["method"]
        jitter = stream.get("jitter", 0.1)
        kind = stream.get("kind", "rate")
        if kind == "rate":
            rate = stream["rate_per_s"]
            dur = stream.get("duration_ms", duration_ms)
            interval_ms = 1000.0 / rate
            t = 0.0
            while t < dur:
                sim.schedule(int(round(t)), "request", {
                    "client": client_id, "method": method,
                    "payload_bytes": stream.get("payload_bytes", 512),
                    "limit": stream.get("limit"),
                })
                step = interval_ms * (1.0 + s_rng.uniform(-jitter, jitter))
                t += step
        elif kind == "burst":
            at = stream.get("at_ms", 0)
            for _ in range(stream["count"]):
                sim.schedule(at, "request", {
                    "client": client_id, "method": method,
                    "payload_bytes": stream.get("payload_bytes", 512),
                    "limit": stream.get("limit"),
                })
        elif kind == "fixed":
            for item in stream["items"]:
                sim.schedule(item["at_ms"], "request", {
                    "client": client_id, "method": method,
                    "payload_bytes": item.get("payload_bytes", 512),
                    "limit": item.get("limit"),
                })
        else:
            raise ValueError("unknown stream kind %r" % kind)

    for push in sc.get("pushes", []):
        interval = push["interval_ms"]
        dur = push.get("duration_ms", duration_ms)
        t = 0
        while t < dur:
            sim.schedule(t, "push", {
                "client": push["client"], "message": push.get("message", "ledger_closed"),
            })
            t += interval
        # client drain events
        client = next((c for c in sc.get("clients", [])
                       if c["id"] == push["client"]), None)
        drain_per_s = client.get("drain_per_s", 0) if client else 0
        if drain_per_s and drain_per_s > 0:
            d_interval = 1000.0 / drain_per_s
            t = 0.0
            while t < dur:
                sim.schedule(int(round(t)), "drain", {"client": push["client"]})
                t += d_interval

    sim.run_until(duration_ms)

    # -- per-request CSV -----------------------------------------------------
    csv_path = os.path.join(OUTPUTS_DIR, sid + ".csv")
    rows = sorted(sim.records, key=lambda r: (r["t_ms"], r["client"], r["method"]))
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "t_ms", "client", "ip", "transport", "method", "payload_bytes",
            "outcome", "control", "latency_ms", "balance_after",
            "queue_depth", "detail"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # -- summary -------------------------------------------------------------
    outcomes = {}
    controls = {}
    for r in sim.records:
        outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
        controls[r["control"]] = controls.get(r["control"], 0) + 1
    served_lat = sorted(sim.latencies)
    first_reject = None
    first_drop = None
    for r in sim.records:
        if r["outcome"] != "served" and first_reject is None:
            first_reject = r["t_ms"]
        if r["outcome"] in ("rejected_overloaded_503", "closed_slowDown_429") \
                and first_drop is None:
            first_drop = r["t_ms"]
    per_client = {}
    for r in sim.records:
        pc = per_client.setdefault(r["client"], {"served": 0, "rejected": 0})
        if r["outcome"] == "served":
            pc["served"] += 1
        else:
            pc["rejected"] += 1
    per_endpoint = {}
    for ip, ep in sim.endpoints.items():
        per_endpoint[ip] = {
            "final_balance": round(ep.decayed_balance(duration_ms), 2),
            "served": ep.requests_served,
            "rejected": ep.requests_rejected,
            "charges_total": ep.charges_total,
            "disconnected": ep.disconnected,
            "disconnect_ms": ep.disconnect_ms,
            "disconnect_reason": ep.disconnect_reason,
        }
    total = len(sim.records)
    served = outcomes.get("served", 0)
    summary = {
        "scenario": sid,
        "title": sc.get("title", ""),
        "pinned_commit": PINNED_COMMIT,
        "simulated": True,
        "duration_ms": duration_ms,
        "total_requests": total,
        "served": served,
        "rejected": total - served,
        "success_rate_pct": round(100.0 * served / total, 4) if total else 0.0,
        "throughput_served_per_s": round(
            served / (duration_ms / 1000.0), 4) if duration_ms else 0.0,
        "latency_ms": {
            "count": len(served_lat),
            "min": min(served_lat) if served_lat else 0,
            "p50": round(percentile(served_lat, 50), 2),
            "p95": round(percentile(served_lat, 95), 2),
            "p99": round(percentile(served_lat, 99), 2),
            "max": max(served_lat) if served_lat else 0,
            "mean": round(statistics.fmean(served_lat), 2) if served_lat else 0,
        },
        "outcomes": dict(sorted(outcomes.items())),
        "controls": dict(sorted(controls.items())),
        "first_rejection_ms": first_reject,
        "first_drop_ms": first_drop,
        "per_client": dict(sorted(per_client.items())),
        "per_endpoint": dict(sorted(per_endpoint.items())),
        "ws_events": sim.ws_events,
        "warnings": sim.warnings,
        "load_monitor": sim.load_monitor_stats(),
    }
    json_path = os.path.join(OUTPUTS_DIR, sid + ".json")
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
        f.write("\n")

    # -- unedited run log ----------------------------------------------------
    sim_path = os.path.join(HERE, "simulator.py")
    log_lines = [
        "scenario: %s" % sid,
        "title: %s" % sc.get("title", ""),
        "pinned_commit: %s" % PINNED_COMMIT,
        "scenario_file: scenarios/%s.json" % sid,
        "scenario_sha256: %s" % scenario_sha,
        "simulator_file: scripts/simulator.py",
        "simulator_sha256: %s" % sha256_file(sim_path),
        "harness_file: scripts/load_harness.py",
        "harness_sha256: %s" % sha256_file(os.path.abspath(__file__)),
        "duration_ms: %d" % duration_ms,
        "total_requests: %d" % total,
        "served: %d" % served,
        "rejected: %d" % (total - served),
        "success_rate_pct: %.4f" % summary["success_rate_pct"],
        "throughput_served_per_s: %.4f" % summary["throughput_served_per_s"],
        "latency_ms: min=%s p50=%s p95=%s p99=%s max=%s mean=%s" % (
            summary["latency_ms"]["min"], summary["latency_ms"]["p50"],
            summary["latency_ms"]["p95"], summary["latency_ms"]["p99"],
            summary["latency_ms"]["max"], summary["latency_ms"]["mean"]),
        "outcomes: %s" % json.dumps(summary["outcomes"], sort_keys=True),
        "controls: %s" % json.dumps(summary["controls"], sort_keys=True),
        "first_rejection_ms: %s" % first_reject,
        "first_drop_ms: %s" % first_drop,
        "load_monitor: %s" % json.dumps(summary["load_monitor"], sort_keys=True),
        "per_client: %s" % json.dumps(summary["per_client"], sort_keys=True),
        "per_endpoint: %s" % json.dumps(summary["per_endpoint"], sort_keys=True),
        "warnings: %d" % len(sim.warnings),
        "ws_events: %d" % len(sim.ws_events),
        "csv_file: outputs/%s.csv" % sid,
        "csv_sha256: %s" % sha256_file(csv_path),
        "json_file: outputs/%s.json" % sid,
        "json_sha256: %s" % sha256_file(json_path),
    ]
    log_path = os.path.join(OUTPUTS_DIR, sid + ".log")
    with open(log_path, "w") as f:
        f.write("\n".join(log_lines) + "\n")
    print("scenario %s: total=%d served=%d rejected=%d success=%.2f%% "
          "first_drop_ms=%s" % (
              sid, total, served, total - served,
              summary["success_rate_pct"], first_drop))
    return summary


def main(argv):
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    if argv:
        wanted = argv
    else:
        wanted = sorted(
            f[:-5] for f in os.listdir(SCENARIOS_DIR) if f.endswith(".json"))
    for sid in wanted:
        path = os.path.join(SCENARIOS_DIR, sid + ".json")
        if not os.path.exists(path):
            raise SystemExit("scenario file not found: %s" % path)
        run_scenario(path)


if __name__ == "__main__":
    main(sys.argv[1:])
