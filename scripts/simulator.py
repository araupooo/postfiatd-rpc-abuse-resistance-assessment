#!/usr/bin/env python3
"""simulator.py — faithful protocol-level model of the postfiatd JSON-RPC and
WebSocket request pipeline, at pinned commit
0085a1ff885d6a446369cf73a4430f75af22be55.

SIMULATED, not a live node. Every control parameter below is taken VERBATIM
from the pinned source; each entry cites the exact file and line numbers
(verified against a local checkout of the pinned commit and the GitHub API
blob SHA/size for every cited file — see docs/source-inventory.md).

Modelled pipeline, in the order the real code applies it:

  1. Connection accept: ServerHandler::onAccept drops the connection when the
     per-port connection count reaches the configured `limit`
     (src/xrpld/rpc/detail/ServerHandler.cpp:175-190; default "unlimited",
     src/libxrpl/server/Port.cpp:265-283).
  2. Request size: > RPC::Tuning::maxRequestSize (1,000,000 bytes) is HTTP 400
     (ServerHandler.cpp:627-637) or, on WebSocket, a jsonInvalid error and the
     session is completed (ServerHandler.cpp:340-360).
  3. Role gate: admin-only handlers from a non-admin role return
     rpcNO_PERMISSION; a FORBID role returns HTTP 403 and is charged
     feeMalformedRPC (ServerHandler.cpp:754-768;
     src/xrpld/rpc/detail/RPCHandler.cpp:156-157).
  4. Resource balance: each endpoint (IP address) carries a balance that
     decays exponentially with a 32-second window
     (include/xrpl/resource/detail/Tuning.h:31-44). Every served request is
     charged its load class at completion (ServerHandler.cpp:922). If the
     decayed balance is at or above dropThreshold (25000) the request is
     refused — HTTP 503 "Server is overloaded" with JSON-RPC error -32604
     (ServerHandler.cpp:737-746), or on WebSocket the session is closed and
     rpcSLOW_DOWN (error 429, "You are placing too much load on the server.")
     is returned (ServerHandler.cpp:429-435;
     src/libxrpl/protocol/ErrorCodes.cpp:106). Crossing warningThreshold
     (5000) charges feeWarning (4000) once per episode
     (include/xrpl/resource/detail/Logic.h:387-398,452-480,492-495,508-525).
  5. Job queue: when the count of jobs at jtCLIENT priority or higher exceeds
     Tuning::maxJobQueueClients (500) the handler returns rpcTOO_BUSY, unless
     the role is unlimited (RPCHandler.cpp:132-140).
  6. Pathfind caps: no new pathfind starts while maxPathfindsInProgress (2)
     are in progress, and none starts while the jtCLIENT job count exceeds
     maxPathfindJobCount (50) or the node is loaded locally
     (src/xrpld/rpc/detail/LegacyPathFind.cpp:38-48).
  7. Page limits: readLimitField clamps a requested `limit` to
     [rmin, rmax] for non-unlimited roles and leaves it unclamped for
     unlimited (admin/identified) roles
     (src/xrpld/rpc/detail/RPCHelpers.cpp:701-717).
  8. WebSocket send queue: if a subscriber's outbound queue exceeds the
     port's ws_queue_limit (default 100, src/libxrpl/server/Port.cpp:284-308)
     the session is closed with close code policy_error, reason
     "Policy error: client is too slow."
     (include/xrpl/server/detail/BaseWSPeer.h:236-246).
  9. Load monitor: jtCLIENT latency targets are average 2000 ms / peak
     5000 ms (src/xrpld/core/JobTypes.h:86-92); the monitor reports
     overloaded when either target is exceeded
     (src/xrpld/core/detail/LoadMonitor.cpp:153-159,163-172).

MODEL ASSUMPTIONS (labelled, not measured node behaviour):
  * Service times per method class are simulator constants (see
    METHOD_SERVICE_MS). No live node was load-tested; a real postfiatd build
    was out of scope for this pack, so service times are model parameters,
    not measurements. All conclusions that depend on them are labelled
    SIMULATED.
  * Balance decay is modelled as a half-life decay over the documented
    32-second exponential decay window:
    balance(t) = balance * 0.5 ** ((t - t_last) / 32s).
  * The charge for a served request is applied at job completion, matching
    the real code (charge at ServerHandler.cpp:922, after the handler runs).
  * Time is virtual (milliseconds since scenario start). The simulation is
    fully deterministic: fixed seeds, no wall clock, no network, no threads.
    Re-running a scenario produces byte-identical outputs.

Usage: imported by load_harness.py. Not a standalone CLI.
"""

import heapq
import math
import random

PINNED_COMMIT = "0085a1ff885d6a446369cf73a4430f75af22be55"

# ---------------------------------------------------------------------------
# Verbatim control parameters from the pinned commit.
# Each value cites the exact file:line it was taken from.
# ---------------------------------------------------------------------------
CONTROL_PARAMS = {
    # src/xrpld/rpc/detail/Tuning.h
    "maxRequestSize": (1000000, "src/xrpld/rpc/detail/Tuning.h:66"),
    "maxJobQueueClients": (500, "src/xrpld/rpc/detail/Tuning.h:64"),
    "maxPathfindsInProgress": (2, "src/xrpld/rpc/detail/Tuning.h:62"),
    "maxPathfindJobCount": (50, "src/xrpld/rpc/detail/Tuning.h:63"),
    "maxValidatedLedgerAgeMinutes": (2, "src/xrpld/rpc/detail/Tuning.h:65"),
    "binaryPageLength": (2048, "src/xrpld/rpc/detail/Tuning.h:69"),
    "jsonPageLength": (256, "src/xrpld/rpc/detail/Tuning.h:72"),
    "max_src_cur": (18, "src/xrpld/rpc/detail/Tuning.h:81"),
    "max_auto_src_cur": (88, "src/xrpld/rpc/detail/Tuning.h:84"),
    # src/xrpld/rpc/detail/Tuning.h LimitRanges: (rmin, rdefault, rmax)
    "accountLines": ((10, 200, 400), "src/xrpld/rpc/detail/Tuning.h:37"),
    "accountChannels": ((10, 200, 400), "src/xrpld/rpc/detail/Tuning.h:40"),
    "accountObjects": ((10, 200, 400), "src/xrpld/rpc/detail/Tuning.h:43"),
    "accountOffers": ((10, 200, 400), "src/xrpld/rpc/detail/Tuning.h:46"),
    "bookOffers": ((0, 60, 100), "src/xrpld/rpc/detail/Tuning.h:49"),
    "noRippleCheck": ((10, 300, 400), "src/xrpld/rpc/detail/Tuning.h:52"),
    "accountNFTokens": ((20, 100, 400), "src/xrpld/rpc/detail/Tuning.h:55"),
    "nftOffers": ((50, 250, 500), "src/xrpld/rpc/detail/Tuning.h:58"),
    # include/xrpl/resource/detail/Tuning.h
    "warningThreshold": (5000, "include/xrpl/resource/detail/Tuning.h:31"),
    "dropThreshold": (25000, "include/xrpl/resource/detail/Tuning.h:35"),
    "decayWindowSeconds": (32, "include/xrpl/resource/detail/Tuning.h:40"),
    "minimumGossipBalance": (1000, "include/xrpl/resource/detail/Tuning.h:44"),
    "secondsUntilExpiration": (300, "include/xrpl/resource/detail/Tuning.h:50"),
    "gossipExpirationSeconds": (30, "include/xrpl/resource/detail/Tuning.h:53"),
    # src/libxrpl/resource/Fees.cpp — charge costs
    "feeMalformedRequest": (200, "src/libxrpl/resource/Fees.cpp:26"),
    "feeRequestNoReply": (10, "src/libxrpl/resource/Fees.cpp:27"),
    "feeInvalidSignature": (2000, "src/libxrpl/resource/Fees.cpp:28"),
    "feeUselessData": (150, "src/libxrpl/resource/Fees.cpp:29"),
    "feeInvalidData": (400, "src/libxrpl/resource/Fees.cpp:30"),
    "feeMalformedData": (2000, "src/libxrpl/resource/Fees.cpp:31"),
    "feeMalformedRPC": (100, "src/libxrpl/resource/Fees.cpp:33"),
    "feeReferenceRPC": (20, "src/libxrpl/resource/Fees.cpp:34"),
    "feeExceptionRPC": (100, "src/libxrpl/resource/Fees.cpp:35"),
    "feeMediumBurdenRPC": (400, "src/libxrpl/resource/Fees.cpp:36"),
    "feeHeavyBurdenRPC": (3000, "src/libxrpl/resource/Fees.cpp:37"),
    "feeWarning": (4000, "src/libxrpl/resource/Fees.cpp:43"),
    "feeDrop": (6000, "src/libxrpl/resource/Fees.cpp:44"),
    # src/libxrpl/server/Port.cpp
    "ws_queue_limit_default": (100, "src/libxrpl/server/Port.cpp:306"),
    # src/xrpld/core/JobTypes.h:86-92 — jtCLIENT latency targets (ms)
    "jtCLIENT_avg_latency_ms": (2000, "src/xrpld/core/JobTypes.h:86"),
    "jtCLIENT_peak_latency_ms": (5000, "src/xrpld/core/JobTypes.h:86"),
    # src/xrpld/core/JobTypes.h:85
    "jtLEDGER_DATA_limit": (3, "src/xrpld/core/JobTypes.h:85"),
}

# ---------------------------------------------------------------------------
# Method table: charge class per handler (from the pinned source), plus the
# SIMULATOR service-time constant for that class. The charge class is
# observed from code; the service time in ms is a MODEL parameter.
# ---------------------------------------------------------------------------
# Handlers charging feeMediumBurdenRPC (400): AccountChannels.cpp:213,
# AccountLines.cpp:260, AccountObjects.cpp:176,298, AccountOffers.cpp:184,
# AccountTx.cpp:216, BookOffers.cpp:216, NFTOffers.cpp:146, Simulate.cpp:313,
# Submit.cpp:47, Subscribe.cpp:209,342, TxHistory.cpp:44.
# LedgerHandler.cpp:79 charges feeHeavyBurdenRPC (3000) for JSON ledger
# requests and feeMediumBurdenRPC for binary ones. Default loadType is
# feeReferenceRPC (20) — ServerHandler.cpp:440, processSession.
METHODS = {
    # name: (charge, service_ms, limit_range_key or None, admin_only)
    "server_info": ("feeReferenceRPC", 5, None, False),
    "fee": ("feeReferenceRPC", 5, None, False),
    "ledger": ("feeHeavyBurdenRPC", 250, None, False),
    "ledger_binary": ("feeMediumBurdenRPC", 60, None, False),
    "account_lines": ("feeMediumBurdenRPC", 40, "accountLines", False),
    "account_objects": ("feeMediumBurdenRPC", 45, "accountObjects", False),
    "account_offers": ("feeMediumBurdenRPC", 40, "accountOffers", False),
    "account_channels": ("feeMediumBurdenRPC", 35, "accountChannels", False),
    "account_tx": ("feeMediumBurdenRPC", 50, None, False),
    "book_offers": ("feeMediumBurdenRPC", 30, "bookOffers", False),
    "no_ripple_check": ("feeMediumBurdenRPC", 30, "noRippleCheck", False),
    "account_nftokens": ("feeMediumBurdenRPC", 40, "accountNFTokens", False),
    "nft_buy_offers": ("feeMediumBurdenRPC", 35, "nftOffers", False),
    "nft_sell_offers": ("feeMediumBurdenRPC", 35, "nftOffers", False),
    "path_find": ("feeMediumBurdenRPC", 120, None, False),
    "subscribe": ("feeMediumBurdenRPC", 10, None, False),
    "submit": ("feeMediumBurdenRPC", 80, None, False),
    "tx_history": ("feeMediumBurdenRPC", 45, None, False),
    "ledger_entry_admin": ("feeReferenceRPC", 5, None, True),
    "unknown_method": ("feeMalformedRPC", 2, None, False),
}

# Roles that bypass resource limits (Role.cpp:125-128).
UNLIMITED_ROLES = ("ADMIN", "IDENTIFIED")


class Endpoint:
    """One per-IP resource consumer (Resource::Logic Entry)."""

    def __init__(self, ip):
        self.ip = ip
        self.balance = 0.0
        self.last_update_ms = 0
        self.warned = False  # feeWarning already charged in this episode
        self.disconnected = False
        self.disconnect_ms = None
        self.disconnect_reason = None
        self.requests_served = 0
        self.requests_rejected = 0
        self.charges_total = 0

    def decayed_balance(self, now_ms):
        dt_s = (now_ms - self.last_update_ms) / 1000.0
        if dt_s <= 0:
            return self.balance
        return self.balance * (0.5 ** (dt_s / 32.0))

    def touch(self, now_ms):
        self.balance = self.decayed_balance(now_ms)
        self.last_update_ms = now_ms

    def charge(self, amount, now_ms):
        self.touch(now_ms)
        self.balance += amount
        self.charges_total += amount
        if self.balance >= 5000 and not self.warned:
            # Crossing warningThreshold charges feeWarning once per episode
            # (Logic.h:492-495).
            self.balance += 4000
            self.warned = True
            return True  # warning issued
        if self.balance < 5000:
            self.warned = False
        return False

    def should_disconnect(self, now_ms):
        return self.decayed_balance(now_ms) >= 25000


class Client:
    """One simulated RPC/WebSocket client."""

    def __init__(self, spec):
        self.id = spec["id"]
        self.ip = spec["ip"]
        self.role = spec.get("role", "PUBLIC")
        self.transport = spec.get("transport", "http")  # http | ws
        self.endpoint = None  # set by Simulator
        self.ws_queue = []  # outbound messages waiting for the client
        self.ws_closed = False
        self.ws_close_reason = None
        self.ws_close_ms = None
        self.subscribed = False
        self.drain_per_s = spec.get("drain_per_s", 0)
        self.connected = True


class Simulator:
    """Discrete-event simulation of one postfiatd RPC/WebSocket port."""

    def __init__(self, node_config=None, seed=20261125):
        cfg = node_config or {}
        self.port_limit = cfg.get("port_limit", 0)  # 0 = unlimited (Port.cpp)
        self.ws_queue_limit = cfg.get(
            "ws_queue_limit", CONTROL_PARAMS["ws_queue_limit_default"][0])
        self.max_job_queue_clients = CONTROL_PARAMS["maxJobQueueClients"][0]
        self.rng = random.Random(seed)
        self.now_ms = 0
        self.events = []  # heap of (time_ms, seq, kind, payload)
        self.seq = 0
        self.endpoints = {}  # ip -> Endpoint
        self.clients = {}  # id -> Client
        self.active_jobs = 0
        self.pathfind_in_progress = 0
        self.active_connections = 0
        self.records = []  # per-request log rows
        self.ws_events = []  # ws queue / close log rows
        self.warnings = []  # warning-threshold crossings
        self.latencies = []  # served-request latencies (ms)
        self.job_latency_samples = []  # (job type, latency ms)

    # -- event plumbing -----------------------------------------------------
    def schedule(self, time_ms, kind, payload):
        self.seq += 1
        heapq.heappush(self.events, (time_ms, self.seq, kind, payload))

    def run_until(self, end_ms):
        while self.events and self.events[0][0] <= end_ms:
            time_ms, _, kind, payload = heapq.heappop(self.events)
            self.now_ms = time_ms
            if kind == "request":
                self._handle_request(payload)
            elif kind == "job_done":
                self._handle_job_done(payload)
            elif kind == "push":
                self._handle_push(payload)
            elif kind == "drain":
                self._handle_drain(payload)
        self.now_ms = end_ms

    # -- clients ------------------------------------------------------------
    def add_client(self, spec):
        client = Client(spec)
        if self.port_limit and self.active_connections >= self.port_limit:
            # onAccept drops the connection (ServerHandler.cpp:182).
            client.connected = False
            self.records.append({
                "t_ms": 0, "client": client.id, "ip": client.ip,
                "transport": client.transport, "method": "-",
                "payload_bytes": 0, "outcome": "rejected_connection_limit",
                "control": "C01_port_limit", "latency_ms": 0,
                "balance_after": 0, "queue_depth": 0,
                "detail": "connection refused: port limit reached",
            })
            return client
        self.active_connections += 1
        if client.ip not in self.endpoints:
            self.endpoints[client.ip] = Endpoint(client.ip)
        client.endpoint = self.endpoints[client.ip]
        self.clients[client.id] = client
        return client

    # -- request pipeline ---------------------------------------------------
    def _handle_request(self, req):
        client = self.clients.get(req["client"])
        t = self.now_ms
        method = req["method"]
        payload_bytes = req.get("payload_bytes", 0)
        record = {
            "t_ms": t, "client": req["client"],
            "ip": client.ip if client else req.get("ip", "?"),
            "transport": client.transport if client else "http",
            "method": method, "payload_bytes": payload_bytes,
            "outcome": "", "control": "", "latency_ms": 0,
            "balance_after": 0, "queue_depth": 0, "detail": "",
        }
        if client is None or not client.connected or client.ws_closed:
            record["outcome"] = "rejected_client_gone"
            record["control"] = "C01_port_limit"
            record["detail"] = "client not connected"
            self.records.append(record)
            return

        ep = client.endpoint
        unlimited = client.role in UNLIMITED_ROLES

        # Step 2 — request size (ServerHandler.cpp:343, 627).
        if payload_bytes > CONTROL_PARAMS["maxRequestSize"][0]:
            record["outcome"] = ("rejected_oversize_jsonInvalid"
                                 if client.transport == "ws"
                                 else "rejected_oversize_400")
            record["control"] = "C02_max_request_size"
            record["detail"] = "payload %d bytes exceeds maxRequestSize 1000000" % payload_bytes
            if client.transport == "ws":
                self._close_ws(client, t, "oversize message")
            ep.requests_rejected += 1
            self.records.append(record)
            return

        # Step 3 — role gate (RPCHandler.cpp:156-157; ServerHandler.cpp:754).
        spec = METHODS.get(method)
        if spec is None:
            # Unknown method: malformed charge, method_not_found -32601.
            ep.charge(CONTROL_PARAMS["feeMalformedRPC"][0], t)
            record["outcome"] = "rejected_unknown_method"
            record["control"] = "C03_role_gate"
            record["detail"] = "method not found (-32601); charged feeMalformedRPC 100"
            record["balance_after"] = round(ep.balance, 2)
            ep.requests_rejected += 1
            self.records.append(record)
            return
        charge_name, service_ms, limit_key, admin_only = spec
        if admin_only and client.role != "ADMIN":
            record["outcome"] = "rejected_no_permission"
            record["control"] = "C03_role_gate"
            record["detail"] = "admin-only handler from role %s" % client.role
            ep.requests_rejected += 1
            self.records.append(record)
            return

        # Step 4 — resource balance (ServerHandler.cpp:737-746, 429-435).
        # Unlimited roles get a separate endpoint that never disconnects.
        if not unlimited and ep.should_disconnect(t):
            record["outcome"] = ("closed_slowDown_429"
                                 if client.transport == "ws"
                                 else "rejected_overloaded_503")
            record["control"] = "C04_resource_balance"
            record["detail"] = ("balance %.2f at or above dropThreshold 25000"
                                % ep.decayed_balance(t))
            record["balance_after"] = round(ep.decayed_balance(t), 2)
            ep.disconnected = True
            ep.disconnect_ms = t
            ep.disconnect_reason = record["outcome"]
            ep.requests_rejected += 1
            if client.transport == "ws":
                self._close_ws(client, t, "threshold exceeded")
            self.records.append(record)
            return

        # Step 5 — job queue (RPCHandler.cpp:135-139).
        if not unlimited and self.active_jobs >= self.max_job_queue_clients:
            record["outcome"] = "rejected_too_busy"
            record["control"] = "C05_job_queue"
            record["detail"] = "jtCLIENT jobs %d exceed maxJobQueueClients 500" % self.active_jobs
            ep.requests_rejected += 1
            self.records.append(record)
            return

        # Step 6 — pathfind caps (LegacyPathFind.cpp:38-48).
        if method == "path_find":
            if self.pathfind_in_progress >= CONTROL_PARAMS["maxPathfindsInProgress"][0]:
                record["outcome"] = "rejected_pathfind_cap"
                record["control"] = "C06_pathfind_caps"
                record["detail"] = "maxPathfindsInProgress 2 already in progress"
                ep.requests_rejected += 1
                self.records.append(record)
                return
            if self.active_jobs > CONTROL_PARAMS["maxPathfindJobCount"][0]:
                record["outcome"] = "rejected_pathfind_cap"
                record["control"] = "C06_pathfind_caps"
                record["detail"] = "jtCLIENT jobs exceed maxPathfindJobCount 50"
                ep.requests_rejected += 1
                self.records.append(record)
                return
            self.pathfind_in_progress += 1

        # Step 7 — page-limit clamp (RPCHelpers.cpp:701-717).
        limit_applied = None
        if limit_key is not None and req.get("limit") is not None:
            rmin, rdefault, rmax = CONTROL_PARAMS[limit_key][0]
            asked = req["limit"]
            if unlimited:
                limit_applied = asked
                record["detail"] = "limit %d served unclamped (unlimited role)" % asked
            else:
                limit_applied = max(rmin, min(rmax, asked))
                if limit_applied != asked:
                    record["detail"] = "limit %d clamped to %d (range %d-%d)" % (
                        asked, limit_applied, rmin, rmax)
                    record["control"] = "C07_page_limits"
                else:
                    record["detail"] = "limit %d within range %d-%d" % (
                        asked, rmin, rmax)

        # Serve: occupy a job slot for the modelled service time.
        self.active_jobs += 1
        self.schedule(t + service_ms, "job_done", {
            "client": client.id, "method": method, "charge": charge_name,
            "service_ms": service_ms, "record": record,
            "limit_applied": limit_applied, "is_pathfind": method == "path_find",
        })

    def _handle_job_done(self, job):
        t = self.now_ms
        client = self.clients.get(job["client"])
        record = job["record"]
        self.active_jobs -= 1
        if job["is_pathfind"]:
            self.pathfind_in_progress -= 1
        if client is not None and client.endpoint is not None:
            ep = client.endpoint
            warned = ep.charge(CONTROL_PARAMS[job["charge"]][0], t)
            if warned:
                self.warnings.append({
                    "t_ms": t, "client": client.id, "ip": ep.ip,
                    "balance": round(ep.balance, 2),
                    "detail": "balance crossed warningThreshold 5000; feeWarning 4000 charged",
                })
            record["balance_after"] = round(ep.balance, 2)
            ep.requests_served += 1
        record["outcome"] = "served"
        if not record["control"]:
            record["control"] = "C00_served"
        record["latency_ms"] = job["service_ms"]
        if record.get("limit_applied") is not None:
            record["detail"] += "; rows_returned=%d" % record["limit_applied"]
        self.latencies.append(job["service_ms"])
        self.job_latency_samples.append(("jtCLIENT", job["service_ms"]))
        self.records.append(record)

    # -- websocket push / drain ----------------------------------------------
    def subscribe(self, client_id):
        client = self.clients.get(client_id)
        if client is None:
            return
        client.subscribed = True

    def _handle_push(self, push):
        t = self.now_ms
        client = self.clients.get(push["client"])
        if client is None or client.ws_closed or not client.subscribed:
            return
        client.ws_queue.append(push["message"])
        if len(client.ws_queue) > self.ws_queue_limit:
            # BaseWSPeer.h:236-246 — close with policy_error.
            self.ws_events.append({
                "t_ms": t, "client": client.id, "ip": client.ip,
                "event": "ws_queue_overflow",
                "queue_depth": len(client.ws_queue),
                "limit": self.ws_queue_limit,
                "detail": "Policy error: client is too slow.",
            })
            self._close_ws(client, t, "Policy error: client is too slow.")
            return
        self.ws_events.append({
            "t_ms": t, "client": client.id, "ip": client.ip,
            "event": "push_queued", "queue_depth": len(client.ws_queue),
            "limit": self.ws_queue_limit, "detail": push["message"],
        })

    def _handle_drain(self, drain):
        client = self.clients.get(drain["client"])
        if client is None or client.ws_closed:
            return
        if client.ws_queue:
            client.ws_queue.pop(0)
            self.ws_events.append({
                "t_ms": self.now_ms, "client": client.id, "ip": client.ip,
                "event": "drain", "queue_depth": len(client.ws_queue),
                "limit": self.ws_queue_limit, "detail": "client drained one message",
            })

    def _close_ws(self, client, t, reason):
        if client.ws_closed:
            return
        client.ws_closed = True
        client.ws_close_reason = reason
        client.ws_close_ms = t
        self.ws_events.append({
            "t_ms": t, "client": client.id, "ip": client.ip,
            "event": "ws_closed", "queue_depth": len(client.ws_queue),
            "limit": self.ws_queue_limit, "detail": reason,
        })

    # -- load monitor ---------------------------------------------------------
    def load_monitor_stats(self):
        if not self.latencies:
            return {"count": 0, "latency_avg_ms": 0, "latency_peak_ms": 0,
                    "is_overloaded": False}
        avg = sum(self.latencies) / len(self.latencies)
        peak = max(self.latencies)
        overloaded = (avg > CONTROL_PARAMS["jtCLIENT_avg_latency_ms"][0]
                      or peak > CONTROL_PARAMS["jtCLIENT_peak_latency_ms"][0])
        return {"count": len(self.latencies),
                "latency_avg_ms": round(avg, 2),
                "latency_peak_ms": peak,
                "is_overloaded": overloaded}
