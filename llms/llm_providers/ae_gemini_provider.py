"""
AE Gemini Provider - Google Gemini 本地模型提供商
负责组装 Gemini 模型需要的所有信息
"""
import sys
import logging
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Optional, Callable, Dict, Any
from .ae_base_provider import AEBaseProvider
from AEQuestion import AEQuestion

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

    def _generate(self, question: AEQuestion,
                  think_process: Optional[Callable[[Dict[str, Any]], None]] = None,
                  delta_process: Optional[Callable[[Dict[str, Any]], None]] = None) -> str:
        try:
            if not self.is_loaded:
                self.load()

            messages = question.messages

            # 只传 messages 与 level，模型名/max_tokens/temperature 由 AEGeminiModel 内部决定
            response = self.gemini_model.generate(
                messages=messages,
                level=question.level,
                think_process=think_process,
                delta_process=delta_process,
            )

            # 4. 验证响应是否有效
            if not response or response.strip() == "":
                logger.warning("⚠️ Gemini 模型未返回有效响应")
                return "Gemini 模型未返回有效响应"

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
