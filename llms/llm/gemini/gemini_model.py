"""
Gemini 本地模型类
封装 Gemini 模型的加载、生成和资源管理
"""
import torch
from transformers import AutoProcessor, AutoModelForCausalLM
from typing import Optional


class AEGeminiModel:
    """Gemini 本地模型封装类"""

    def __init__(self, model_path: str = None):
        """
        初始化 Gemini 模型

        Args:
            model_path: 模型路径，如果不指定则使用默认路径
        """
        self.model_path = model_path or "/Users/tianjunqi/.cache/huggingface/hub/models--google--gemma-4-E2B-it/snapshots/b446025c61ecea876162774ee247706056963aba"
        self.model = None
        self.processor = None
        self.is_loaded = False
        self.device = None

    def load(self):
        """
        加载 Gemini 模型和处理器

        Raises:
            Exception: 加载失败时抛出异常
        """
        if self.is_loaded:
            print("Gemini 模型已加载，跳过重复加载")
            return

        try:
            print(f"正在加载 Gemini Processor...")
            self.processor = AutoProcessor.from_pretrained(self.model_path)

            print(f"正在加载 Gemini Model...")
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                device_map="auto",
                torch_dtype=torch.bfloat16
            )

            self.device = self.model.device
            self.is_loaded = True
            print(f"✅ Gemini 模型加载成功！")
            print(f"   Device: {self.device}")

        except Exception as e:
            print(f"❌ Gemini 模型加载失败: {str(e)}")
            self.cleanup()
            raise

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.9,
        top_k: int = 50,
        do_sample: bool = True
    ) -> str:
        """
        使用 Gemini 模型生成文本

        Args:
            prompt: 输入提示词
            max_new_tokens: 最大生成 token 数
            temperature: 温度参数
            top_p: nucleus sampling 参数
            top_k: top-k sampling 参数
            do_sample: 是否使用采样

        Returns:
            str: 生成的文本

        Raises:
            Exception: 生成失败时抛出异常
        """
        if not self.is_loaded:
            raise Exception("Gemini 模型未加载，请先调用 load() 方法")

        try:
            # 1. 处理输入
            inputs = self.processor(prompt, return_tensors="pt")

            # 将 inputs 移到正确的设备
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # 2. 生成参数
            generation_params = {
                "max_new_tokens": max_new_tokens,
                "do_sample": do_sample,
            }

            # 设置 pad_token 和 eos_token
            if hasattr(self.processor, 'tokenizer'):
                if self.processor.tokenizer.pad_token_id is not None:
                    generation_params["pad_token_id"] = self.processor.tokenizer.pad_token_id
                if self.processor.tokenizer.eos_token_id is not None:
                    generation_params["eos_token_id"] = self.processor.tokenizer.eos_token_id

            if do_sample:
                generation_params.update({
                    "temperature": temperature,
                    "top_p": top_p,
                    "top_k": top_k
                })

            # 3. 生成输出
            with torch.no_grad():
                outputs = self.model.generate(**inputs, **generation_params)

            # 4. 解码输出
            response = self.processor.decode(outputs[0], skip_special_tokens=True)

            # 5. 移除输入部分，只返回生成的内容
            if response.startswith(prompt):
                response = response[len(prompt):].strip()

            return response

        except Exception as e:
            raise Exception(f"Gemini 生成失败: {str(e)}")

    def get_status(self) -> dict:
        """
        获取模型状态

        Returns:
            dict: 包含模型状态信息的字典
        """
        return {
            "model_path": self.model_path,
            "is_loaded": self.is_loaded,
            "device": str(self.device) if self.device else None,
            "model_type": "gemma-4-E2B-it"
        }

    def cleanup(self):
        """清理模型资源"""
        if self.model is not None:
            del self.model
            self.model = None

        if self.processor is not None:
            del self.processor
            self.processor = None

        self.device = None
        self.is_loaded = False
        print("🧹 Gemini 模型资源已清理")


# 全局单例实例
_gemini_model_instance: Optional[AEGeminiModel] = None


def get_gemini_model(model_path: str = None) -> AEGeminiModel:
    """
    获取 Gemini 模型单例实例

    Args:
        model_path: 模型路径（仅首次调用时有效）

    Returns:
        AEGeminiModel: Gemini 模型实例
    """
    global _gemini_model_instance
    if _gemini_model_instance is None:
        _gemini_model_instance = AEGeminiModel(model_path)
    return _gemini_model_instance


def cleanup_gemini_model():
    """清理全局 Gemini 模型实例"""
    global _gemini_model_instance
    if _gemini_model_instance is not None:
        _gemini_model_instance.cleanup()
        _gemini_model_instance = None
