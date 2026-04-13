"""
Gemini 本地模型类
封装 Gemini 模型的加载、生成和资源管理
使用 mlx_lm 库进行模型加载和推理
"""
from typing import Optional, List, Dict, Any
import logging
from mlx_lm import load, generate

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class AEGeminiModel:
    """Gemini 本地模型封装类（基于 mlx_lm）"""

    def __init__(self, model_path: str = None):
        """
        初始化 Gemini 模型

        Args:
            model_path: 模型路径，如果不指定则使用默认路径
        """
        self.model_path = model_path or "/Users/tianjunqi/llms/gemini/mlx/26B-A4B"
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
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system: Optional[str] = None
    ) -> str:
        """
        使用 Gemini 模型生成文本（支持 messages 格式）

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            max_tokens: 最大生成 token 数
            temperature: 温度参数
            system: 系统提示词（可选，会添加到 messages 开头）

        Returns:
            str: 生成的文本

        Raises:
            Exception: 生成失败时抛出异常
        """
        if not self.is_loaded:
            logger.warning("⚠️ Gemini 模型未加载，正在加载...")
            self.load()

        logger.info(f"🔄 开始生成文本 - messages_count={len(messages)}, max_tokens={max_tokens}, system={'是' if system else '否'}")

        try:
            # 1. 构建完整的 messages（如果有 system，添加到开头）
            formatted_messages = []
            if system:
                formatted_messages.append({
                    "role": "system",
                    "content": system
                })
                logger.info(f"📝 添加 system: {system[:100]}...")

            formatted_messages.extend(messages)
            logger.info(f"💬 Messages: {formatted_messages}")

            # 2. 使用 tokenizer 的 chat template 将 messages 转换为 prompt
            prompt = self.tokenizer.apply_chat_template(
                formatted_messages,
                tokenize=False,
                add_generation_prompt=True
            )

            logger.info(f"📦 Prompt 已生成 - length={len(prompt)}")
            logger.info(f"📝 Prompt 内容: {prompt[:200]}...")

            # 3. 调用 mlx_lm 的 generate 函数
            response = generate(
                self.model,
                self.tokenizer,
                prompt=prompt,
                max_tokens=max_tokens
            )

            logger.info(f"✅ 文本生成成功 - response_length={len(response)}")
            logger.info(f"📄 响应内容: {response[:200]}...")

            return response.strip()

        except Exception as e:
            logger.error(f"❌ Gemini 生成失败: {str(e)}", exc_info=True)
            raise Exception(f"Gemini 生成失败: {str(e)}")

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
