"""
缓存存储实现 - 支持内存和持久化
"""
from typing import List, Dict, Any, Optional
import json
import os
from pathlib import Path
from datetime import datetime
from threading import Lock

from .cache_entry import CacheEntry, MessageRole, ConversationTurn


class QuestionCacheStore:
    """问题缓存存储"""

    def __init__(self, cache_dir: Optional[str] = None, enable_persistence: bool = True):
        """
        初始化缓存存储

        Args:
            cache_dir: 缓存文件存储目录，默认为当前目录下的cache_data
            enable_persistence: 是否启用持久化存储
        """
        self.enable_persistence = enable_persistence
        self.cache_dir = Path(cache_dir) if cache_dir else Path(__file__).parent / "cache_data"

        if self.enable_persistence:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 内存缓存：session_id -> List[CacheEntry]
        self._memory_cache: Dict[str, List[CacheEntry]] = {}
        self._lock = Lock()

    def add_entry(self, entry: CacheEntry):
        """
        添加缓存条目

        Args:
            entry: 缓存条目
        """
        with self._lock:
            session_id = entry.session_id

            # 添加到内存缓存
            if session_id not in self._memory_cache:
                self._memory_cache[session_id] = []
            self._memory_cache[session_id].append(entry)

            # 持久化
            if self.enable_persistence:
                self._save_to_disk(session_id)

    def add_question(
        self,
        session_id: str,
        question: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CacheEntry:
        """
        添加用户问题

        Args:
            session_id: 会话ID
            question: 问题内容
            metadata: 额外元数据

        Returns:
            创建的缓存条目
        """
        entry = CacheEntry(
            session_id=session_id,
            role=MessageRole.USER,
            content=question,
            metadata=metadata
        )
        self.add_entry(entry)
        return entry

    def add_response(
        self,
        session_id: str,
        response: str,
        llm_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> CacheEntry:
        """
        添加LLM回复

        Args:
            session_id: 会话ID
            response: 回复内容
            llm_type: LLM类型
            metadata: 额外元数据

        Returns:
            创建的缓存条目
        """
        entry = CacheEntry(
            session_id=session_id,
            role=MessageRole.ASSISTANT,
            content=response,
            llm_type=llm_type,
            metadata=metadata
        )
        self.add_entry(entry)
        return entry

    def get_session_history(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[CacheEntry]:
        """
        获取会话历史

        Args:
            session_id: 会话ID
            limit: 限制返回的条目数量（最新的N条）

        Returns:
            缓存条目列表
        """
        with self._lock:
            # 先从内存获取
            if session_id in self._memory_cache:
                entries = self._memory_cache[session_id]
            # 否则从磁盘加载
            elif self.enable_persistence:
                entries = self._load_from_disk(session_id)
                self._memory_cache[session_id] = entries
            else:
                entries = []

            # 应用限制
            if limit and len(entries) > limit:
                return entries[-limit:]
            return entries

    def get_conversation_turns(self, session_id: str) -> List[ConversationTurn]:
        """
        获取结构化的对话轮次

        Args:
            session_id: 会话ID

        Returns:
            对话轮次列表
        """
        entries = self.get_session_history(session_id)
        turns = []
        current_question = None
        current_responses = []

        for entry in entries:
            if entry.role == MessageRole.USER:
                # 如果有前一个问题，保存它
                if current_question is not None:
                    turns.append(ConversationTurn(current_question, current_responses))
                # 开始新的轮次
                current_question = entry
                current_responses = []
            elif entry.role == MessageRole.ASSISTANT:
                current_responses.append(entry)

        # 保存最后一个问题
        if current_question is not None:
            turns.append(ConversationTurn(current_question, current_responses))

        return turns

    def clear_session(self, session_id: str):
        """
        清空指定会话的缓存

        Args:
            session_id: 会话ID
        """
        with self._lock:
            # 清空内存
            if session_id in self._memory_cache:
                del self._memory_cache[session_id]

            # 删除持久化文件
            if self.enable_persistence:
                cache_file = self._get_cache_file_path(session_id)
                if cache_file.exists():
                    cache_file.unlink()

    def get_all_sessions(self) -> List[str]:
        """
        获取所有会话ID列表

        Returns:
            会话ID列表
        """
        with self._lock:
            # 合并内存和磁盘的会话ID
            sessions = set(self._memory_cache.keys())

            if self.enable_persistence and self.cache_dir.exists():
                for file in self.cache_dir.glob("*.json"):
                    session_id = file.stem
                    sessions.add(session_id)

            return sorted(list(sessions))

    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            统计信息字典
        """
        sessions = self.get_all_sessions()
        total_entries = sum(
            len(self.get_session_history(sid)) for sid in sessions
        )

        return {
            "total_sessions": len(sessions),
            "total_entries": total_entries,
            "memory_sessions": len(self._memory_cache),
            "cache_dir": str(self.cache_dir) if self.enable_persistence else None
        }

    def _get_cache_file_path(self, session_id: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{session_id}.json"

    def _save_to_disk(self, session_id: str):
        """保存会话到磁盘"""
        if session_id not in self._memory_cache:
            return

        cache_file = self._get_cache_file_path(session_id)
        entries = self._memory_cache[session_id]

        data = {
            "session_id": session_id,
            "entries": [e.to_dict() for e in entries],
            "updated_at": datetime.now().isoformat()
        }

        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_from_disk(self, session_id: str) -> List[CacheEntry]:
        """从磁盘加载会话"""
        cache_file = self._get_cache_file_path(session_id)

        if not cache_file.exists():
            return []

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return [CacheEntry.from_dict(e) for e in data["entries"]]
        except Exception as e:
            print(f"Error loading cache for session {session_id}: {e}")
            return []
