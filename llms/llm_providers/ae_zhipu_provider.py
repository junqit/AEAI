"""
AE Zhipu Provider - 智谱 Zhipu API 提供商
负责组装 Zhipu API 需要的所有信息

key 与接口访问参照 claude_provider：复用同一内部网关与同一 auth_token，
模型名替换为智谱 GLM 系列。
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


class AEZhipuProvider(AEBaseProvider):
    """Zhipu (智谱) API 提供商"""

    def __init__(self):
        super().__init__()
        self.zhipu_model = None

    def load(self):
        """加载 Zhipu API"""
        if self.is_loaded:
            logger.info(f"{self.name} 已加载，跳过重复加载")
            return

        try:
            # 导入 Zhipu 模型类
            from llm.zhipu import get_zhipu_model

            logger.info(f"🔄 正在初始化 {self.name}...")
            self.zhipu_model = get_zhipu_model()

            # 加载配置
            self.zhipu_model.load()

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

            # 只传 messages 与 level，模型名与 max_tokens 由 AEZhipuModel 内部决定
            result = self.zhipu_model.generate(
                messages=messages,
                level=level,
            )

            # 解析响应
            parsed_result = self._parse_response(result)
            logger.info(f"✅ Zhipu 回复生成成功 - response_length={len(parsed_result) if parsed_result else 0}")
            return parsed_result

        except Exception as e:
            logger.error(f"❌ Zhipu API 调用失败: {str(e)}", exc_info=True)
            raise Exception(f"Zhipu API 调用失败: {str(e)}")

    def _parse_response(self, result) -> str:
        """
        解析 Zhipu API 响应
        接口访问参照 claude_provider，响应格式与 Claude 一致（Anthropic 兼容）

        Args:
            result: API 响应结果

        Returns:
            str: 提取的文本内容
        """
        if isinstance(result, dict):
            # Claude/Anthropic API 标准响应格式: {"content": [{"type": "text", "text": "..."}]}
            if "content" in result:
                content = result["content"]
                if isinstance(content, list) and len(content) > 0:
                    if isinstance(content[0], dict) and "text" in content[0]:
                        return content[0]["text"]
                    else:
                        return str(content[0])
                else:
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
        if self.zhipu_model:
            status["model_status"] = self.zhipu_model.get_status()
        return status

    def cleanup(self):
        """清理 Zhipu 资源"""
        if self.zhipu_model is not None:
            self.zhipu_model.cleanup()
            self.zhipu_model = None

        self.is_loaded = False
        print(f"🧹 {self.name} cleaned up")
