"""
AE Gemini Provider - Google Gemini 本地模型提供商
负责组装 Gemini 模型需要的所有信息
"""
import sys
import logging
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from .ae_base_provider import AEBaseProvider
from AEQuestion import AEQuestion
from AEAiLevel import AEAiLevel

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class AEGeminiProvider(AEBaseProvider):
    """Gemini 本地模型提供商"""

    def __init__(self):
        super().__init__()
        self.gemini_model = None

    def load(self):
        """加载 Gemini 本地模型"""
        if self.is_loaded:
            logger.info(f"{self.name} 已加载，跳过重复加载")
            return

        try:
            # 导入 Gemini 模型类
            from llm.gemini.gemini_model import get_gemini_model

            logger.info(f"🔄 正在初始化 {self.name}...")
            self.gemini_model = get_gemini_model()

            # 加载模型
            self.gemini_model.load()

            self.is_loaded = True
            logger.info(f"✅ {self.name} 加载成功!")

        except Exception as e:
            logger.error(f"❌ {self.name} 加载失败: {str(e)}", exc_info=True)
            raise

    def generate(self, question: AEQuestion, level: AEAiLevel, max_tokens: int) -> str:
        """
        使用 Gemini 本地模型生成回复
        在这里组装 Gemini 模型需要的所有信息

        Args:
            question: 问题对象（包含 messages、system、tools 等所有参数）
            level: AI 级别
            max_tokens: 最大 token 数

        Returns:
            str: Gemini 生成的回复
        """
        logger.info(f"🔄 开始生成 Gemini 回复 - level={level.name}, max_tokens={max_tokens}")

        try:
            # 确保模型已加载
            if not self.is_loaded:
                self.load()

            # 1. 从 question 对象中提取参数
            messages = question.messages  # 消息列表
            system = question.system  # 系统提示词

            # 2. 打印调用信息
            logger.info(f"📋 请求参数 - messages_count={len(messages)}, system={'是' if system else '否'}")
            logger.debug(f"📝 System 内容: {system[:200] if system else None}...")
            logger.debug(f"💬 Messages: {messages}")

            # 3. 调用 Gemini 模型 - 传递 messages 和 system
            response = self.gemini_model.generate(
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7,
                system=system
            )

            # 4. 验证响应是否有效
            if not response or response.strip() == "":
                logger.warning("⚠️ Gemini 模型未返回有效响应")
                return "Gemini 模型未返回有效响应"

            logger.info(f"✅ Gemini 回复生成成功 - response_length={len(response)}")
            return response

        except Exception as e:
            logger.error(f"❌ Gemini 本地模型调用失败: {str(e)}", exc_info=True)
            raise Exception(f"Gemini 本地模型调用失败: {str(e)}")

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
        logger.info(f"🧹 {self.name} 已清理")
