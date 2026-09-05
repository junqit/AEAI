"""
AE Base Provider - LLM 提供商基类
"""
import json
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Callable, Dict, Any
from abc import ABC, abstractmethod
from AEQuestion import AEQuestion

logger = logging.getLogger(__name__)


class AEBaseProvider(ABC):
    """LLM 提供商基类"""

    MAX_TOKENS: int = 4096
    # per-provider 并行上限：provider 专属线程池的 max_workers，限制同时执行 _generate 的请求数；子类按后端能力覆盖
    MAX_CONCURRENCY: int = 10

    def __init__(self):
        self.name = self.__class__.__name__
        self.is_loaded = False
        # provider 专属线程池（并行队列）：max_workers=并发上限，超出的请求在线程池内排队等待
        self._executor: Optional[ThreadPoolExecutor] = None

    def _get_executor(self) -> ThreadPoolExecutor:
        """惰性创建 provider 专属线程池，max_workers=MAX_CONCURRENCY。"""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self.MAX_CONCURRENCY,
                thread_name_prefix=f"{self.name}-worker"
            )
            logger.info(f"🔧 {self.name} 并行队列初始化 max_workers={self.MAX_CONCURRENCY}")
        return self._executor

    async def generate(self, question: AEQuestion,
                       think_process: Optional[Callable[[Dict[str, Any]], None]] = None,
                       delta_process: Optional[Callable[[Dict[str, Any]], None]] = None) -> str:
        # 打印完整的请求 messages（JSON）与回复内容，统一在此处输出；各 provider 内不再打印
        level = question.level
        logger.info("[%s] 发送 level=%s messages=%s",
                    self.name, getattr(level, "name", level),
                    json.dumps(question.messages, ensure_ascii=False, indent=2))
        # 提交到 provider 专属线程池（并行队列）：超出 max_workers 的请求排队等待，
        # 同步 _generate 不阻塞事件循环
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            self._get_executor(), self._generate, question, think_process, delta_process
        )
        logger.info("[%s] 接收 result=%s",
                    self.name,
                    result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2))
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
