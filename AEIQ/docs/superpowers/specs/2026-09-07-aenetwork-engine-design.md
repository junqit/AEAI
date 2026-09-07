# AENetworkEngine — Outbound Client Network Engine

**Date:** 2026-09-07
**Status:** Approved (Approach B)
**Owner:** tianjunqi

## 1. Goal

Create `AENetworkEngine` under `Network/` — an **outbound client** network engine that lets the
AEIQ service connect to remote TCP/UDP endpoints, send `AENetReq`, and await the matched `AENetRsp`.
It mirrors the capabilities of the iOS `AENetSocketEngine.swift` (connect/disconnect, packetized
serial send, async receive+parse, request/response matching, UDP heartbeat, connection state
machine).

The existing inbound UDP server (`AESocketServer` on :8888 → `AENetRouteCenter`) is **untouched**.
This engine is additive — a standalone outbound tool business code can instantiate when it needs to
reach out to a peer that speaks the AEPacket protocol.

## 2. Reference

- Source of capability truth: `Client/CocoaPods/AENetworkEngine/NetCore/Socket/AENetSocketEngine.swift`
- The engine mirrors its **capabilities**, not its exact wire format. The Python engine speaks the
  existing Python AEPacket protocol (AEDataType REQUEST/RESPONSE/HEARTBEAT; see `Network/Socket/Packet/AEPacket.py`).

## 3. Key decisions (confirmed with user)

| Decision | Choice |
|---|---|
| Role | Outbound client engine (existing inbound server untouched) |
| Transport | TCP + UDP (faithful mirror of Swift) |
| Concurrency | Hybrid — blocking sockets in threads + reuse `AEPacketParser`/`AEPacketReceiveBuffer`; bridge to asyncio via `asyncio.Future` + `loop.call_soon_threadsafe` |
| File organization | Approach B: engine + client transport split |
| Streaming | V1 single-shot request/response; multi-chunk streaming is a documented future extension |

## 4. Reused components (no duplication)

| Component | Path | Role in engine |
|---|---|---|
| `AEPacket.packets_from_data` | `Network/Socket/Packet/AEPacket.py` | send-side fragmentation |
| `AEPacketHeader`, `calculate_crc16` | same | header codec + CRC |
| `AEPacketParser` | `Network/Socket/Packet/AEPacketParser.py` | TCP stream receive parse (`on_response_callback`) |
| `AEPacketReceiveBuffer` | `Network/Socket/Packet/AEPacketReceiveBuffer.py` | UDP datagram receive parse (`on_packet_received`) |
| `AEPacketPool`, `AEReceiveBuffer` | same dir | fragmentation reassembly + 粘包/半包 (used by the two parsers) |
| `AENetReq`, `AENetRsp` | `Network/Core/` | request/response models (`to_bytes`/`from_bytes`, `req.requestId`, `user`) |

`AEDataType` values used: `REQUEST=0x01` (send), `RESPONSE=0x02` (receive), `HEARTBEAT=0x03`
(UDP keepalive), `PING`/`PONG` reserved.

## 5. Module structure

```
Network/
├─ AENetworkEngine.py                  # NEW — orchestrator
├─ Socket/Connection/
│   └─ AENetSocketClient.py            # NEW — raw TCP/UDP client transport
├─ Socket/Packet/  (reuse)
└─ Core/           (reuse)
```

## 6. New module: `AENetSocketClient` (raw transport)

Low-level TCP/UDP client socket. No protocol knowledge beyond "send bytes / receive bytes /
notify state". Mirrors the Swift `io/` separation.

```
class AENetSocketClient:
    def __init__(self, ip: str, port: int, protocol_type: AENetSocketType)
    def connect(self) -> None                      # blocking; raises AESocketError on failure
    def disconnect(self) -> None                    # closes socket, stops recv + heartbeat threads
    def send(self, data: bytes) -> None            # TCP: sendall; UDP: send (connected socket)
    def start_receiving(self, on_data: Callable[[bytes], None],
                        on_closed: Callable[[], None]) -> None  # spawns recv-loop thread
    def start_heartbeat(self, interval: int, beat: Callable[[], None]) -> None  # UDP only
    @property
    def state(self) -> AESocketState
```

- **TCP:** `socket(AF_INET, SOCK_STREAM)`, `connect((ip,port))`, recv loop `recv(65536)` → `on_data`;
  `b''` → peer closed → `on_closed` → `disconnected`.
- **UDP:** `socket(AF_INET, SOCK_DGRAM)`, `connect((ip,port))` (sets default peer → `send`/`recvfrom`
  without addr), recvfrom loop → `on_data`. Heartbeat timer thread (default 15s) calls `beat`.
- State transitions via a lock; `on_state_changed` callback set by the engine.
- Threads: recv-loop (daemon) + (UDP) heartbeat (daemon). Stopped on `disconnect()`.

## 7. New module: `AENetworkEngine` (orchestrator)

### 7.1 Public API

```python
from enum import Enum
class AENetSocketType(Enum): TCP = "tcp"; UDP = "udp"
class AESocketState(Enum): DISCONNECTED, CONNECTING, CONNECTED, FAILED
class AESocketError(Exception): invalidAddress, connectionFailed, sendFailed, notConnected, encodingFailed

class AENetworkEngine:
    def __init__(self, ip: str, port: int, protocol_type: AENetSocketType = AENetSocketType.UDP,
                 heartbeat_interval: int = 15)
    async def connect(self) -> None                     # resolves CONNECTED; raises on FAILED
    async def send(self, request: AENetReq) -> AENetRsp  # await matched response; auto-sets requestId
    def send_nowait(self, request: AENetReq) -> None     # sync fire-and-forget (enqueue only)
    async def disconnect(self) -> None                  # stops transport, clears pending w/ asyncio.CancelledError
    @property
    def state(self) -> AESocketState
    on_state_changed: Callable[[AESocketState], None]        # optional callback
    on_response_received: Callable[[AENetRsp], None]         # optional; unsolicited/push responses
    on_request_received: Callable[[AENetReq], None]           # optional; peer-pushed requests
```

### 7.2 Request/response matching (asyncio bridge)

- `connect()` captures `self._loop = asyncio.get_running_loop()`.
- `_pending: dict[str, asyncio.Future]` keyed by `request.req.requestId`.
- `send(req)`:
  1. If `req.req is None` → create `AENetReqInfo`; if `requestId` missing → generate CRC32-style
     8-hex id (mirrors Swift `AENetReq.generateRequestId`).
  2. Create `Future` on `self._loop`, store in `_pending[request_id]`.
  3. Enqueue `req.to_bytes()` (wrapped as a "package" with `AEDataType.REQUEST`) to the send queue.
  4. `await future` → returns `AENetRsp`. Caller wraps `asyncio.wait_for` for timeout
     (engine does not impose a default timeout; `req.req.timeout` is the caller's concern).
- Parser thread `on_response(rsp)` → `self._loop.call_soon_threadsafe(self._resolve, rsp)`.
- `_resolve(rsp)`: match by `rsp.req.requestId`; if a Future exists → `set_result(rsp)` + pop;
  else → fire `on_response_received`.
- Parser `on_request(req)` (peer-pushed request, no pending Future) →
  `self._loop.call_soon_threadsafe(self._dispatch_request, req)` → fires `on_request_received`.

### 7.3 Serial send queue

- `queue.Queue` of packages; one sender thread processes one package at a time:
  `AEPacket.packets_from_data(REQUEST, data)` → send each packet bytes via `client.send(packet_bytes())`.
- On send error → `state=FAILED`, drain queue, reject all pending Futures with `AESocketError.sendFailed`.
- Mirrors Swift `processSendQueue` (one `AEPackageData` fully sent before the next).

### 7.4 Receive wiring (reuse parsers)

- **TCP:** recv-loop `on_data(bytes)` → `self._parser.feed(data)` where `self._parser = AEPacketParser(
  on_response_callback=self._on_response, on_request_callback=self._on_request)`.
- **UDP:** recv-loop `on_data(bytes)` → `self._udp_buffer.receive(data, peer_addr)` where
  `self._udp_buffer = AEPacketReceiveBuffer(on_packet_received=self._on_parsed_result)`;
  `_on_parsed_result` dispatches by `data_type`: RESPONSE → `_on_response(rsp)`, REQUEST → `_on_request(req)`.
- `on_closed` (TCP) → `state=DISCONNECTED` + reject pending.
- Parser thread is the reused one inside `AEPacketParser`/`AEPacketReceiveBuffer`; no new parse thread.

### 7.5 Heartbeat (UDP only)

- `client.start_heartbeat(interval, beat=self._send_heartbeat)`.
- `_send_heartbeat()` → `AEPacket.packets_from_data(HEARTBEAT, b'{}')` → enqueue to send queue
  (same serial path). On failure → `state=FAILED`, stop heartbeat. Mirrors Swift `sendHeartbeat`.

### 7.6 Lifecycle

- `connect()` → set state CONNECTING → `client.connect()` → start parsers → `client.start_receiving(...)`
  → (UDP) `client.start_heartbeat(...)` → state CONNECTED (or FAILED on exception, re-raised to caller).
- `disconnect()` → `client.disconnect()` → stop parsers → drain send queue → reject all pending
  Futures with `asyncio.CancelledError` → state DISCONNECTED.
- `__del__`/`close()` best-effort disconnect.

## 8. Data flow

```
send:    AENetReq → to_bytes → packets_from_data(REQUEST) → send-queue thread → client.send(packet)
recv TCP: recv → AEPacketParser.feed → parser thread → on_response(AENetRsp)
recv UDP: recvfrom → AEPacketReceiveBuffer.receive → parser thread → on_packet_received → on_response
bridge:  on_response → loop.call_soon_threadsafe → _resolve → Future.set_result → await send returns
heartbeat (UDP): timer → packets_from_data(HEARTBEAT,b'{}') → send-queue → client.send
```

## 9. State machine

```
DISCONNECTED → CONNECTING → CONNECTED
       ↑            ↓              ↓
       └────── FAILED ←───────────┘  (send fail / recv error / heartbeat fail / peer close→DISCONNECTED)
```
- Thread-safe via `threading.Lock`; `on_state_changed` fired on every transition.
- `AESocketError` subclasses: `invalidAddress, connectionFailed, sendFailed, notConnected, encodingFailed`.

## 10. Scope & out-of-scope

**In scope (V1):**
- TCP + UDP outbound connect/send/receive; single-shot `await send(req) -> AENetRsp`.
- Request/response matching by `req.requestId`; unsolicited `on_response_received`.
- UDP heartbeat keepalive; connection state machine; asyncio bridge.
- Tests for transport + engine (loopback echo).

**Out of scope (V1):**
- Multi-chunk streaming responses (Swift `onStreamReceived`/`onCompleted`). Needs `is_completed` on
  `AENetRsp` + an `async for` API. Documented future extension; `on_response_received` is the hook.
- Reconnection / auto-reconnect.
- TLS/encryption (Swift `AENetSecurity` TLV) — not present in the Python protocol layer today.
- Wiring into `app.py`/`AENetRouteCenter` — the engine is a standalone outbound tool.
- Cross-compatibility with the Swift wire format (different AEDataType values + different
  fragmentation seq direction). The engine speaks the **Python** AEPacket protocol.

## 11. Testing

- `Network/Socket/test_network_engine.py` (mirrors existing `test_packet.py`/`test_socket_wrapper.py` naming):
  - `AENetSocketClient`: loopback TCP echo (connect → send → recv → close detection) and UDP echo.
  - `AENetworkEngine`: `await send(req)` round-trip against a local echo server; requestId auto-gen;
    timeout via `wait_for`; heartbeat observed on UDP; `disconnect()` cancels pending Futures.
- Reuse existing `test_packet.py` coverage for packet/fragmentation round-trip (no re-test).

## 12. Acceptance criteria

1. `AENetworkEngine` connects to a local TCP and a local UDP echo peer and reaches `CONNECTED`.
2. `await engine.send(req)` returns the matched `AENetRsp` for a real round-trip (req.requestId matches).
3. Missing `requestId` is auto-generated and used for matching.
4. UDP engine sends a HEARTBEAT packet every `heartbeat_interval` seconds.
5. TCP peer-close → state `DISCONNECTED`; pending `send()` awaitables cancelled.
6. `disconnect()` stops all threads and rejects pending Futures.
7. No changes to `app.py`, `AENetRouteCenter`, `AESocketServer`, or existing packet/model code.
8. New tests pass; existing `test_packet.py` still passes.
