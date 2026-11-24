# Source inventory

Pinned commit: `0085a1ff885d6a446369cf73a4430f75af22be55`
(2026-10-10, "Merge pull request #50 from postfiatorg/hotfix/upstream-hardening-1.0.9")

Every file below was verified the same way: the local checkout's
`git hash-object` output equals the GitHub API blob SHA for the pinned
commit, and the byte sizes agree. Line numbers were read with `grep -n`
on the local checkout of the pinned commit, never from a fetched raw file.

| File | Blob SHA (git) | Size (bytes) | Lines cited |
|---|---|---|---|
| src/xrpld/rpc/detail/Tuning.h | 4f4a8be1bf768281fe6f195083adee5ca180d701 | 3330 | 37, 40, 43, 46, 49, 52, 55, 58, 60, 62-66, 69, 72, 77, 81, 84 |
| src/xrpld/rpc/detail/ServerHandler.cpp | c574cf8d7636d701bb635d08ed64e25dc74f8e65 | 40596 | 175-190, 340-360, 403-419, 429-435, 607-608, 627-637, 640-655, 729-746, 754-768, 922 |
| src/xrpld/rpc/detail/RPCHandler.cpp | b2e4c2c4409320df20d2d46e3793b4093bf46b1f | 8015 | 132-140, 156-157, 194 |
| src/libxrpl/resource/Fees.cpp | d4565d9226963acb9c3720c2b8efb4db2d4af71e | 2139 | 26-44 |
| include/xrpl/resource/detail/Tuning.h | 62234c356933c998a07b223dae2ef1a2bead3646 | 1932 | 31, 35, 40, 44, 50, 53 |
| include/xrpl/resource/detail/Logic.h | 0fc5a9035ac6679ffc7961f7ecfdc9d354e7c075 | 18166 | 204, 218-248, 269-330, 387-398, 452-480, 492-495, 508-525 |
| src/libxrpl/server/Port.cpp | 95709fc298b46dd790447496af4a99a322871132 | 11117 | 265-283, 284-308 |
| src/xrpld/core/JobTypes.h | 29863893d974304b19bbbe16b384b099afc1e23f | 7845 | 85-93 |
| src/xrpld/core/detail/JobQueue.cpp | 1ea1df51abb7fcc1f220113e64e1b13ae4e9101a | 12713 | 127-134, 342-346, 373-380, 441-448 |
| src/xrpld/rpc/detail/Role.cpp | 94da34efa228b0fa96574e1c9f9de110ded06fcc | 10089 | 125-128, 131-154 |
| src/libxrpl/protocol/ErrorCodes.cpp | ec295343cef1b5c8665aef3b0838db709f3c8fa2 | 11482 | 106 |
| src/xrpld/rpc/handlers/LedgerHandler.cpp | 8987f2d07eb3c2401a29d8e1ecb6c5f55f7634c3 | 12624 | 79 |
| src/xrpld/core/detail/LoadMonitor.cpp | 98fa959d6caa8e585c8052937818f7331f9d84ae | 5299 | 50-51, 144-172, 200 |
| src/libxrpl/server/JSONRPCUtil.cpp | 69adb235ee7cbd36ef026f1edf7e6696c9b889c1 | 5085 | 123-124, 132-133 |
| cfg/postfiatd-example.cfg | b569f0f3f33252693968710c90ece5b5a394b1e2 | 57654 | 1435-1478 |
| src/xrpld/core/JobTypeData.h | 89532c15d9f955104305bca018d86e9a39d00ba2 | 2860 | 66 |
| src/xrpld/core/LoadMonitor.h | c65a0e687071191be658fbab140444c052043f61 | 2542 | 50-90 |
| include/xrpl/server/detail/BaseWSPeer.h | 027b0cbf7ca1725667d1b4155ba7e8aee90a770d | 14321 | 59, 236-246, 270, 325, 359, 371 |
| src/xrpld/rpc/detail/RPCHelpers.cpp | edb91611bec2b7b581511cc3e85b6087dd40941d | 35977 | 352, 701-717, 1061 |
| src/xrpld/rpc/handlers/AccountLines.cpp | 146a9527a931ea65d39a44d2e8c5a7bc76995b19 | 9191 | 119-124 |
| src/xrpld/rpc/detail/LegacyPathFind.cpp | 35220178bf5f6d0c52d8988f55977833bcdb67b0 | 2230 | 38-48 |
| src/xrpld/rpc/detail/Handler.h | 8c263a90aba74499b44eecff36b1dc4d4515087e | 4228 | 109 |

## What each cited file establishes

- **Tuning.h (RPC)**: all per-method page-limit ranges, pathfind caps,
  the 500-client job cap, the 2-minute validated-ledger age, the
  1,000,000-byte request cap, and the binary/JSON page lengths.
- **ServerHandler.cpp**: connection accept/drop, WebSocket and HTTP
  oversize handling, the batch loop (no batch-count cap), the
  resource-balance refusal (HTTP 503 / error -32604), the WebSocket
  slow-down close (error 429), the per-request charge, and the
  log-duration thresholds (1 s warn, 10 s error).
- **RPCHandler.cpp**: the 500-job `rpcTOO_BUSY` gate, the admin-only
  `rpcNO_PERMISSION` gate, and the per-command load event.
- **Fees.cpp**: the complete charge table (reference 20, medium 400,
  heavy 3000, malformed 100, exception 100, warning 4000, drop 6000).
- **Tuning.h (resource)**: warn 5000, drop 25000, decay window 32 s,
  gossip floor 1000, entry expiry 300 s, gossip expiry 30 s.
- **Logic.h**: per-endpoint balance table, the disposition function
  (warn/drop), the charge function, and the disconnect function.
- **Port.cpp**: `limit` defaults to "unlimited"; `send_queue_limit`
  defaults to 100.
- **JobTypes.h / JobQueue.cpp**: jtCLIENT latency targets (avg 2000 ms /
  peak 5000 ms), jtLEDGER_DATA limit 3, job deferral below the limit.
- **Role.cpp**: ADMIN and IDENTIFIED roles are unlimited (bypass resource
  limits).
- **ErrorCodes.cpp**: `rpcSLOW_DOWN` ("You are placing too much load on
  the server.", 429).
- **LedgerHandler.cpp**: JSON ledger charges heavy (3000), binary ledger
  charges medium (400).
- **LoadMonitor.cpp / LoadMonitor.h / JobTypeData.h**: latency-target
  plumbing and the overloaded flag.
- **JSONRPCUtil.cpp**: HTTP status strings, including 429 Too Many
  Requests and 503 Server is overloaded.
- **postfiatd-example.cfg**: the shipped example port layout; no port
  sets `limit`.
- **BaseWSPeer.h**: the WebSocket send-queue overflow close
  (policy_error, "Policy error: client is too slow.").
- **RPCHelpers.cpp**: `readLimitField` clamping and the validated-ledger
  staleness check.
- **AccountLines.cpp**: a representative handler applying the page limit.
- **LegacyPathFind.cpp**: the pathfind concurrency caps.
- **Handler.h**: the validated-ledger age gate for WebSocket handlers.
