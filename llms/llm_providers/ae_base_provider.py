"""
AE Base Provider - LLM 提供商基类
"""
import json
import logging
from typing import Optional, Callable, Dict, Any
from abc import ABC, abstractmethod
from AEQuestion import AEQuestion

logger = logging.getLogger(__name__)


class AEBaseProvider(ABC):
    """LLM 提供商基类"""

    MAX_TOKENS: int = 4096

    def __init__(self):
        self.name = self.__class__.__name__
        self.is_loaded = False

    def generate(self, question: AEQuestion,
                 think_process: Optional[Callable[[Dict[str, Any]], None]] = None,
                 delta_process: Optional[Callable[[Dict[str, Any]], None]] = None) -> str:
        # 打印完整的请求 messages（JSON）与回复内容，统一在此处输出；各 provider 内不再打印
        level = question.level
        logger.info("[%s] 发送 level=%s messages=%s",
                    self.name, getattr(level, "name", level),
                    json.dumps(question.messages, ensure_ascii=False, indent=2))
        result = self._generate(question, think_process, delta_process)
        logger.info("[%s] 接收 result=%s",
                    self.name, result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2))
        return result

    @abstractmethod
    def _generate(self, question: AEQuestion,
                  think_process: Optional[Callable[[Dict[str, Any]], None]] = None,
                  delta_process: Optional[Callable[[Dict[str, Any]], None]] = None) -> str:
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
