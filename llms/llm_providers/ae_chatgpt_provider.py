"""
AE ChatGPT Provider - OpenAI ChatGPT API 提供商
使用 AEGPTModel 进行数据请求
"""
from typing import Optional, Callable, Dict, Any
from .ae_base_provider import AEBaseProvider
from AEQuestion import AEQuestion
from llm.gpt.gpt import AEGPTModel


class AEChatGPTProvider(AEBaseProvider):
    """ChatGPT API 提供商"""

    def __init__(self):
        super().__init__()
        self._gpt = AEGPTModel()

    def load(self):
        self._gpt.load()
        self.is_loaded = True

    def _generate(self, question: AEQuestion,
                  think_process: Optional[Callable[[Dict[str, Any]], None]] = None,
                  delta_process: Optional[Callable[[Dict[str, Any]], None]] = None) -> str:
        if not self.is_loaded:
            self.load()

        # 只传 messages 与 level，模型名与 max_tokens 由 AEGPTModel 内部决定
        result = self._gpt.generate(
            messages=question.messages,
            level=question.level,
            think_process=think_process,
            delta_process=delta_process,
        )

        if isinstance(result, str):
            return result

        content = result.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", "")

        return str(result)

    def cleanup(self):
        self._gpt.cleanup()
        self.is_loaded = False
