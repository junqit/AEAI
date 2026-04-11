"""
消息处理器 - 将 UDP 消息与 FastAPI 应用集成
"""
from typing import Dict, Any, Optional
from datetime import datetime
import logging


class MessageHandler:
    def __init__(self, context_manager=None):
        """
        初始化消息处理器

        Args:
            context_manager: Context 管理器实例，用于处理上下文相关的请求
        """
        self.context_manager = context_manager
        self.logger = logging.getLogger(__name__)

    def handle(self, data: Dict[Any, Any], addr: tuple) -> Optional[Dict]:
        """
        处理收到的 UDP 消息

        Args:
            data: 接收到的 JSON 数据
            addr: 客户端地址 (host, port)

        Returns:
            响应数据字典，会被自动发送回客户端
        """
        try:
            # 获取消息类型
            msg_type = data.get("type", "unknown")

            self.logger.info(f"处理消息类型: {msg_type} 来自 {addr}")

            # 根据消息类型分发处理
            if msg_type == "ping":
                return self._handle_ping(data)
            elif msg_type == "chat":
                return self._handle_chat(data)
            elif msg_type == "context":
                return self._handle_context(data)
            elif msg_type == "custom":
                return self._handle_custom(data)
            else:
                return {
                    "status": "error",
                    "message": f"Unknown message type: {msg_type}",
                    "timestamp": datetime.now().isoformat()
                }

        except Exception as e:
            self.logger.error(f"处理消息时出错: {e}")
            return {
                "status": "error",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def _handle_ping(self, data: Dict) -> Dict:
        """处理 ping 请求"""
        return {
            "status": "success",
            "type": "pong",
            "message": "Server is alive",
            "timestamp": datetime.now().isoformat(),
            "echo": data
        }

    def _handle_chat(self, data: Dict) -> Dict:
        """
        处理聊天请求

        数据格式示例:
        {
            "type": "chat",
            "message": "Hello",
            "context_id": "user_123"
        }
        """
        message = data.get("message", "")
        context_id = data.get("context_id")

        if not message:
            return {
                "status": "error",
                "message": "Message content is required",
                "timestamp": datetime.now().isoformat()
            }

        # TODO: 这里可以与 Context Manager 集成，处理聊天逻辑
        # 示例响应
        return {
            "status": "success",
            "type": "chat_response",
            "message": f"Received: {message}",
            "context_id": context_id,
            "timestamp": datetime.now().isoformat()
        }

    def _handle_context(self, data: Dict) -> Dict:
        """
        处理上下文相关请求

        数据格式示例:
        {
            "type": "context",
            "action": "get" | "create" | "delete",
            "context_id": "user_123",
            "data": {...}
        }
        """
        action = data.get("action")
        context_id = data.get("context_id")

        if not action:
            return {
                "status": "error",
                "message": "Action is required",
                "timestamp": datetime.now().isoformat()
            }

        # TODO: 集成 Context Manager
        if self.context_manager:
            # 根据 action 调用相应的 context_manager 方法
            pass

        return {
            "status": "success",
            "type": "context_response",
            "action": action,
            "context_id": context_id,
            "timestamp": datetime.now().isoformat()
        }

    def _handle_custom(self, data: Dict) -> Dict:
        """
        处理自定义消息

        数据格式由业务层定义
        """
        return {
            "status": "success",
            "type": "custom_response",
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
