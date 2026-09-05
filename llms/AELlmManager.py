"""
AELlmManager - 统一的 LLM 管理器
支持多种 LLM 类型：Claude、ChatGPT、DeepSeek、Gemini、Qwen 等
使用独立的 Provider 类管理各个 LLM
"""
import os
import logging
from typing import Optional, Callable, Dict, Any
from question.AEQuestion import AELLMType, AEQuestion
from AEAiLevel import AEAiLevel
from llm_providers import (
    AEClaudeProvider,
    AEChatGPTProvider,
    AEDeepSeekProvider,
    AEGeminiProvider,
    AEZhipuProvider,
    AEQwenProvider
)

logger = logging.getLogger(__name__)


class AELlmManager:
    """
    统一的 LLM 管理器
    根据配置的 LLM 类型，调用对应的 Provider
    """

    _instance = None  # 单例模式

    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化管理器"""
        if hasattr(self, '_initialized'):
            return

        self._initialized = True
        self.llm_type = None
        self.providers = {}  # Provider 实例缓存

        # 初始化所有 Provider
        self._init_providers()

        # 从环境变量获取默认 LLM 类型（直接用枚举值反查，无需维护字符串映射表）
        default_llm = os.getenv("DEFAULT_LLM_TYPE", "claude").lower()
        try:
            self.llm_type = AELLMType(default_llm)
        except ValueError:
            self.llm_type = AELLMType.CLAUDE

    def _init_providers(self):
        """初始化所有 Provider 并加载模型"""

        # 实例化所有 Provider
        self.providers = {
            AELLMType.CLAUDE: AEClaudeProvider(),
            AELLMType.CHATGPT: AEChatGPTProvider(),
            AELLMType.DEEPSEEK: AEDeepSeekProvider(),
            AELLMType.ZHIPU: AEZhipuProvider(),
            AELLMType.QWEN: AEQwenProvider()
            # AELLMType.GEMINI: AEGeminiProvider()
        }

        # 加载每个 Provider（如果需要预加载）
        for llm_type, provider in self.providers.items():
            try:
                if hasattr(provider, 'load') and not provider.is_loaded:
                    provider.load()
            except Exception as e:
                logger.warning("Failed to load %s provider: %s", llm_type.value, e)
                # 继续加载其他 Provider，不中断整个初始化过程

    @staticmethod
    def _default_think_process(info: Dict[str, Any]) -> None:
        """默认 think_process：无操作占位。调用方未提供回调时使用；需进度输出时由调用方传入回调。"""

    @staticmethod
    def _default_delta_process(info: Dict[str, Any]) -> None:
        """默认 delta_process：无操作占位。"""

    async def generate(self, question: AEQuestion,
                       think_process: Optional[Callable[[Dict[str, Any]], None]] = None,
                       delta_process: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        """
        生成回复

        Args:
            question: AEQuestion 对象，包含所有必要信息（messages、llm_type、level、max_tokens、system、context、tools）
            think_process: 流式逐 delta（思考过程）进度回调，接收 make_progress_info 字典
                （progress / content / generated_length / max_tokens / remaining / final，final=False）。
                为 None 时使用默认回调打印；仅流式模型（DeepSeek）会触发，非流式模型不回调。
            delta_process: 最终结果进度回调，接收同一 make_progress_info 字典（final=True）。
                为 None 时使用默认回调打印；所有模型在生成完成后回调一次。

        Returns:
            Dict[str, Any]: 包含响应详情的字典
            格式: {
                "response": "...",
                "status": "success" | "error",
                "error": None | "错误信息",
                "elapsed_seconds": 1.2
            }
        """
        import time

        # 从 question 对象中获取所有参数
        llm_type = question.llm_type

        # 未提供回调时使用默认打印回调（进度信息统一在此输出，模型层不再打印 stream 日志）
        if think_process is None:
            think_process = self._default_think_process
        if delta_process is None:
            delta_process = self._default_delta_process

        start_time = time.time()

        # 获取对应的 Provider 并生成
        provider = self.providers.get(llm_type)
        if provider is None:
            elapsed = time.time() - start_time
            return {
                "response": None,
                "status": "error",
                "error": f"不支持的 LLM 类型: {llm_type}",
                "elapsed_seconds": elapsed
            }

        try:
            response = await provider.generate(question, think_process, delta_process)
            elapsed = time.time() - start_time
            return {
                "response": response,
                "status": "success",
                "error": None,
                "elapsed_seconds": elapsed
            }
        except Exception as e:
            elapsed = time.time() - start_time
            return {
                "response": None,
                "status": "error",
                "error": f"{llm_type.value} 调用失败: {str(e)}",
                "elapsed_seconds": elapsed
            }

    def get_status(self) -> Dict[str, Any]:
        """获取 LLM 管理器状态"""
        providers_status = {}
        for llm_type, provider in self.providers.items():
            providers_status[llm_type.value] = provider.get_status()

        return {
            "llm_type": self.llm_type.value,
            "available": True,
            "providers": providers_status
        }

    def cleanup_provider(self, llm_type: AELLMType):
        """清理指定 Provider 的资源"""
        provider = self.providers.get(llm_type)
        if provider:
            provider.cleanup()


# 全局单例实例
_manager_instance = None
def get_ae_llm_manager() -> AELlmManager:
    """获取 AELlmManager 单例实例"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = AELlmManager()
    return _manager_instance


def cleanup_ae_llm_manager():
    """清理 AELlmManager 资源"""
    global _manager_instance
    if _manager_instance is not None:
        # 清理所有 Provider
        for llm_type, provider in _manager_instance.providers.items():
            try:
                provider.cleanup()
            except Exception as e:
                logger.error("Error cleaning up %s: %s", llm_type.value, e)

        _manager_instance = None

