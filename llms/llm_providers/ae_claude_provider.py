"""
AE Claude Provider - Claude API 提供商
负责组装 Claude API 需要的所有信息
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


class AEClaudeProvider(AEBaseProvider):
    """Claude API 提供商"""

    def __init__(self):
        super().__init__()
        self.claude_model = None

    def load(self):
        """加载 Claude API"""
        if self.is_loaded:
            logger.info(f"{self.name} 已加载，跳过重复加载")
            return

        try:
            # 导入 Claude 模型类
            from llm.claude import get_claude_model

            logger.info(f"🔄 正在初始化 {self.name}...")
            self.claude_model = get_claude_model()

            # 加载配置
            self.claude_model.load()

            self.is_loaded = True
            logger.info(f"✅ {self.name} 加载成功!")

        except Exception as e:
            logger.error(f"❌ {self.name} 加载失败: {str(e)}", exc_info=True)
            raise

    def generate(self, question: AEQuestion, level: AEAiLevel, max_tokens: int) -> str:
        """
        使用 Claude API 生成回复
        在这里组装 Claude API 需要的所有信息

        Args:
            question: 问题对象（包含 messages、system、tools 等所有参数）
            level: AI 级别
            max_tokens: 最大 token 数

        Returns:
            str: Claude 生成的回复
        """
        logger.info(f"🔄 开始生成 Claude 回复 - level={level.name}, max_tokens={max_tokens}")

        try:
            if not self.is_loaded:
                self.load()

            # 1. 根据 level 选择模型
            model = self._get_model_by_level(level)
            logger.info(f"📦 选择模型 - model={model}, level={level.name}")

            # 2. 从 question 对象中提取所有参数
            messages = question.messages  # 直接使用 messages 列表
            system = question.system  # 系统提示词
            tools = question.tools  # 工具列表

            # 3. 打印调用信息
            logger.info(f"📋 请求参数 - messages_count={len(messages)}, system={'是' if system else '否'}, tools={len(tools) if tools else 0}")
            logger.debug(f"📝 System 内容: {system[:200] if system else None}...")
            logger.debug(f"💬 Messages: {messages}")

            # 4. 调用 Claude API - 传递完整参数
            result = self.claude_model.generate(
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=0.0,
                system=system,  # 传递系统提示词
                tools=tools  # 传递工具列表
            )

            # 5. 解析响应
            parsed_result = self._parse_response(result)
            logger.info(f"✅ Claude 回复生成成功 - response_length={len(parsed_result) if parsed_result else 0}")
            return parsed_result

        except Exception as e:
            logger.error(f"❌ Claude API 调用失败: {str(e)}", exc_info=True)
            raise Exception(f"Claude API 调用失败: {str(e)}")

    def _get_model_by_level(self, level: AEAiLevel) -> str:
        """
        根据 AI 级别选择 Claude 模型

        Args:
            level: AI 级别

        Returns:
            str: 模型名称
        """
        model_map = {
            AEAiLevel.default: "ppio/pa/claude-haiku-4-5-20251001",
            AEAiLevel.middle: "ppio/pa/claude-sonnet-4-5-20250929",
            AEAiLevel.high: "ppio/pa/claude-opus-4-6"
        }
        return model_map.get(level, "ppio/pa/claude-haiku-4-5-20251001")

    def _parse_response(self, result) -> str:
        """
        解析 Claude API 响应

        Args:
            result: API 响应结果

        Returns:
            str: 提取的文本内容
        """
        if isinstance(result, dict):
            # Claude API 标准响应格式: {"content": [{"type": "text", "text": "..."}]}
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
        if self.claude_model:
            status["model_status"] = self.claude_model.get_status()
        return status

    def cleanup(self):
        """清理 Claude 资源"""
        if self.claude_model is not None:
            self.claude_model.cleanup()
            self.claude_model = None

        self.is_loaded = False
        print(f"🧹 {self.name} cleaned up")

