"""
AE Base Provider - LLM 提供商基类
"""
from abc import ABC, abstractmethod
from AEQuestion import AEQuestion
from AEAiLevel import AEAiLevel


class AEBaseProvider(ABC):
    """LLM 提供商基类"""

    def __init__(self):
        """初始化提供商"""
        self.name = self.__class__.__name__
        self.is_loaded = False

    @abstractmethod
    def generate(self, question: AEQuestion, level: AEAiLevel, max_tokens: int) -> str:
        """
        生成回复

        Args:
            question: 问题对象
            level: AI 级别
            max_tokens: 最大 token 数

        Returns:
            str: 生成的回复
        """
        pass

    @abstractmethod
    def load(self):
        """加载必要的资源（如模型、API 配置等）"""
        pass

    @abstractmethod
    def cleanup(self):
        """清理资源"""
        pass

    def get_status(self) -> dict:
        """获取提供商状态"""
        return {
            "name": self.name,
            "loaded": self.is_loaded
        }
