from typing import Dict, Optional
from datetime import datetime, timedelta
import asyncio
import sys
import os

# 添加父目录到路径以导入配置
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from AEIQConfig import config
from .AEContext import AEContext


class AEContextManager:
    """管理多个 AEContext 实例的管理器"""

    def __init__(self):
        """
        初始化 Context 管理器
        配置从 AEIQConfig 读取
        """
        self.contexts: Dict[str, AEContext] = {}
        self.session_timeout = config.get_session_timeout()
        self._lock = asyncio.Lock()

    async def get_or_create_context(self, session_id: str) -> AEContext:
        """
        获取或创建 Context 实例

        Args:
            session_id: 会话 ID

        Returns:
            AEContext 实例
        """
        async with self._lock:
            if session_id not in self.contexts:
                self.contexts[session_id] = AEContext(session_id=session_id)
            else:
                # 更新访问时间
                self.contexts[session_id].updated_at = datetime.now()

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
