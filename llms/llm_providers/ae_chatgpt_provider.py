"""
AE ChatGPT Provider - OpenAI ChatGPT API 提供商
负责组装 ChatGPT API 需要的所有信息
"""
from .ae_base_provider import AEBaseProvider
from AEQuestion import AEQuestion
from AEAiLevel import AEAiLevel


class AEChatGPTProvider(AEBaseProvider):
    """ChatGPT API 提供商"""

    def __init__(self):
        super().__init__()
        self.api_key = None
        self.client = None

    def load(self):
        """加载 ChatGPT API 配置"""
        import os
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            print("⚠️  Warning: OPENAI_API_KEY not found in environment")
        self.is_loaded = True
        print(f"✅ {self.name} loaded")

    def generate(self, question: AEQuestion, level: AEAiLevel, max_tokens: int) -> str:
        """
        使用 ChatGPT API 生成回复
        在这里组装 ChatGPT API 需要的所有信息

        Args:
            question: 问题对象
            level: AI 级别
            max_tokens: 最大 token 数

        Returns:
            str: ChatGPT 生成的回复
        """
        if not self.is_loaded:
            self.load()

        # 1. 根据 level 选择模型
        model = self._get_model_by_level(level)

        # 2. 组装消息列表
        messages = question.to_messages()

        # 3. 如果有系统提示词，添加到消息开头
        if question.system:
            messages = [{"role": "system", "content": question.system}] + messages

        # 4. 组装请求参数
        request_params = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7
        }

        # 5. 如果有工具，添加工具参数
        if question.tools:
            request_params["tools"] = question.tools

        # TODO: 实现 ChatGPT API 调用
        # from openai import OpenAI
        # client = OpenAI(api_key=self.api_key)
        # response = client.chat.completions.create(**request_params)
        # return response.choices[0].message.content

        raise NotImplementedError("ChatGPT API 调用尚未实现")

    def _get_model_by_level(self, level: AEAiLevel) -> str:
        """
        根据 AI 级别选择 ChatGPT 模型

        Args:
            level: AI 级别

        Returns:
            str: 模型名称
        """
        model_map = {
            AEAiLevel.default: "gpt-3.5-turbo",
            AEAiLevel.middle: "gpt-4",
            AEAiLevel.high: "gpt-4-turbo"
        }
        return model_map.get(level, "gpt-3.5-turbo")

    def cleanup(self):
        """清理 ChatGPT 资源"""
        self.api_key = None
        self.client = None
        self.is_loaded = False
        print(f"🧹 {self.name} cleaned up")
