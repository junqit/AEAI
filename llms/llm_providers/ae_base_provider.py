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
        messages = question.messages or []
        roles = [m.get("role", "?") for m in messages if isinstance(m, dict)]
        logger.info("[%s] 发送 level=%s msg_count=%d roles=%s",
                    self.name, getattr(level, "name", level), len(messages), roles)
        result = self._generate(question, level)
        result_len = len(result) if isinstance(result, str) else len(str(result))
        logger.info("[%s] 接收 result_len=%d", self.name, result_len)
        return result

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
