"""
Socket 服务器

提供 UDP Socket 服务，使用 AESocketWrapper 处理连接
"""

import socket
import threading
import logging
from Network.Socket import socket_manager

logger = logging.getLogger(__name__)


class SocketServer:
    """
    UDP Socket 服务器

    功能：
    1. 监听 UDP 端口
    2. 接收客户端数据包
    3. 为每个客户端地址创建 AESocketWrapper
    4. 通过 SocketConnectionManager 管理所有连接
    """

    def __init__(self, host: str = '0.0.0.0', port: int = 8888):
        """
        初始化服务器

        Args:
            host: 监听地址
            port: 监听端口
        """
        self.host = host
        self.port = port
        self.server_socket: socket.socket = None
        self.receive_thread: threading.Thread = None
        self.running = False

        logger.info(f"UDP Socket server initialized on {host}:{port}")

    def start(self) -> None:
        """启动服务器"""
        if self.running:
            logger.warning("Server is already running")
            return

        try:
            # 创建 UDP 服务器 socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))

            self.running = True

            # 启动接收数据的线程
            self.receive_thread = threading.Thread(
                target=self._receive_loop,
                daemon=True,
                name="UDPSocketServerReceive"
            )
            self.receive_thread.start()

            logger.info(f"UDP Socket server started on {self.host}:{self.port}")

        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            raise

    def stop(self) -> None:
        """停止服务器"""
        logger.info("Stopping UDP socket server")
        self.running = False

        # 关闭所有连接
        socket_manager.close_all()

        # 关闭服务器 socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception as e:
                logger.error(f"Error closing server socket: {e}")

        # 等待接收线程结束
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=2.0)

        logger.info("UDP Socket server stopped")

    def _receive_loop(self) -> None:
        """接收数据的循环"""
        logger.info("UDP receive loop started")

        while self.running:
            try:
                # 接收数据和客户端地址
                data, client_addr = self.server_socket.recvfrom(65535)
                logger.debug(f"Received {len(data)} bytes from {client_addr}")

                # 为该客户端地址创建或获取连接
                connection_id = socket_manager.add_udp_connection(
                    self.server_socket,
                    client_addr,
                    data
                )

                logger.debug(f"Data from {connection_id}, total connections: {len(socket_manager)}")

            except OSError as e:
                if self.running:
                    logger.error(f"Error receiving data: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error in receive loop: {e}")
                if not self.running:
                    break

        logger.info("UDP receive loop ended")

    @property
    def is_running(self) -> bool:
        """检查服务器是否运行"""
        return self.running

    @property
    def connection_count(self) -> int:
        """获取当前连接数"""
        return socket_manager.get_connection_count()


# 全局服务器实例
_server_instance: SocketServer = None


def get_socket_server(host: str = '0.0.0.0', port: int = 8888) -> SocketServer:
    """
    获取 Socket 服务器单例

    Args:
        host: 监听地址
        port: 监听端口

    Returns:
        SocketServer 实例
    """
    global _server_instance

    if _server_instance is None:
        _server_instance = SocketServer(host, port)

    return _server_instance


def start_socket_server(host: str = '0.0.0.0', port: int = 8888) -> SocketServer:
    """
    启动 Socket 服务器

    Args:
        host: 监听地址
        port: 监听端口

    Returns:
        SocketServer 实例
    """
    server = get_socket_server(host, port)
    if not server.is_running:
        server.start()
    return server


def stop_socket_server() -> None:
    """停止 Socket 服务器"""
    global _server_instance

    if _server_instance:
        _server_instance.stop()
