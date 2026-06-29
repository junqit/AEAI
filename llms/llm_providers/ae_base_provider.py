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
        logger.info(f"[{self.name}] 发送 - messages={question.messages}")
        result = self._generate(question, level)
        logger.info(f"[{self.name}] 接收 - result={result[:200] if isinstance(result, str) else str(result)[:200]}")
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
