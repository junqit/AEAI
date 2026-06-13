"""
AE DeepSeek Provider - DeepSeek API 提供商
负责组装 DeepSeek API 需要的所有信息
"""
from .ae_base_provider import AEBaseProvider
from AEQuestion import AEQuestion
from AEAiLevel import AEAiLevel


class AEDeepSeekProvider(AEBaseProvider):
    """DeepSeek API 提供商"""

    def __init__(self):
        super().__init__()
        self.api_key = None
        self.base_url = "https://api.deepseek.com"

    def load(self):
        """加载 DeepSeek API 配置"""
        import os
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            print("⚠️  Warning: DEEPSEEK_API_KEY not found in environment")
        self.is_loaded = True
        print(f"✅ {self.name} loaded")

    MAX_TOKENS = 64000

    def _generate(self, question: AEQuestion, level: AEAiLevel) -> str:
        if not self.is_loaded:
            self.load()

        model = self._get_model_by_level(level)
        messages = question.messages

        request_params = {
            "model": model,
            "messages": messages,
            "max_tokens": self.MAX_TOKENS,
            "temperature": 0.7
        }

        # TODO: 实现 DeepSeek API 调用
        # DeepSeek API 兼容 OpenAI 格式
        # import requests
        # response = requests.post(
        #     f"{self.base_url}/v1/chat/completions",
        #     headers={"Authorization": f"Bearer {self.api_key}"},
        #     json=request_params
        # )
        # result = response.json()
        # return result['choices'][0]['message']['content']

        raise NotImplementedError("DeepSeek API 调用尚未实现")

    def _get_model_by_level(self, level: AEAiLevel) -> str:
        """
        根据 AI 级别选择 DeepSeek 模型

        Args:
            level: AI 级别

        Returns:
            str: 模型名称
        """
        model_map = {
            AEAiLevel.default: "deepseek-chat",
            AEAiLevel.middle: "deepseek-coder",
            AEAiLevel.high: "deepseek-coder"
        }
        return model_map.get(level, "deepseek-chat")

    def cleanup(self):
        """清理 DeepSeek 资源"""
        self.api_key = None
        self.is_loaded = False
        print(f"🧹 {self.name} cleaned up")
