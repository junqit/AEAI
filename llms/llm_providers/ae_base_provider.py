"""
AE Base Provider - LLM 提供商基类
"""
import logging
from abc import ABC, abstractmethod
from AEQuestion import AEQuestion
from AEAiLevel import AEAiLevel

logger = logging.getLogger(__name__)


class AEBaseProvider(ABC):
    """LLM 提供商基类"""

    MAX_TOKENS: int = 4096

    def __init__(self):
        self.name = self.__class__.__name__
        self.is_loaded = False

    def generate(self, question: AEQuestion, level: AEAiLevel) -> str:
        self._normalize_messages(question)
        logger.info(f"[{self.name}] 发送 - messages={question.messages}")
        result = self._generate(question, level)
        logger.info(f"[{self.name}] 接收 - result={result[:200] if isinstance(result, str) else str(result)[:200]}")
        return result

    @staticmethod
    def _normalize_messages(question: AEQuestion):
        """将 context role 转换为 user role，确保所有 LLM API 兼容"""
        for msg in question.messages:
            if msg.get("role") == "context" or msg.get("role") == "system":
                msg["role"] = "user"

    @abstractmethod
    def _generate(self, question: AEQuestion, level: AEAiLevel) -> str:
        pass

    @abstractmethod
    def load(self):
        pass

    @abstractmethod
    def cleanup(self):
        pass

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "loaded": self.is_loaded
        }
