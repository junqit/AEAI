"""
AE Qwen Provider - Qwen (通义千问) API 提供商
负责组装 Qwen API 需要的所有信息
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


class AEQwenProvider(AEBaseProvider):
    """Qwen API 提供商"""

    def __init__(self):
        super().__init__()
        self.qwen_model = None

    def load(self):
        """加载 Qwen API"""
        if self.is_loaded:
            logger.info(f"{self.name} 已加载，跳过重复加载")
            return

        try:
            # 导入 Qwen 模型类
            from llm.qwen import get_qwen_model

            logger.info(f"🔄 正在初始化 {self.name}...")
            self.qwen_model = get_qwen_model()

            # 加载配置
            self.qwen_model.load()

            self.is_loaded = True
            logger.info(f"✅ {self.name} 加载成功!")

        except Exception as e:
            logger.error(f"❌ {self.name} 加载失败：{str(e)}", exc_info=True)
            raise

    def _generate(self, question: AEQuestion,
                  think_process: Optional[Callable[[Dict[str, Any]], None]] = None,
                  delta_process: Optional[Callable[[Dict[str, Any]], None]] = None) -> str:
        try:
            if not self.is_loaded:
                self.load()

            messages = question.messages

            # 只传 messages 与 level，max_tokens 由 AEQwenModel 内部决定
            result = self.qwen_model.generate(
                messages=messages,
                level=question.level,
                think_process=think_process,
                delta_process=delta_process,
            )

            # 解析响应
            parsed_result = self._parse_response(result)
            return parsed_result

        except Exception as e:
            logger.error(f"❌ Qwen API 调用失败：{str(e)}", exc_info=True)
            raise Exception(f"Qwen API 调用失败：{str(e)}")

    def _parse_response(self, result) -> str:
        """
        解析 Qwen API 响应

        Args:
            result: API 响应结果

        Returns:
            str: 提取的文本内容
        """
        if isinstance(result, dict):
            # 模型层以 {"error": ...} 标记失败（413 / 超时 / 连接错误等），先判错再解析内容，
            # 否则错误体里的 "response" 字段会被下方 "response" 分支误当成功结果返回。
            if "error" in result:
                raise Exception(result["error"])
            # OpenAI 兼容格式：choices[0].message.content
            if "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    return choice["message"]["content"]
            # 备选格式：content 字段
            if "content" in result:
                content = result["content"]
                if isinstance(content, list):
                    return str(content)
                return str(content)
            elif "text" in result:
                return result["text"]
            elif "response" in result:
                return result["response"]
            else:
                return str(result)
        elif isinstance(result, str):
            # 如果返回的是字符串，检查是否是错误消息
            if result.startswith("请求失败") or result.startswith("请求异常"):
                raise Exception(result)
            return result
        else:
            return str(result)

    def get_status(self) -> dict:
        """获取提供商状态"""
        status = super().get_status()
        status["model"] = self.model_path
        status["base_url"] = self.base_url
        return status

    def cleanup(self):
        """清理 Qwen 资源"""
        # Qwen 本地 API 不需要特殊清理
        self.is_loaded = False
        logger.info(f"🧹 {self.name} cleaned up")
