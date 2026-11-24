#!/usr/bin/env python3
"""build_matrix.py — build the severity-ranked abuse-scenario matrix from the
harness summaries (outputs/S*.json) and the control-effectiveness table.

Severity is a deterministic function of the measured numbers, using the
rubric documented in outputs/matrix.md and below. No severity label is
typed in by hand; the script computes it from the scenario JSONs:

  Request-based scenarios (S0, S1, S4, S5, S6, S7, S9, S10):
    attacker = the client(s) sending abusive load; benign = the rest.
    attacker_success = attacker served / attacker total.
    served_before_reject = attacker requests served before the attacker's
      first rejection (or all attacker requests served, if the attacker was
      never rejected).
    CRITICAL: attacker_success == 1.0 and the attacker was never rejected.
    HIGH:     served_before_reject >= 100.
    MEDIUM:   a control engaged (first_drop_ms is not None) and
      attacker_success > 0.05.
    LOW:      a control engaged and attacker_success <= 0.05, or the
      control behaved exactly as designed with no attacker success.
    INFO:     no abusive traffic in the scenario.
  WebSocket scenario (S2): severity from the slowest close time.
    CRITICAL: a slow client was never closed.
    MEDIUM:   a slow client was closed after holding the connection > 10 s.
    LOW:      all slow clients closed within 10 s.
  Boundary scenarios (S3, S8): severity from bypass count.
    CRITICAL: any oversize request served / any over-range limit served
      unclamped to a public role.
    LOW:      0 bypasses.

Usage:
    python3 scripts/build_matrix.py
Writes:
    outputs/matrix.csv
    outputs/matrix.md
    outputs/matrix.log
"""

import csv
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
OUTPUTS_DIR = os.path.join(PACK, "outputs")

# scenario -> (attacker clients, benign clients, kind)
SCENARIO_ROLES = {
    "S0-baseline": ([], ["c-baseline"], "baseline"),
    "S1-burst-single-ip": (["c-flood"], [], "request"),
    "S2-slow-ws-clients": (["w-slow", "w-mid"], ["w-fast"], "ws"),
    "S3-oversized-payloads": (["c-http", "c-ws"], [], "boundary"),
    "S4-expensive-repeat": (["c-heavy", "c-medium"], ["c-light"], "request"),
    "S5-admin-bypass": (["c-admin"], ["c-public"], "request"),
    "S6-job-queue-saturation": (["c-burst"], [], "request"),
    "S7-multi-ip-isolation": (["c-abusive"],
                               ["c-benign-1", "c-benign-2", "c-benign-3",
                                "c-benign-4"], "request"),
    "S8-page-limit-clamp": (["c-public"], ["c-admin"], "boundary"),
    "S9-connection-limit": (["c-conn-4", "c-conn-5"],
                            ["c-conn-1", "c-conn-2", "c-conn-3"], "request"),
    "S10-pathfind-cap": (["c-pf"], [], "request"),
}

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load(sid):
    with open(os.path.join(OUTPUTS_DIR, sid + ".json")) as f:
        return json.load(f)


def csv_rows(sid):
    with open(os.path.join(OUTPUTS_DIR, sid + ".csv"), newline="") as f:
        return list(csv.DictReader(f))


def severity_request(sid, summary, attackers, benign):
    rows = csv_rows(sid)
    att_total = sum(1 for r in rows if r["client"] in attackers)
    att_served = sum(1 for r in rows
                     if r["client"] in attackers and r["outcome"] == "served")
    ben_total = sum(1 for r in rows if r["client"] in benign)
    ben_served = sum(1 for r in rows
                     if r["client"] in benign and r["outcome"] == "served")
    first_drop = summary["first_drop_ms"]
    att_reject_times = [int(r["t_ms"]) for r in rows
                        if r["client"] in attackers
                        and r["outcome"] != "served"]
    att_first_reject = min(att_reject_times) if att_reject_times else None
    if att_first_reject is not None:
        served_before_reject = sum(
            1 for r in rows
            if r["client"] in attackers and r["outcome"] == "served"
            and int(r["t_ms"]) < att_first_reject)
    else:
        served_before_reject = att_served
    att_rate = (att_served / att_total) if att_total else 0.0
    ben_rate = (ben_served / ben_total) if ben_total else 1.0
    if att_total and att_rate == 1.0 and att_first_reject is None:
        sev, why = "CRITICAL", (
            "attacker success 100%% (%d/%d served) and no control ever "
            "rejected the attacker" % (att_served, att_total))
    elif served_before_reject >= 100:
        sev, why = "HIGH", (
            "%d attacker requests served before the attacker's first "
            "rejection at %s ms"
            % (served_before_reject, att_first_reject))
    elif first_drop is not None and att_rate > 0.05:
        sev, why = "MEDIUM", (
            "control engaged at %s ms but attacker success rate %.1f%%"
            % (first_drop, 100 * att_rate))
    elif first_drop is not None or att_first_reject is not None:
        sev, why = "LOW", (
            "control engaged (attacker first rejection %s ms) and attacker "
            "success rate %.1f%%; benign success %.1f%%"
            % (att_first_reject, 100 * att_rate, 100 * ben_rate))
    else:
        sev, why = "LOW", (
            "control behaved as designed; attacker success %.1f%%, benign "
            "success %.1f%%" % (100 * att_rate, 100 * ben_rate))
    return sev, why, {
        "attacker_total": att_total, "attacker_served": att_served,
        "attacker_success_pct": round(100 * att_rate, 2),
        "benign_total": ben_total, "benign_served": ben_served,
        "benign_success_pct": round(100 * ben_rate, 2),
        "served_before_first_reject": served_before_reject,
    }


def severity_ws(sid, summary, attackers, benign):
    closes = {e["client"]: e["t_ms"] for e in summary["ws_events"]
              if e["event"] == "ws_closed"}
    slowest = max((closes.get(c, None) for c in attackers
                   if closes.get(c) is not None), default=None)
    unclosed = [c for c in attackers if c not in closes]
    if unclosed:
        sev, why = "CRITICAL", "slow client(s) never closed: %s" % ",".join(unclosed)
    elif slowest is not None and slowest > 10000:
        sev, why = "MEDIUM", (
            "slowest client closed at %d ms after holding the connection "
            "with a full 100-message queue" % slowest)
    else:
        sev, why = "LOW", "all slow clients closed within 10 s"
    return sev, why, {
        "attacker_total": len(attackers), "attacker_served": 0,
        "attacker_success_pct": 0.0,
        "benign_total": len(benign), "benign_served": len(benign),
        "benign_success_pct": 100.0,
        "served_before_first_reject": 0,
        "ws_close_ms": closes,
    }


def severity_boundary(sid, summary):
    rows = csv_rows(sid)
    if sid == "S3-oversized-payloads":
        over = [r for r in rows if int(r["payload_bytes"]) > 1000000]
        bypass = sum(1 for r in over if r["outcome"] == "served")
        in_range = [r for r in rows if int(r["payload_bytes"]) <= 1000000]
        if bypass:
            return ("CRITICAL", "%d oversize requests served" % bypass,
                    {"attacker_total": len(over), "attacker_served": bypass,
                     "attacker_success_pct": round(100 * bypass / len(over), 2),
                     "benign_total": len(in_range),
                     "benign_served": sum(1 for r in in_range if r["outcome"] == "served"),
                     "benign_success_pct": round(100 * sum(1 for r in in_range if r["outcome"] == "served") / len(in_range), 2) if in_range else 0.0,
                     "served_before_first_reject": bypass})
        return ("LOW", "%d/%d oversize requests rejected; 0 served" % (len(over) - bypass, len(over)),
                {"attacker_total": len(over), "attacker_served": 0,
                 "attacker_success_pct": 0.0,
                 "benign_total": len(in_range),
                 "benign_served": sum(1 for r in in_range if r["outcome"] == "served"),
                 "benign_success_pct": round(100 * sum(1 for r in in_range if r["outcome"] == "served") / len(in_range), 2) if in_range else 0.0,
                 "served_before_first_reject": 0})
    if sid == "S8-page-limit-clamp":
        over_public = [r for r in rows
                       if r["client"] == "c-public" and "clamped" in r["detail"]]
        bypass = sum(1 for r in rows
                     if r["client"] == "c-public" and "unclamped" in r["detail"])
        other = [r for r in rows if r not in over_public]
        if bypass:
            return ("CRITICAL", "%d over-range limits served unclamped" % bypass,
                    {"attacker_total": len(over_public) + bypass,
                     "attacker_served": bypass,
                     "attacker_success_pct": round(100 * bypass / (len(over_public) + bypass), 2),
                     "benign_total": len(other),
                     "benign_served": sum(1 for r in other if r["outcome"] == "served"),
                     "benign_success_pct": round(100 * sum(1 for r in other if r["outcome"] == "served") / len(other), 2) if other else 0.0,
                     "served_before_first_reject": bypass})
        return ("LOW", "%d over-range public limits clamped, 0 served unclamped" % len(over_public),
                {"attacker_total": len(over_public), "attacker_served": 0,
                 "attacker_success_pct": 0.0,
                 "benign_total": len(other),
                 "benign_served": sum(1 for r in other if r["outcome"] == "served"),
                 "benign_success_pct": round(100 * sum(1 for r in other if r["outcome"] == "served") / len(other), 2) if other else 0.0,
                 "served_before_first_reject": 0})
    return "LOW", "boundary held", {}


def main():
    order = ["S0-baseline", "S1-burst-single-ip", "S2-slow-ws-clients",
             "S3-oversized-payloads", "S4-expensive-repeat", "S5-admin-bypass",
             "S6-job-queue-saturation", "S7-multi-ip-isolation",
             "S8-page-limit-clamp", "S9-connection-limit", "S10-pathfind-cap"]
    matrix = []
    for sid in order:
        summary = load(sid)
        attackers, benign, kind = SCENARIO_ROLES[sid]
        if kind == "baseline":
            sev, why = "INFO", "no abusive traffic; 100% served as expected"
            detail = {"attacker_total": 0, "attacker_served": 0,
                      "attacker_success_pct": 0.0,
                      "benign_total": summary["total_requests"],
                      "benign_served": summary["served"],
                      "benign_success_pct": summary["success_rate_pct"],
                      "served_before_first_reject": 0}
        elif kind == "ws":
            sev, why, detail = severity_ws(sid, summary, attackers, benign)
        elif kind == "boundary":
            sev, why, detail = severity_boundary(sid, summary)
        else:
            sev, why, detail = severity_request(sid, summary, attackers, benign)
        matrix.append({
            "scenario": sid,
            "title": summary["title"],
            "severity": sev,
            "severity_basis": why,
            "total_requests": summary["total_requests"],
            "served": summary["served"],
            "rejected": summary["rejected"],
            "success_rate_pct": summary["success_rate_pct"],
            "first_rejection_ms": summary["first_rejection_ms"],
            "first_drop_ms": summary["first_drop_ms"],
            "p50_latency_ms": summary["latency_ms"]["p50"],
            "p95_latency_ms": summary["latency_ms"]["p95"],
            "throughput_served_per_s": summary["throughput_served_per_s"],
            "attacker_total": detail["attacker_total"],
            "attacker_served": detail["attacker_served"],
            "attacker_success_pct": detail["attacker_success_pct"],
            "benign_total": detail["benign_total"],
            "benign_served": detail["benign_served"],
            "benign_success_pct": detail["benign_success_pct"],
            "served_before_first_reject": detail["served_before_first_reject"],
            "evidence_csv": "outputs/%s.csv" % sid,
            "evidence_json": "outputs/%s.json" % sid,
            "evidence_log": "outputs/%s.log" % sid,
        })

    ranked = sorted(matrix, key=lambda m: (SEVERITY_ORDER[m["severity"]],
                                            m["scenario"]))

    csv_path = os.path.join(OUTPUTS_DIR, "matrix.csv")
    fields = ["scenario", "title", "severity", "severity_basis",
              "total_requests", "served", "rejected", "success_rate_pct",
              "first_rejection_ms", "first_drop_ms", "p50_latency_ms",
              "p95_latency_ms", "throughput_served_per_s", "attacker_total",
              "attacker_served", "attacker_success_pct", "benign_total",
              "benign_served", "benign_success_pct", "served_before_first_reject",
              "evidence_csv", "evidence_json", "evidence_log"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in ranked:
            w.writerow(m)

    lines = [
        "# Abuse-scenario matrix (severity-ranked, SIMULATED)",
        "",
        "All rows are SIMULATED results from the protocol-level simulator "
        "(scripts/simulator.py) at pinned commit "
        "0085a1ff885d6a446369cf73a4430f75af22be55. No live node was load-tested.",
        "Severity is a deterministic function of the measured numbers, using "
        "this rubric:",
        "",
        "- CRITICAL: attacker success 100% and no control ever rejected the "
        "attacker; or a slow WebSocket client never closed; or an oversize "
        "request / over-range limit served to a public role.",
        "- HIGH: 100 or more attacker requests served before the attacker's "
        "first rejection.",
        "- MEDIUM: a control engaged, but attacker success rate above 5%; or "
        "a slow WebSocket client held its connection for more than 10 s "
        "before being closed.",
        "- LOW: a control engaged and attacker success rate at or below 5%; "
        "or a boundary held with zero bypasses.",
        "- INFO: no abusive traffic in the scenario.",
        "",
        "| Scenario | Severity | Total | Served | Rejected | Success % | "
        "First drop (ms) | Attacker success % | Benign success % | "
        "Served before 1st reject |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m in ranked:
        lines.append("| %s | %s | %d | %d | %d | %.2f | %s | %.2f | %.2f | %d |" % (
            m["scenario"], m["severity"], m["total_requests"], m["served"],
            m["rejected"], m["success_rate_pct"],
            m["first_drop_ms"] if m["first_drop_ms"] is not None else "-",
            m["attacker_success_pct"], m["benign_success_pct"],
            m["served_before_first_reject"]))
    lines += [
        "",
        "## Per-scenario severity basis",
        "",
    ]
    for m in ranked:
        lines.append("- **%s** (%s): %s" % (
            m["scenario"], m["severity"], m["severity_basis"]))
    lines += [
        "",
        "## How to reproduce",
        "",
        "Run `bash scripts/run_all.sh` from a fresh clone. Every row links to "
        "its per-request log (for example outputs/S1-burst-single-ip.csv, and "
        "likewise for every scenario), its summary "
        "(outputs/S1-burst-single-ip.json, and likewise for every scenario) "
        "and its unedited run log "
        "(outputs/S1-burst-single-ip.log, and likewise for every scenario). "
        "The same numbers are in outputs/matrix.csv.",
        "",
    ]
    md_path = os.path.join(OUTPUTS_DIR, "matrix.md")
    with open(md_path, "w") as f:
        f.write("\n".join(lines))

    log_lines = [
        "matrix build",
        "script_file: scripts/build_matrix.py",
        "script_sha256: %s" % sha256_file(os.path.abspath(__file__)),
        "scenarios: %d" % len(ranked),
        "severity_counts: %s" % json.dumps(
            {s: sum(1 for m in ranked if m["severity"] == s)
             for s in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]},
            sort_keys=True),
        "csv_file: outputs/matrix.csv",
        "csv_sha256: %s" % sha256_file(csv_path),
        "md_file: outputs/matrix.md",
        "md_sha256: %s" % sha256_file(md_path),
    ]
    with open(os.path.join(OUTPUTS_DIR, "matrix.log"), "w") as f:
        f.write("\n".join(log_lines) + "\n")
    print("matrix: %d scenarios ranked" % len(ranked))
    for m in ranked:
        print("  %s %s" % (m["severity"], m["scenario"]))


if __name__ == "__main__":
    main()
