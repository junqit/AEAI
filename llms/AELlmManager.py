"""
AELlmManager - 统一的 LLM 管理器
支持多种 LLM 类型：Claude、ChatGPT、DeepSeek、Gemini 等
使用独立的 Provider 类管理各个 LLM
"""
import os
from typing import Optional, Dict, Any
from question.AEQuestion import LLMType, AEQuestion
from AEAiLevel import AEAiLevel
from llm_providers import (
    AEClaudeProvider,
    AEChatGPTProvider,
    AEDeepSeekProvider,
    AEGeminiProvider
)


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

        # 从环境变量获取默认 LLM 类型
        default_llm = os.getenv("DEFAULT_LLM_TYPE", "claude").lower()
        self._set_llm_type(default_llm)

        print(f"AELlmManager initialized with LLM type: {self.llm_type.value}")

    def _init_providers(self):
        """初始化所有 Provider"""
        self.providers = {
            LLMType.CLAUDE: AEClaudeProvider(),
            LLMType.CHATGPT: AEChatGPTProvider(),
            LLMType.DEEPSEEK: AEDeepSeekProvider(),
            LLMType.GEMINI: AEGeminiProvider()
        }

    def _set_llm_type(self, llm_type_str: str):
        """设置 LLM 类型"""
        llm_type_map = {
            "claude": LLMType.CLAUDE,
            "chatgpt": LLMType.CHATGPT,
            "deepseek": LLMType.DEEPSEEK,
            "gemini": LLMType.GEMINI
        }
        self.llm_type = llm_type_map.get(llm_type_str.lower(), LLMType.CLAUDE)

    def generate(
        self,
        message: str,
        llm_type: Optional[LLMType] = None,
        level: AEAiLevel = AEAiLevel.default,
        system: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        max_tokens: int = 256
    ) -> Dict[str, Any]:
        """
        生成回复

        Args:
            message: 用户消息
            llm_type: LLM 类型（如果不指定则使用默认类型）
            level: AI 级别
            system: 系统提示词
            context: 上下文信息
            max_tokens: 最大生成token数

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

        # 使用指定的 LLM 类型，如果没有指定则使用默认类型
        current_llm_type = llm_type or self.llm_type
        start_time = time.time()

        # 创建 AEQuestion 对象
        question = AEQuestion(
            question=message,
            system=system,
            context=context or {}
        )

        # 获取对应的 Provider 并生成
        provider = self.providers.get(current_llm_type)
        if provider is None:
            elapsed = time.time() - start_time
            return {
                "response": None,
                "status": "error",
                "error": f"不支持的 LLM 类型: {current_llm_type}",
                "elapsed_seconds": elapsed
            }

        try:
            response = provider.generate(question, level, max_tokens)
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
                "error": f"{current_llm_type.value} 调用失败: {str(e)}",
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

    def set_llm_type(self, llm_type: LLMType):
        """动态切换 LLM 类型"""
        self.llm_type = llm_type

        # 如果切换到 Gemini，确保模型已加载
        if llm_type == LLMType.GEMINI:
            gemini_provider = self.providers.get(LLMType.GEMINI)
            if gemini_provider and not gemini_provider.is_loaded:
                print("Loading Gemini model for switched LLM type...")
                gemini_provider.load()

        print(f"LLM type switched to: {llm_type.value}")

    def cleanup_provider(self, llm_type: LLMType):
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
                print(f"Error cleaning up {llm_type.value}: {e}")

        _manager_instance = None
        print("AELlmManager cleaned up")

