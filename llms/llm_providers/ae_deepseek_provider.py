"""
AE DeepSeek Provider - DeepSeek API 提供商
负责组装 DeepSeek API 需要的所有信息

key 与接口访问参照 zhipu_provider：复用同一内部网关与同一 auth_token，
通过 OpenAI 兼容的 /v1/chat/completions 接口访问（附带 X-Model-Provider-Id: tongyi），
模型名替换为 DeepSeek 系列。
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


class AEDeepSeekProvider(AEBaseProvider):
    """DeepSeek API 提供商"""

    def __init__(self):
        super().__init__()
        self.deepseek_model = None

    def load(self):
        """加载 DeepSeek API"""
        if self.is_loaded:
            logger.info(f"{self.name} 已加载，跳过重复加载")
            return

        try:
            # 导入 DeepSeek 模型类
            from llm.deepseek import get_deepseek_model

            logger.info(f"🔄 正在初始化 {self.name}...")
            self.deepseek_model = get_deepseek_model()

            # 加载配置
            self.deepseek_model.load()

            self.is_loaded = True
            logger.info(f"✅ {self.name} 加载成功!")

        except Exception as e:
            logger.error(f"❌ {self.name} 加载失败: {str(e)}", exc_info=True)
            raise

    def _generate(self, question: AEQuestion, level: AEAiLevel) -> str:
        try:
            if not self.is_loaded:
                self.load()

            messages = question.messages

            # 只传 messages 与 level，模型名与 max_tokens 由 AEDeepSeekModel 内部决定
            result = self.deepseek_model.generate(
                messages=messages,
                level=level,
            )

            # 解析响应
            parsed_result = self._parse_response(result)
            return parsed_result

        except Exception as e:
            logger.error(f"❌ DeepSeek API 调用失败: {str(e)}", exc_info=True)
            raise Exception(f"DeepSeek API 调用失败: {str(e)}")

    def _parse_response(self, result) -> str:
        """
        解析 DeepSeek API 响应
        接口访问参照 zhipu_provider，响应格式与 Claude 一致（Anthropic 兼容）

        Args:
            result: API 响应结果

        Returns:
            str: 提取的文本内容
        """
        if isinstance(result, dict):
            # Anthropic 响应: content 是块数组，可能含 thinking（推理）与 text（结果），取 text 块
            if "content" in result:
                content = result["content"]
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                            return block["text"]
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
        if self.deepseek_model:
            status["model_status"] = self.deepseek_model.get_status()
        return status

    def cleanup(self):
        """清理 DeepSeek 资源"""
        if self.deepseek_model is not None:
            self.deepseek_model.cleanup()
            self.deepseek_model = None

        self.is_loaded = False
        print(f"🧹 {self.name} cleaned up")
