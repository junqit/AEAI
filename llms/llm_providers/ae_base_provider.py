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
from common.aellm_enums import AEQuestionType

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
        qt = question.question_type
        logger.info("[%s] 发送 level=%s question_type=%s messages=%s",
                    self.name, getattr(level, "name", level), qt.value,
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

    # ==================== AEQuestionType 适配 ====================

    def _prepare_messages(self, question: AEQuestion) -> list:
        """按 question_type 适配 messages；子类可覆写 _adapt_image_messages 处理图片格式转换。"""
        messages = question.messages
        if question.question_type == AEQuestionType.image:
            messages = self._adapt_image_messages(messages)
        return messages

    def _adapt_image_messages(self, messages: list) -> list:
        """适配图片消息格式；默认透传（OpenAI image_url 格式，Qwen/ChatGPT 直接用）。子类按 API 差异覆写。"""
        return messages

    @staticmethod
    def _convert_image_url_to_anthropic(content_list: list) -> list:
        """将 OpenAI image_url 格式转为 Anthropic image 格式（Claude/DeepSeek/Zhipu 用）。"""
        adapted = []
        for item in content_list:
            if isinstance(item, dict) and item.get("type") == "image_url":
                url = item.get("image_url", {}).get("url", "")
                if url.startswith("data:"):
                    header, b64data = url.split(",", 1)
                    media_type = header.split(":")[1].split(";")[0]  # e.g. image/png
                    adapted.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64data}})
                else:
                    adapted.append({"type": "image", "source": {"type": "url", "url": url}})
            else:
                adapted.append(item)
        return adapted
