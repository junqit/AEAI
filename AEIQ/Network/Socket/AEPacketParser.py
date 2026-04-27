"""
数据包解析器

职责：
1. 管理接收缓冲区
2. 在独立线程中解析数据包
3. 通过回调通知已解析的数据
"""

import threading
import logging
from typing import Callable, Optional
from .AEReceiveBuffer import AEReceiveBuffer
from .AEPacket import AEPacket, AEDataType
from ..Core import AENetReq, AENetRsp

logger = logging.getLogger(__name__)


class AEPacketParser:
    """
    数据包解析器

    功能：
    1. 接收原始字节数据
    2. 缓存到接收缓冲区
    3. 在独立线程中解析完整数据包
    4. 根据类型解析为 AENetReq 或 AENetRsp
    5. 通过回调通知业务层

    使用示例：
        # 创建解析器
        def on_request(request: AENetReq):
            print(f"收到请求: {request.action}")

        def on_response(response: AENetRsp):
            print(f"收到响应: {response.status}")

        parser = AEPacketParser(
            on_request_callback=on_request,
            on_response_callback=on_response
        )

        # 启动解析线程
        parser.start()

        # 接收到数据后喂给解析器
        parser.feed(data_chunk)

        # 关闭
        parser.stop()
    """

    def __init__(self,
                 on_request_callback: Optional[Callable[[AENetReq], None]] = None,
                 on_response_callback: Optional[Callable[[AENetRsp], None]] = None,
                 on_error_callback: Optional[Callable[[Exception], None]] = None,
                 buffer_size: int = 10 * 1024 * 1024):
        """
        初始化解析器

        Args:
            on_request_callback: 收到请求时的回调
            on_response_callback: 收到响应时的回调
            on_error_callback: 发生错误时的回调
            buffer_size: 缓冲区大小（默认10MB）
        """
        # 接收缓冲区
        self._buffer = AEReceiveBuffer(max_buffer_size=buffer_size)
        self._buffer_lock = threading.Lock()

        # 解析线程
        self._parse_thread: Optional[threading.Thread] = None
        self._running = False

        # 信号量：通知有新数据
        self._data_available = threading.Event()

        # 回调函数
        self._on_request_callback = on_request_callback
        self._on_response_callback = on_response_callback
        self._on_error_callback = on_error_callback

        logger.info("Packet parser created")

    def start(self) -> None:
        """
        启动解析线程
        """
        if self._running:
            logger.warning("Parser thread is already running")
            return

        self._running = True
        self._parse_thread = threading.Thread(
            target=self._parse_loop,
            daemon=True,
            name="PacketParser"
        )
        self._parse_thread.start()
        logger.info("Parser thread started")

    def stop(self) -> None:
        """
        停止解析线程
        """
        logger.info("Stopping parser thread")
        self._running = False

        # 通知线程退出
        self._data_available.set()

        # 等待线程结束
        if self._parse_thread and self._parse_thread.is_alive():
            self._parse_thread.join(timeout=2.0)

        # 清空缓冲区
        with self._buffer_lock:
            self._buffer.clear()

        logger.info("Parser thread stopped")

    def feed(self, data: bytes) -> None:
        """
        喂入数据到解析器

        Args:
            data: 接收到的原始字节数据

        此方法应该在接收线程中调用，将数据追加到缓冲区
        """
        if not self._running:
            logger.warning("Parser is not running, data discarded")
            return

        try:
            # 追加到缓冲区（加锁保护）
            with self._buffer_lock:
                self._buffer.append(data)

            logger.debug(f"Fed {len(data)} bytes to parser, buffer size: {self._buffer.size}")

            # 通知解析线程
            self._data_available.set()

        except OverflowError as e:
            logger.error(f"Buffer overflow: {e}")
            # 清空缓冲区
            with self._buffer_lock:
                self._buffer.clear()
            self._notify_error(e)

        except Exception as e:
            logger.error(f"Error feeding data: {e}")
            self._notify_error(e)

    def _parse_loop(self) -> None:
        """
        解析线程的主循环

        工作流程：
        1. 等待数据可用信号
        2. 从缓冲区解析完整数据包
        3. 根据数据类型反序列化
        4. 通过回调通知业务层
        """
        try:
            while self._running:
                # 等待数据可用信号（最多等待1秒）
                if not self._data_available.wait(timeout=1.0):
                    continue

                # 清除信号
                self._data_available.clear()

                # 循环解析缓冲区中的所有完整数据包
                while self._running:
                    try:
                        # 从缓冲区解析数据包（加锁保护）
                        with self._buffer_lock:
                            packet = self._buffer.try_parse_packet()

                        if packet is None:
                            # 没有完整的数据包，等待更多数据
                            break

                        logger.debug(f"Packet parsed: type=0x{packet.header.data_type:04X}, size={packet.header.length}")

                        # 根据数据类型处理（不持锁，避免阻塞接收）
                        self._handle_packet(packet)

                    except ValueError as e:
                        logger.error(f"Failed to parse packet: {e}")
                        self._notify_error(e)
                        # 继续尝试解析下一个包
                        continue

                    except Exception as e:
                        logger.error(f"Error handling packet: {e}")
                        self._notify_error(e)
                        # 非致命错误，继续处理
                        continue

        except Exception as e:
            logger.error(f"Error in parse loop: {e}")
            self._notify_error(e)

        finally:
            logger.info("Parse loop ended")

    def _handle_packet(self, packet: AEPacket) -> None:
        """
        处理已解析的数据包

        Args:
            packet: 完整的数据包
        """
        data_type = packet.header.data_type

        try:
            # 根据数据类型解析数据
            if data_type == AEDataType.REQUEST.value:
                # 解析为请求
                request = AENetReq.from_bytes(packet.data)
                logger.debug(f"Parsed as REQUEST: action={request.action}")
                self._notify_request(request)

            elif data_type == AEDataType.RESPONSE.value:
                # 解析为响应
                response = AENetRsp.from_bytes(packet.data)
                logger.debug(f"Parsed as RESPONSE: status={response.status}")
                self._notify_response(response)

            elif data_type == AEDataType.HEARTBEAT.value:
                # 心跳包
                logger.debug("Received HEARTBEAT")
                # 心跳包可以不做处理，或者通过特殊回调通知

            elif data_type == AEDataType.PING.value:
                logger.debug("Received PING")
                # Ping 包可能需要自动回复 Pong
                # 但这是 Socket 层的职责，解析器只负责通知

            elif data_type == AEDataType.PONG.value:
                logger.debug("Received PONG")

            else:
                logger.warning(f"Unknown data type: 0x{data_type:04X}")

        except Exception as e:
            logger.error(f"Error parsing packet data: {e}")
            self._notify_error(e)

    def _notify_request(self, request: AENetReq) -> None:
        """通知请求回调"""
        if self._on_request_callback:
            try:
                self._on_request_callback(request)
            except Exception as e:
                logger.error(f"Error in request callback: {e}")

    def _notify_response(self, response: AENetRsp) -> None:
        """通知响应回调"""
        if self._on_response_callback:
            try:
                self._on_response_callback(response)
            except Exception as e:
                logger.error(f"Error in response callback: {e}")

    def _notify_error(self, error: Exception) -> None:
        """通知错误回调"""
        if self._on_error_callback:
            try:
                self._on_error_callback(error)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")

    @property
    def is_running(self) -> bool:
        """检查解析器是否正在运行"""
        return self._running

    @property
    def buffer_size(self) -> int:
        """获取当前缓冲区大小"""
        with self._buffer_lock:
            return self._buffer.size

    def __enter__(self):
        """支持 with 语句"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 语句"""
        self.stop()
        return False
