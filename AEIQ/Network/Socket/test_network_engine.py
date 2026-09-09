"""
AENetworkEngine 出站客户端引擎单元测试

用本地 TCP/UDP AEPacket 回显对端验证：
- connect -> CONNECTED
- await send(req) -> 匹配的 AENetRsp（requestId 自动生成 + 回显匹配）
- UDP 心跳保活
- disconnect 取消 pending（CancelledError）
- TCP 对端关闭 -> DISCONNECTED + pending 取消
"""

import unittest
import socket
import threading
import asyncio
import time
from typing import Optional

from AEIQ.Network.AENetworkEngine import AENetworkEngine
from AEIQ.Network.Socket.Connection.AENetSocketClient import (
    AENetSocketType, AESocketState, AESocketError,
)
from AEIQ.Network.Socket import (
    AEPacket, AEPacketHeader, AEDataType,
    AEPacketReceiveBuffer, AEPacketParser,
)
from AEIQ.Network.Core.AENetReq import AENetReq, AENetReqInfo
from AEIQ.Network.Core.AENetRsp import AENetRsp


RECV_BUF = 65536


def _echo_response_for(request: AENetReq) -> AENetRsp:
    """根据请求的 requestId / path 构造回显响应。"""
    rid = request.req.requestId if request.req else None
    path = request.req.path if request.req else None
    return AENetRsp(code=200, req=AENetReqInfo(requestId=rid, path=path), rsp={"echo": True})


class UDPEchoPeer:
    """UDP 回显对端：解析 AEPacket 请求，回显带相同 requestId 的响应；并统计心跳包。"""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.heartbeats = 0
        self._running = True
        self._buffer = AEPacketReceiveBuffer(on_packet_received=self._on_packet)
        self._buffer.start()
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

    def _recv_loop(self):
        while self._running:
            try:
                data, addr = self.sock.recvfrom(RECV_BUF)
            except OSError:
                return
            # 在喂入解析器前统计心跳包（解析器对心跳包不上回调）
            if len(data) >= AEPacketHeader.HEADER_SIZE:
                try:
                    hdr = AEPacketHeader.from_bytes(data[:AEPacketHeader.HEADER_SIZE])
                    if hdr.data_type_value == AEDataType.HEARTBEAT.value:
                        self.heartbeats += 1
                except Exception:
                    pass
            self._buffer.receive(data, addr)

    def _on_packet(self, result):
        if isinstance(result.payload, AENetReq):
            rsp = _echo_response_for(result.payload)
            for pkt in AEPacket.packets_from_data(AEDataType.DATA, rsp.to_bytes()):
                try:
                    self.sock.sendto(pkt.to_bytes(), result.client_addr)
                except OSError:
                    return

    def stop(self):
        self._running = False
        self._buffer.stop()
        try:
            self.sock.close()
        except Exception:
            pass


class UDPDiscardPeer:
    """UDP 黑洞对端：收包不响应（用于 pending 取消测试）。"""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self._running = True
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

    def _recv_loop(self):
        while self._running:
            try:
                self.sock.recvfrom(RECV_BUF)
            except OSError:
                return

    def stop(self):
        self._running = False
        try:
            self.sock.close()
        except Exception:
            pass


class TCPEchoPeer:
    """TCP 回显对端：接收 AEPacket 流，回显带相同 requestId 的响应。"""

    def __init__(self):
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.conn: Optional[socket.socket] = None
        self._running = True
        self._parser: Optional[AEPacketParser] = None
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self):
        try:
            self.conn, _ = self.srv.accept()
        except OSError:
            return
        self._parser = AEPacketParser(
            on_request_callback=self._on_request,
            on_response_callback=lambda r: None,
            on_error_callback=lambda e: None,
        )
        self._parser.start()
        while self._running and self.conn is not None:
            try:
                data = self.conn.recv(RECV_BUF)
            except OSError:
                return
            if not data:
                return
            self._parser.feed(data)

    def _on_request(self, request: AENetReq):
        rsp = _echo_response_for(request)
        for pkt in AEPacket.packets_from_data(AEDataType.DATA, rsp.to_bytes()):
            try:
                self.conn.sendall(pkt.to_bytes())
            except OSError:
                return

    def stop(self):
        self._running = False
        if self._parser is not None:
            self._parser.stop()
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
        try:
            self.srv.close()
        except Exception:
            pass


class TCPDiscardPeer:
    """TCP 黑洞对端：accept 后收包不响应（用于对端关闭测试）。"""

    def __init__(self):
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.conn: Optional[socket.socket] = None
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self.conn, _ = self.srv.accept()
        except OSError:
            return
        while self._running:
            try:
                data = self.conn.recv(RECV_BUF)
            except OSError:
                return
            if not data:
                return

    def stop(self):
        self._running = False
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
        try:
            self.srv.close()
        except Exception:
            pass


class TestAENetworkEngineUDP(unittest.IsolatedAsyncioTestCase):

    async def test_send_recv_roundtrip(self):
        peer = UDPEchoPeer()
        engine = AENetworkEngine("127.0.0.1", peer.port, AENetSocketType.UDP, heartbeat_interval=999)
        try:
            await engine.connect()
            self.assertEqual(engine.state, AESocketState.CONNECTED)

            req = AENetReq()  # 无 requestId
            rsp = await asyncio.wait_for(engine.send(req), timeout=5.0)

            self.assertEqual(rsp.code, 200)
            self.assertIsNotNone(req.req)
            self.assertIsNotNone(req.req.requestId)  # 自动生成
            self.assertEqual(rsp.req.requestId, req.req.requestId)  # 回显匹配
        finally:
            await engine.disconnect()
            peer.stop()

    async def test_request_id_preserved(self):
        peer = UDPEchoPeer()
        engine = AENetworkEngine("127.0.0.1", peer.port, AENetSocketType.UDP, heartbeat_interval=999)
        try:
            await engine.connect()
            req = AENetReq(req=AENetReqInfo(requestId="deadbeef", path="/context/info"))
            rsp = await asyncio.wait_for(engine.send(req), timeout=5.0)
            self.assertEqual(rsp.req.requestId, "deadbeef")
            self.assertEqual(rsp.req.path, "/context/info")
        finally:
            await engine.disconnect()
            peer.stop()

    async def test_udp_heartbeat(self):
        peer = UDPEchoPeer()
        engine = AENetworkEngine("127.0.0.1", peer.port, AENetSocketType.UDP, heartbeat_interval=0.3)
        try:
            await engine.connect()
            await asyncio.sleep(1.0)  # 等待至少一次心跳
            self.assertGreaterEqual(peer.heartbeats, 1)
        finally:
            await engine.disconnect()
            peer.stop()

    async def test_disconnect_cancels_pending(self):
        peer = UDPDiscardPeer()
        engine = AENetworkEngine("127.0.0.1", peer.port, AENetSocketType.UDP, heartbeat_interval=999)
        try:
            await engine.connect()
            req = AENetReq()
            task = asyncio.ensure_future(engine.send(req))
            await asyncio.sleep(0.3)  # 让发送入队并等待
            await engine.disconnect()
            with self.assertRaises(asyncio.CancelledError):
                await task
        finally:
            peer.stop()

    async def test_send_when_not_connected_raises(self):
        engine = AENetworkEngine("127.0.0.1", 1, AENetSocketType.UDP)
        with self.assertRaises(AESocketError):
            await engine.send(AENetReq())


class TestAENetworkEngineTCP(unittest.IsolatedAsyncioTestCase):

    async def test_send_recv_roundtrip(self):
        peer = TCPEchoPeer()
        engine = AENetworkEngine("127.0.0.1", peer.port, AENetSocketType.TCP)
        try:
            await engine.connect()
            self.assertEqual(engine.state, AESocketState.CONNECTED)

            req = AENetReq()
            rsp = await asyncio.wait_for(engine.send(req), timeout=5.0)

            self.assertEqual(rsp.code, 200)
            self.assertIsNotNone(req.req.requestId)
            self.assertEqual(rsp.req.requestId, req.req.requestId)
        finally:
            await engine.disconnect()
            peer.stop()

    async def test_peer_close_disconnects_and_cancels(self):
        peer = TCPDiscardPeer()
        engine = AENetworkEngine("127.0.0.1", peer.port, AENetSocketType.TCP)
        try:
            await engine.connect()
            req = AENetReq()
            task = asyncio.ensure_future(engine.send(req))
            await asyncio.sleep(0.3)  # 请求已发出，对端不回，pending 挂起

            peer.stop()  # 关闭对端 -> 引擎 recv b'' -> DISCONNECTED + 取消 pending
            await asyncio.sleep(0.5)

            self.assertEqual(engine.state, AESocketState.DISCONNECTED)
            with self.assertRaises(asyncio.CancelledError):
                await task
        finally:
            try:
                await engine.disconnect()
            except Exception:
                pass
            peer.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
