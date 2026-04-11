"""
UDP Socket 服务器
接收 JSON 格式数据并提供消息处理回调
"""
import socket
import json
import threading
import logging
from typing import Callable, Optional, Dict, Any
from datetime import datetime


class UDPServer:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9999,
        buffer_size: int = 4096
    ):
        """
        初始化 UDP 服务器

        Args:
            host: 绑定的主机地址，默认 0.0.0.0 监听所有网络接口
            port: 绑定的端口号
            buffer_size: 接收缓冲区大小（字节）
        """
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.socket: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.message_handler: Optional[Callable] = None

        # 配置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def set_message_handler(self, handler: Callable[[Dict[Any, Any], tuple], Optional[Dict]]):
        """
        设置消息处理回调函数

        Args:
            handler: 回调函数，接收参数 (data: dict, addr: tuple)
                    返回 dict 类型的响应数据（可选），会自动发送回客户端
        """
        self.message_handler = handler

    def start(self):
        """启动 UDP 服务器"""
        if self.running:
            self.logger.warning("UDP 服务器已经在运行中")
            return

        try:
            # 创建 UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # 绑定地址和端口
            self.socket.bind((self.host, self.port))
            self.running = True

            self.logger.info(f"UDP 服务器启动成功: {self.host}:{self.port}")

            # 在新线程中运行服务器
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

        except Exception as e:
            self.logger.error(f"UDP 服务器启动失败: {e}")
            raise

    def _run(self):
        """服务器主循环"""
        while self.running:
            try:
                # 接收数据
                data, addr = self.socket.recvfrom(self.buffer_size)

                # 在新线程中处理消息，避免阻塞接收
                threading.Thread(
                    target=self._handle_message,
                    args=(data, addr),
                    daemon=True
                ).start()

            except Exception as e:
                if self.running:
                    self.logger.error(f"接收数据时发生错误: {e}")

    def _handle_message(self, raw_data: bytes, addr: tuple):
        """
        处理接收到的消息

        Args:
            raw_data: 原始字节数据
            addr: 客户端地址 (host, port)
        """
        try:
            # 解码并解析 JSON
            message_str = raw_data.decode('utf-8')
            data = json.loads(message_str)

            self.logger.info(f"收到来自 {addr} 的消息: {data}")

            # 调用消息处理器
            response = None
            if self.message_handler:
                response = self.message_handler(data, addr)

            # 如果有响应数据，发送回客户端
            if response is not None:
                self.send_response(response, addr)

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON 解析失败: {e}")
            error_response = {
                "status": "error",
                "message": "Invalid JSON format",
                "timestamp": datetime.now().isoformat()
            }
            self.send_response(error_response, addr)

        except Exception as e:
            self.logger.error(f"处理消息时发生错误: {e}")
            error_response = {
                "status": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }
            self.send_response(error_response, addr)

    def send_response(self, data: Dict, addr: tuple):
        """
        发送响应数据给客户端

        Args:
            data: 要发送的字典数据
            addr: 客户端地址 (host, port)
        """
        try:
            response_json = json.dumps(data, ensure_ascii=False)
            response_bytes = response_json.encode('utf-8')
            self.socket.sendto(response_bytes, addr)
            self.logger.info(f"已发送响应到 {addr}: {data}")
        except Exception as e:
            self.logger.error(f"发送响应失败: {e}")

    def stop(self):
        """停止 UDP 服务器"""
        if not self.running:
            self.logger.warning("UDP 服务器未运行")
            return

        self.logger.info("正在停止 UDP 服务器...")
        self.running = False

        if self.socket:
            self.socket.close()

        if self.thread:
            self.thread.join(timeout=2)

        self.logger.info("UDP 服务器已停止")

    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.stop()
