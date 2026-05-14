"""
Socket 连接管理器

管理多个 Socket 连接，每个连接使用 AESocketWrapper 包装
"""

import socket
import threading
import logging
from typing import Dict, Optional, TYPE_CHECKING
from .AESocketWrapper import AESocketWrapper
from .AESocketListener import AESocketListener
from ..Core import AENetReq, AENetRsp

if TYPE_CHECKING:
    from .IRequestHandler import IRequestHandler

logger = logging.getLogger(__name__)


class SocketConnectionManager:
    """
    Socket 连接管理器（网络层）

    职责：
    1. 管理多个 Socket 连接
    2. 为每个连接分配唯一 ID
    3. 接收网络请求并分发给业务层
    4. 发送响应到指定连接
    """

    def __init__(self):
        """初始化连接管理器"""
        self._connections: Dict[str, AESocketWrapper] = {}
        self._lock = threading.Lock()

        # 请求处理器（业务层）
        self._request_handler: Optional['IRequestHandler'] = None

        logger.info("Socket connection manager initialized")

    def set_request_handler(self, handler: 'IRequestHandler') -> None:
        """
        注册请求处理器（业务层）

        Args:
            handler: 实现 IRequestHandler 接口的处理器
        """
        self._request_handler = handler
        logger.info(f"Request handler registered: {handler.__class__.__name__}")

    def send_response(self, connection_id: str, response: AENetRsp) -> bool:
        """
        发送响应到指定连接（实现 IResponseSender 接口）

        Args:
            connection_id: 连接ID
            response: 响应对象

        Returns:
            是否发送成功
        """
        return self.send_to_connection(connection_id, response)

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
            connection_id, wrapper = self._find_connection_by_addr_unlocked(addr)

            if wrapper is None:
                connection_id = self._generate_connection_id_unlocked(addr)
                listener = SocketConnectionListener(connection_id, self)
                wrapper = AESocketWrapper(sock, addr, is_udp=True)
                wrapper.add_listener(listener)
                wrapper.start_receiving()
                self._connections[connection_id] = wrapper
                logger.info(f"UDP connection added: {connection_id} from {addr}")

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

        if wrapper:
            if wrapper.is_udp:
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
                if wrapper.send_response(response):
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
            self._connections.clear()

        for wrapper in connections:
            try:
                wrapper.close()
            except Exception as e:
                logger.error(f"Error closing connection: {e}")

        logger.info("All connections closed")

    def _generate_connection_id(self, addr: tuple) -> str:
        with self._lock:
            return self._generate_connection_id_unlocked(addr)

    def _generate_connection_id_unlocked(self, addr: tuple) -> str:
        return f"conn_{addr[0]}_{addr[1]}"

    def _find_connection_by_addr_unlocked(self, addr: tuple) -> tuple:
        for conn_id, wrapper in self._connections.items():
            if wrapper.address == addr:
                return conn_id, wrapper
        return None, None

    def __len__(self) -> int:
        """返回连接数"""
        return self.get_connection_count()


class SocketConnectionListener(AESocketListener):
    """
    Socket 连接监听器（网络层内部）

    为每个连接创建一个监听器实例，接收数据后转发给业务层处理器
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
        """
        处理接收到的请求

        Args:
            request: 请求对象
        """
        logger.info(f"[{self.connection_id}] Request received: {request.model_dump_json(exclude_none=True, indent=2)}")

        # 转发给业务层处理器
        if self.manager._request_handler:
            try:
                self.manager._request_handler.handle_request(request, self.connection_id)
            except Exception as e:
                logger.error(f"[{self.connection_id}] Error in request handler: {e}", exc_info=True)
                # 发送错误响应
                error_response = AENetRsp.create_error(
                    requestId=request.requestId,
                    error_code="ERR_HANDLER",
                    error_message=f"Request handler error: {str(e)}"
                )
                self.manager.send_to_connection(self.connection_id, error_response)
        else:
            logger.warning(f"[{self.connection_id}] No request handler registered, request ignored")
            # 发送错误响应
            error_response = AENetRsp.create_error(
                requestId=request.requestId,
                error_code="ERR_NO_HANDLER",
                error_message="No request handler registered"
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
