"""
Gemini 本地模型类
封装 Gemini 模型的加载、生成和资源管理
使用 mlx_lm 库进行模型加载和推理
"""
from typing import Optional, List, Dict, Any, Callable
import logging
import re
from mlx_lm import load, generate
from mlx_lm.sample_utils import make_sampler

from AEAiLevel import AEAiLevel
from common.llm_utils import split_system_messages, fire_progress

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class AEGeminiModel:
    """Gemini 本地模型封装类（基于 mlx_lm）"""

    # 本地 mlx 模型，无远程模型名；各级别使用同一本地模型路径
    # max_tokens 与 temperature 按 LLM 不同在模型内部设置
    MAX_TOKENS = 32000
    TEMPERATURE = 0.7

    def _get_model_by_level(self, level: AEAiLevel) -> str:
        """
        根据 AI 级别选择 Gemini 模型路径（模型内部自行判断）

        Args:
            level: AI 级别

        Returns:
            str: 模型路径
        """
        return self.model_path

    def __init__(self, model_path: str = None):
        """
        初始化 Gemini 模型

        Args:
            model_path: 模型路径，如果不指定则使用默认路径
        """
        self.model_path = model_path or "/Users/tianjunqi/llms/gemini/mlx/E2B"
        self.model = None
        self.tokenizer = None
        self.is_loaded = False
        logger.info(f"🚀 初始化 Gemini 模型 - model_path={self.model_path}")

    def load(self):
        """
        加载 Gemini 模型和 tokenizer（使用 mlx_lm）

        Raises:
            Exception: 加载失败时抛出异常
        """
        if self.is_loaded:
            logger.info("Gemini 模型已加载，跳过重复加载")
            return

        try:
            logger.info(f"🔄 开始加载 Gemini 模型 - path={self.model_path}")

            # 使用 mlx_lm 加载模型和 tokenizer
            self.model, self.tokenizer = load(self.model_path)

            self.is_loaded = True
            logger.info(f"✅ Gemini 模型加载成功 - model_path={self.model_path}")

        except Exception as e:
            logger.error(f"❌ Gemini 模型加载失败: {str(e)}", exc_info=True)
            self.cleanup()
            raise

    def generate(
        self,
        messages: List[Dict[str, str]],
        level: AEAiLevel,
        think_process: Optional[Callable[[Dict[str, Any]], None]] = None,
        delta_process: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> str:
        """
        使用 Gemini 模型生成文本（支持 messages 格式）

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            level: AI 级别（模型名/max_tokens/temperature 由模型内部决定）
            delta_process: 进度回调，整体进度 = 生成累计长度 / max_tokens；
                生成完成后回调一次最终结果（final=True）。为 None 时不回调。

        Returns:
            str: 生成的文本

        Raises:
            Exception: 生成失败时抛出异常
        """
        if not self.is_loaded:
            logger.warning("⚠️ Gemini 模型未加载，正在加载...")
            self.load()

        # max_tokens 与 temperature 由模型内部设置
        max_tokens = self.MAX_TOKENS
        temperature = self.TEMPERATURE

        # 将 system/context 角色消息合并为一条 system 消息（mlx chat template 认 system 角色）
        system_text, chat_messages = split_system_messages(messages)

        logger.info(f"🔄 开始生成文本 - messages_count={len(chat_messages)}, max_tokens={max_tokens}")

        try:
            # 1. 构建完整的 messages（system 在前）
            formatted_messages = []
            if system_text:
                formatted_messages.append({"role": "system", "content": system_text})
            formatted_messages.extend(chat_messages)
            logger.info(f"💬 Messages: {formatted_messages}")

            prompt = self.tokenizer.apply_chat_template(
                formatted_messages,
                tokenize=False,
                add_generation_prompt=True
            )

            logger.info(f"📦 Prompt 已生成 - length={len(prompt)}")

            response = generate(
                self.model,
                self.tokenizer,
                prompt=prompt,
                max_tokens=max_tokens
            )

            # 响应内容由 AEBaseProvider.generate 统一打印，模型层不再输出
            parsed = self.parse_output(text=response.strip())
            # 本地非流式：拿到完整结果后回调一次最终进度（final=True）
            fire_progress(delta_process, parsed["answer"], max_tokens, True)
            return parsed["answer"]

        except Exception as e:
            logger.error(f"❌ Gemini 生成失败: {str(e)}", exc_info=True)
            raise Exception(f"Gemini 生成失败: {str(e)}")


    def parse_output(self, text: str) -> Dict[str, str]:
        """
        解析模型输出，提取思考过程和答案

        Args:
            text: 原始模型输出

        Returns:
            Dict[str, str]: 包含 'think' 和 'answer' 的字典
        """
        text = text.strip()

        start_tag = "<|channel>thought"
        end_tag = "<channel|>"

        think = ""
        answer = text

        # 检查是否包含思考过程标签
        if start_tag in text:
            # 提取 start_tag 之后的内容
            parts = text.split(start_tag, 1)[-1]

            if end_tag in parts:
                # 分离思考过程和答案
                think, answer = parts.split(end_tag, 1)
            else:
                # 只有思考过程，没有答案
                think = parts
                answer = ""
        
        return {
            "think": think.strip(),
            "answer": answer.strip()
        }

    def get_status(self) -> dict:
        """
        获取模型状态

        Returns:
            dict: 包含模型状态信息的字典
        """
        status = {
            "model_path": self.model_path,
            "is_loaded": self.is_loaded,
            "model_type": "gemma-mlx"
        }
        logger.info(f"📊 模型状态: {status}")
        return status

    def cleanup(self):
        """清理模型资源"""
        logger.info("🧹 开始清理 Gemini 模型资源...")

        if self.model is not None:
            del self.model
            self.model = None
            logger.info("✅ 模型已释放")

        if self.tokenizer is not None:
            del self.tokenizer
            self.tokenizer = None
            logger.info("✅ Tokenizer 已释放")

        self.is_loaded = False
        logger.info("✅ Gemini 模型资源已清理")


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
        logger.info("✅ 创建 Gemini 模型单例实例")
    return _gemini_model_instance


def cleanup_gemini_model():
    """清理全局 Gemini 模型实例"""
    global _gemini_model_instance
    if _gemini_model_instance is not None:
        _gemini_model_instance.cleanup()
        _gemini_model_instance = None
        logger.info("✅ 全局 Gemini 模型实例已清理")
