"""
AE Gemini Provider - Google Gemini 本地模型提供商
负责组装 Gemini 模型需要的所有信息
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from .ae_base_provider import AEBaseProvider
from AEQuestion import AEQuestion
from AEAiLevel import AEAiLevel

class AEGeminiProvider(AEBaseProvider):
    """Gemini 本地模型提供商"""

    def __init__(self):
        super().__init__()
        self.gemini_model = None
        self.model_path = "/Users/tianjunqi/.cache/huggingface/hub/models--google--gemma-4-E2B-it/snapshots/b446025c61ecea876162774ee247706056963aba"

        self.load()

    def load(self):
        """加载 Gemini 本地模型"""
        if self.is_loaded:
            return

        try:
            # 导入 Gemini 模型类
            from llm.gemini.gemini_model import get_gemini_model

            print(f"正在初始化 {self.name}...")
            self.gemini_model = get_gemini_model(self.model_path)

            # 加载模型
            # self.gemini_model.load()

            self.is_loaded = True
            print(f"✅ {self.name} loaded successfully!")

        except Exception as e:
            print(f"❌ Failed to load {self.name}: {str(e)}")
            raise

    def generate(self, question: AEQuestion, level: AEAiLevel, max_tokens: int) -> str:
        """
        使用 Gemini 本地模型生成回复
        在这里组装 Gemini 模型需要的所有信息

        Args:
            question: 问题对象
            level: AI 级别
            max_tokens: 最大 token 数

        Returns:
            str: Gemini 生成的回复
        """
        try:
            # 确保模型已加载
            if not self.is_loaded:
                self.load()

            # 1. 组装提示词
            prompt = self._build_prompt(question)

            # 2. 根据 level 获取生成参数
            generation_params = self._get_generation_params(level, max_tokens)

            # 3. 调用模型生成
            print(f"Calling Gemini Model:")
            print(f"  Level: {level.name}")
            print(f"  Max Tokens: {max_tokens}")
            print(f"  Prompt Length: {len(prompt)}")

            response = self.gemini_model.generate(
                prompt=prompt,
                **generation_params
            )

            # 4. 验证响应是否有效
            if not response or response.strip() == "":
                return "Gemini 模型未返回有效响应"

            # 5. 清理响应（移除可能残留的输入部分）
            if "Assistant:" in response:
                # 只取 Assistant: 后面的内容
                response = response.split("Assistant:")[-1].strip()

            return response

        except Exception as e:
            raise Exception(f"Gemini 本地模型调用失败: {str(e)}")

    def _build_prompt(self, question: AEQuestion) -> str:
        """
        构建 Gemini 模型的提示词

        Args:
            question: 问题对象

        Returns:
            str: 完整的提示词
        """
        prompt_parts = []

        # 添加系统提示词
        if question.system:
            prompt_parts.append(f"System: {question.system}\n")

        # 添加用户问题
        prompt_parts.append(f"User: {question.question}\n")
        prompt_parts.append("Assistant:")

        return "\n".join(prompt_parts)

    def _get_generation_params(self, level: AEAiLevel, max_tokens: int) -> dict:
        """
        根据 AI 级别获取生成参数

        Args:
            level: AI 级别
            max_tokens: 最大 token 数

        Returns:
            dict: 生成参数
        """
        # 根据不同级别设置不同的参数
        params_map = {
            AEAiLevel.default: {
                "max_new_tokens": max_tokens,
                "temperature": 0.7,
                "top_p": 0.9,
                "top_k": 50,
                "do_sample": True
            },
            AEAiLevel.middle: {
                "max_new_tokens": max_tokens,
                "temperature": 0.5,
                "top_p": 0.85,
                "top_k": 40,
                "do_sample": True
            },
            AEAiLevel.high: {
                "max_new_tokens": max_tokens,
                "temperature": 0.3,
                "top_p": 0.8,
                "top_k": 30,
                "do_sample": True
            }
        }

        return params_map.get(level, params_map[AEAiLevel.default])

    def get_status(self) -> dict:
        """获取提供商状态"""
        status = super().get_status()
        if self.gemini_model:
            status["model_status"] = self.gemini_model.get_status()
        return status

    def cleanup(self):
        """清理 Gemini 模型资源"""
        if self.gemini_model is not None:
            self.gemini_model.cleanup()
            self.gemini_model = None

        self.is_loaded = False
        print(f"🧹 {self.name} cleaned up")
