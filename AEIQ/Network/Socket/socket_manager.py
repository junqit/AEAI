"""
Socket 连接管理器

管理多个 Socket 连接，每个连接使用 AESocketWrapper 包装
"""

import socket
import threading
import logging
from typing import Dict, Optional
from .AESocketWrapper import AESocketWrapper
from .AESocketListener import AESocketListener
from ..Core import AENetReq, AENetRsp

logger = logging.getLogger(__name__)


class SocketConnectionManager:
    """
    Socket 连接管理器

    功能：
    1. 管理多个 AESocketWrapper 实例
    2. 为每个连接分配唯一 ID
    3. 处理连接的生命周期
    4. 广播消息到所有连接
    """

    def __init__(self):
        """初始化连接管理器"""
        self._connections: Dict[str, AESocketWrapper] = {}
        self._udp_connection_ids: Dict[tuple, str] = {}
        self._udp_server_wrapper: Optional[AESocketWrapper] = None
        self._udp_server_socket: Optional[socket.socket] = None
        self._udp_send_lock = threading.Lock()
        self._lock = threading.Lock()
        self._next_connection_id = 1

        logger.info("Socket connection manager initialized")

    def add_connection(self, sock: socket.socket, addr: tuple) -> str:
        """
        添加新的 Socket 连接（TCP）

        Args:
            sock: Socket 对象
            addr: 连接地址

        Returns:
            连接 ID
        """
        connection_id = self._generate_connection_id(addr)

        # 创建监听器
        listener = SocketConnectionListener(connection_id, self)

        # 创建包装器
        wrapper = AESocketWrapper(sock, addr)
        wrapper.add_listener(listener)

        # 保存连接
        with self._lock:
            self._connections[connection_id] = wrapper

        # 启动接收
        wrapper.start_receiving()

        logger.info(f"Connection added: {connection_id} from {addr}")
        return connection_id

    def add_udp_connection(self, sock: socket.socket, addr: tuple, data: bytes) -> str:
        """
        添加或获取 UDP 连接，并处理接收到的数据

        Args:
            sock: UDP Socket 对象
            addr: 客户端地址
            data: 接收到的数据

        Returns:
            连接 ID
        """
        with self._lock:
            connection_id = self._udp_connection_ids.get(addr)
            wrapper = self._connections.get(connection_id) if connection_id else None

            if wrapper is None:
                connection_id = self._generate_connection_id_unlocked(addr)
                listener = SocketConnectionListener(connection_id, self)
                wrapper = AESocketWrapper(sock, addr, is_udp=True)
                wrapper.add_listener(listener)
                wrapper.start_receiving()
                self._connections[connection_id] = wrapper
                self._udp_connection_ids[addr] = connection_id
                logger.info(f"UDP connection added: {connection_id} from {addr}")

            server_wrapper = self._udp_server_wrapper
            if server_wrapper is None or self._udp_server_socket is not sock:
                self._udp_server_wrapper = AESocketWrapper(sock, is_udp=True)
                self._udp_server_wrapper.start_receiving()
                self._udp_server_socket = sock
                logger.info("UDP server wrapper initialized")

            server_wrapper = self._udp_server_wrapper

        wrapper.feed_data(data)
        return connection_id

    def remove_connection(self, connection_id: str) -> None:
        """
        移除连接

        Args:
            connection_id: 连接 ID
        """
        with self._lock:
            wrapper = self._connections.pop(connection_id, None)
            udp_addr = None
            for addr, udp_connection_id in list(self._udp_connection_ids.items()):
                if udp_connection_id == connection_id:
                    udp_addr = addr
                    break
            if udp_addr is not None:
                self._udp_connection_ids.pop(udp_addr, None)

        if wrapper:
            if udp_addr is not None:
                wrapper.stop_receiving()
            else:
                wrapper.close()
            logger.info(f"Connection removed: {connection_id}")
        else:
            logger.warning(f"Connection not found: {connection_id}")

    def get_connection(self, connection_id: str) -> Optional[AESocketWrapper]:
        """
        获取连接

        Args:
            connection_id: 连接 ID

        Returns:
            AESocketWrapper 或 None
        """
        with self._lock:
            return self._connections.get(connection_id)

    def send_to_connection(self, connection_id: str, response: AENetRsp) -> bool:
        """
        发送响应到指定连接

        Args:
            connection_id: 连接 ID
            response: 响应对象

        Returns:
            是否发送成功
        """
        wrapper = self.get_connection(connection_id)
        if wrapper:
            if self._is_udp_connection(wrapper):
                return self._send_udp_response(wrapper.address, response)
            return wrapper.send_response(response)
        else:
            logger.warning(f"Cannot send to connection {connection_id}: not found")
            return False

    def broadcast(self, response: AENetRsp, exclude: Optional[str] = None) -> int:
        """
        广播消息到所有连接

        Args:
            response: 响应对象
            exclude: 排除的连接 ID（可选）

        Returns:
            成功发送的连接数
        """
        success_count = 0

        with self._lock:
            connections = list(self._connections.items())

        for conn_id, wrapper in connections:
            if conn_id != exclude:
                if self._is_udp_connection(wrapper):
                    if self._send_udp_response(wrapper.address, response):
                        success_count += 1
                elif wrapper.send_response(response):
                    success_count += 1

        logger.info(f"Broadcast to {success_count} connections")
        return success_count

    def get_connection_count(self) -> int:
        """获取当前连接数"""
        with self._lock:
            return len(self._connections)

    def get_all_connection_ids(self) -> list:
        """获取所有连接 ID"""
        with self._lock:
            return list(self._connections.keys())

    def close_all(self) -> None:
        """关闭所有连接"""
        with self._lock:
            connections = list(self._connections.values())
            server_wrapper = self._udp_server_wrapper
            self._connections.clear()
            self._udp_connection_ids.clear()
            self._udp_server_wrapper = None
            self._udp_server_socket = None

        closed_wrappers = set()
        for wrapper in connections:
            if id(wrapper) in closed_wrappers:
                continue
            try:
                wrapper.close()
                closed_wrappers.add(id(wrapper))
            except Exception as e:
                logger.error(f"Error closing connection: {e}")

        if server_wrapper and id(server_wrapper) not in closed_wrappers:
            try:
                server_wrapper.close()
            except Exception as e:
                logger.error(f"Error closing UDP server wrapper: {e}")

        logger.info("All connections closed")

    def _generate_connection_id(self, addr: tuple) -> str:
        """
        生成连接 ID

        Args:
            addr: 连接地址

        Returns:
            连接 ID
        """
        with self._lock:
            return self._generate_connection_id_unlocked(addr)

    def _generate_connection_id_unlocked(self, addr: tuple) -> str:
        conn_id = f"conn_{self._next_connection_id}_{addr[0]}_{addr[1]}"
        self._next_connection_id += 1
        return conn_id

    def _is_udp_connection(self, wrapper: AESocketWrapper) -> bool:
        return wrapper.address in self._udp_connection_ids

    def _send_udp_response(self, addr: tuple, response: AENetRsp) -> bool:
        server_wrapper = self._udp_server_wrapper
        if server_wrapper is None:
            logger.warning(f"Cannot send to UDP connection {addr}: server wrapper not initialized")
            return False

        with self._udp_send_lock:
            original_addr = server_wrapper._addr
            server_wrapper._addr = addr
            try:
                return server_wrapper.send_response(response)
            finally:
                server_wrapper._addr = original_addr

    def __len__(self) -> int:
        """返回连接数"""
        return self.get_connection_count()


class SocketConnectionListener(AESocketListener):
    """
    Socket 连接监听器

    为每个连接创建一个监听器实例，处理该连接的所有消息
    """

    def __init__(self, connection_id: str, manager: SocketConnectionManager):
        """
        初始化监听器

        Args:
            connection_id: 连接 ID
            manager: 连接管理器
        """
        self.connection_id = connection_id
        self.manager = manager

    def on_request_received(self, request: AENetReq) -> None:
        """处理接收到的请求"""
        logger.info(f"[{self.connection_id}] Request received: {request.model_dump_json(exclude_none=True, indent=2)}")

        try:
            # 根据 path 路由到不同的处理器
            response = AENetRsp.create_success(
                requestId=request.requestId,
                content=request.path,
                result={
                    "context": request.context,
                    "question": request.question,
                    "llm_types": request.llm_types,
                    "path": request.path
                }
            )
            self.manager.send_to_connection(self.connection_id, response)

        except Exception as e:
            logger.error(f"[{self.connection_id}] Error handling request: {e}")
            error_response = AENetRsp.create_error(
                requestId=request.requestId,
                error_code="ERR_PROCESSING",
                error_message=str(e)
            )
            self.manager.send_to_connection(self.connection_id, error_response)

    def on_data_received(self, response: AENetRsp) -> None:
        """
        处理接收到的响应（客户端一般不发送响应，但保留此方法）

        Args:
            response: 响应对象
        """
        logger.debug(f"[{self.connection_id}] Response received: {response.status}")

    def on_connection_closed(self) -> None:
        """连接关闭回调"""
        logger.info(f"[{self.connection_id}] Connection closed")
        # 从管理器中移除连接
        self.manager.remove_connection(self.connection_id)

    def on_error(self, error: Exception) -> None:
        """错误回调"""
        logger.error(f"[{self.connection_id}] Error: {error}")


# 全局单例
socket_manager = SocketConnectionManager()
