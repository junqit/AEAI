from typing import Dict, Optional, TYPE_CHECKING
from datetime import datetime, timedelta
import asyncio
import logging
import sys
import os

# 添加父目录到路径以导入配置
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from AEIQConfig import config
from .AEContext import AEContext
from Network.Core import AENetReq, AENetRsp

if TYPE_CHECKING:
    from Network.Socket.IResponseSender import IResponseSender

logger = logging.getLogger(__name__)


class AEContextManager:
    """
    Context 管理器（业务层）

    职责：
    1. 管理多个 AEContext 实例
    2. 实现 IRequestHandler 接口，处理来自网络层的请求
    3. 通过 IResponseSender 接口发送响应到网络层
    """

    def __init__(self, response_sender: Optional['IResponseSender'] = None):
        """
        初始化 Context 管理器

        Args:
            response_sender: 响应发送器（网络层实现的接口）
        """
        self.contexts: Dict[str, AEContext] = {}
        self.session_timeout = config.get_session_timeout()
        self._lock = asyncio.Lock()

        # 响应发送器（网络层）
        self._response_sender = response_sender

        logger.info("AEContextManager initialized")

    def set_response_sender(self, sender: 'IResponseSender') -> None:
        """
        设置响应发送器（依赖注入）

        Args:
            sender: 实现 IResponseSender 接口的发送器
        """
        self._response_sender = sender
        logger.info(f"Response sender set: {sender.__class__.__name__}")

    def handle_request(self, request: AENetReq, connection_id: str) -> None:
        """
        处理网络请求（实现 IRequestHandler 接口）

        Args:
            request: 请求对象
            connection_id: 连接ID
        """
        logger.info(f"Handling request from connection {connection_id}: path={request.path}")

        try:
            # 根据 path 路由到不同的处理方法
            if request.path == "/ae/context/chat":
                self._handle_chat(request, connection_id)
            elif request.path == "/ae/context/cancel":
                self._handle_cancel(request, connection_id)
            elif request.path == "/ae/context/create":
                self._handle_create(request, connection_id)
            else:
                self._send_error(
                    connection_id,
                    request.requestId,
                    "ERR_UNKNOWN_PATH",
                    f"Unknown path: {request.path}"
                )

        except Exception as e:
            logger.error(f"Error handling request: {e}", exc_info=True)
            self._send_error(
                connection_id,
                request.requestId,
                "ERR_INTERNAL",
                str(e)
            )

    def _handle_chat(self, request: AENetReq, connection_id: str) -> None:
        """处理聊天请求"""
        # TODO: 实现实际的 AI 聊天逻辑
        # 1. 从 request.context 获取 context_id
        # 2. 获取或创建 AEContext
        # 3. 调用 AI 进行处理
        # 4. 发送响应

        response = AENetRsp.create_success(
            requestId=request.requestId,
            content="Chat response placeholder",
            result={
                "message": "This is a placeholder for AI chat response",
                "context_id": request.context.get("id") if request.context else None
            }
        )
        self._send_response(connection_id, response)

    def _handle_cancel(self, request: AENetReq, connection_id: str) -> None:
        """处理取消请求"""
        # TODO: 实现取消逻辑
        response = AENetRsp.create_success(
            requestId=request.requestId,
            content="Cancel request received",
            result={"status": "cancelled"}
        )
        self._send_response(connection_id, response)

    def _handle_create(self, request: AENetReq, connection_id: str) -> None:
        """处理创建 Context 请求"""
        # TODO: 实现创建 Context 逻辑
        response = AENetRsp.create_success(
            requestId=request.requestId,
            content="Context created",
            result={"context_id": "ctx_new_placeholder"}
        )
        self._send_response(connection_id, response)

    def _send_response(self, connection_id: str, response: AENetRsp) -> None:
        """发送响应到网络层"""
        if self._response_sender:
            success = self._response_sender.send_response(connection_id, response)
            if not success:
                logger.error(f"Failed to send response to connection {connection_id}")
        else:
            logger.error("No response sender available")

    def _send_error(self, connection_id: str, request_id: Optional[str],
                   error_code: str, error_message: str) -> None:
        """发送错误响应"""
        response = AENetRsp.create_error(
            requestId=request_id,
            error_code=error_code,
            error_message=error_message
        )
        self._send_response(connection_id, response)

    async def create_context(self, aedir: Optional[str] = None) -> AEContext:
        """
        创建新的 Context 实例（自动生成 session_id）

        Args:
            aedir: Context 对应的目录路径（可选）

        Returns:
            新创建的 AEContext 实例
        """
        async with self._lock:
            # 创建 Context（内部自动生成 session_id）
            context = AEContext(aedir=aedir)

            # 将 Context 添加到管理器
            self.contexts[context.session_id] = context

            return context

    async def get_or_create_context(self, session_id: str, aedir: Optional[str] = None) -> AEContext:
        """
        获取或创建 Context 实例（兼容旧接口，使用指定的 session_id）

        Args:
            session_id: 会话 ID
            aedir: Context 对应的目录路径（可选）

        Returns:
            AEContext 实例
        """
        async with self._lock:
            if session_id not in self.contexts:
                # 创建新 Context
                context = AEContext(aedir=aedir)
                # 覆盖自动生成的 session_id，使用指定的 session_id（兼容旧代码）
                context.session_id = session_id
                self.contexts[session_id] = context
            else:
                # 更新访问时间
                self.contexts[session_id].updated_at = datetime.now()
                # 如果提供了新的 aedir，更新它
                if aedir is not None:
                    self.contexts[session_id].aedir = aedir

            return self.contexts[session_id]

    async def get_context(self, session_id: str) -> Optional[AEContext]:
        """
        获取 Context 实例

        Args:
            session_id: 会话 ID

        Returns:
            AEContext 实例，如果不存在则返回 None
        """
        async with self._lock:
            return self.contexts.get(session_id)

    async def delete_context(self, session_id: str) -> bool:
        """
        删除 Context 实例

        Args:
            session_id: 会话 ID

        Returns:
            是否成功删除
        """
        async with self._lock:
            if session_id in self.contexts:
                context = self.contexts[session_id]
                context.cleanup()
                del self.contexts[session_id]
                return True
            return False

    async def cleanup_expired_contexts(self):
        """清理过期的 Context"""
        async with self._lock:
            now = datetime.now()
            expired_sessions = []

            for session_id, context in self.contexts.items():
                if (now - context.updated_at).total_seconds() > self.session_timeout:
                    expired_sessions.append(session_id)

            for session_id in expired_sessions:
                context = self.contexts[session_id]
                context.cleanup()
                del self.contexts[session_id]

            return len(expired_sessions)

    async def get_all_contexts_stats(self) -> Dict[str, dict]:
        """
        获取所有 Context 的统计信息

        Returns:
            所有会话的统计信息字典
        """
        async with self._lock:
            stats = {}
            for session_id, context in self.contexts.items():
                stats[session_id] = context.get_stats()
            return stats

    async def get_active_sessions_count(self) -> int:
        """获取活跃会话数量"""
        async with self._lock:
            return len(self.contexts)

    def cleanup_all(self):
        """清理所有 Context"""
        for context in self.contexts.values():
            context.cleanup()
        self.contexts.clear()
