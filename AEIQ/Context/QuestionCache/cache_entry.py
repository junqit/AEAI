"""
缓存条目数据结构
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum


class MessageRole(Enum):
    """消息角色枚举"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class CacheEntry:
    """单条缓存记录"""

    def __init__(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        llm_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None
    ):
        """
        初始化缓存条目

        Args:
            session_id: 会话ID
            role: 消息角色（用户/助手/系统）
            content: 消息内容
            llm_type: LLM类型（对于assistant角色）
            metadata: 额外的元数据
            timestamp: 时间戳，默认为当前时间
        """
        self.session_id = session_id
        self.role = role
        self.content = content
        self.llm_type = llm_type
        self.metadata = metadata or {}
        self.timestamp = timestamp or datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "session_id": self.session_id,
            "role": self.role.value,
            "content": self.content,
            "llm_type": self.llm_type,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CacheEntry':
        """从字典创建缓存条目"""
        return cls(
            session_id=data["session_id"],
            role=MessageRole(data["role"]),
            content=data["content"],
            llm_type=data.get("llm_type"),
            metadata=data.get("metadata", {}),
            timestamp=datetime.fromisoformat(data["timestamp"])
        )

    def to_message_format(self) -> Dict[str, str]:
        """
        转换为标准消息格式（用于LLM API）

        Returns:
            {"role": "user/assistant", "content": "..."}
        """
        return {
            "role": self.role.value,
            "content": self.content
        }


class ConversationTurn:
    """一轮对话（一个问题+多个LLM回复）"""

    def __init__(self, question: CacheEntry, responses: List[CacheEntry]):
        """
        初始化对话轮次

        Args:
            question: 用户问题
            responses: LLM回复列表（可能有多个LLM的回复）
        """
        self.question = question
        self.responses = responses
        self.timestamp = question.timestamp

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "question": self.question.to_dict(),
            "responses": [r.to_dict() for r in self.responses],
            "timestamp": self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationTurn':
        """从字典创建对话轮次"""
        return cls(
            question=CacheEntry.from_dict(data["question"]),
            responses=[CacheEntry.from_dict(r) for r in data["responses"]]
        )
