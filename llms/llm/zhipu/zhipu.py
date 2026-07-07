"""
Zhipu (智谱) API 模型类
封装 Zhipu API 的调用、配置和资源管理

key 与接口访问参照 claude_provider：复用同一内部网关与同一 auth_token，
通过 Anthropic 兼容的 /v1/messages 接口访问，仅模型名替换为智谱 GLM 系列。
"""
import requests
import json
import time
import logging
from typing import Optional, List, Dict, Any

from AEAiLevel import AEAiLevel
from common.llm_utils import split_system_messages

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class AEZhipuModel:
    """Zhipu (智谱) API 模型封装类"""

    # AI 级别 → 模型名映射，由模型内部自行判断
    # 模型名遵循内部网关命名约定，智谱 GLM 统一使用 zhipuai/glm-5.2
    MODEL_MAP = {
        AEAiLevel.default: "zhipuai/glm-5.2",
        AEAiLevel.middle: "zhipuai/glm-5.2",
        AEAiLevel.high: "zhipuai/glm-5.2",
    }
    DEFAULT_MODEL = "zhipuai/glm-5.2"
    # max_tokens 按 LLM 不同在模型内部设置
    MAX_TOKENS = 128000

    def __init__(self, base_url: str = None, auth_token: str = None):
        """
        初始化 Zhipu 模型

        Args:
            base_url: API 基础 URL（与 Claude 共用同一内部网关）
            auth_token: 认证 token（与 Claude 共用同一 key）
        """
        self.base_url = base_url or "http://model.mify.ai.srv/anthropic"
        self.auth_token = auth_token or "sk-psTx7IFlW79l67Or8JqLsBL0CqCtkhVlHoOMfRMts1Ugkdiu"
        self.is_loaded = False
        logger.info(f"🚀 初始化 Zhipu 模型 - base_url={self.base_url}")

    def _get_model_by_level(self, level: AEAiLevel) -> str:
        """
        根据 AI 级别选择 Zhipu 模型名（模型内部自行判断）

        Args:
            level: AI 级别

        Returns:
            str: 模型名称
        """
        return self.MODEL_MAP.get(level, self.DEFAULT_MODEL)

    def load(self):
        """
        加载 Zhipu API 配置

        Raises:
            Exception: 配置验证失败时抛出异常
        """
        if self.is_loaded:
            logger.info("Zhipu API 已配置，跳过重复加载")
            return

        try:
            logger.info("🔄 开始加载 Zhipu API 配置...")
            # 验证配置
            if not self.base_url:
                raise ValueError("base_url 不能为空")
            if not self.auth_token:
                raise ValueError("auth_token 不能为空")

            self.is_loaded = True
            logger.info(f"✅ Zhipu API 配置成功 - base_url={self.base_url}")

        except Exception as e:
            logger.error(f"❌ Zhipu API 配置失败: {str(e)}", exc_info=True)
            self.cleanup()
            raise

    def generate(
        self,
        messages: List[Dict[str, str]],
        level: AEAiLevel,
    ) -> Dict[str, Any]:
        if not self.is_loaded:
            self.load()

        # 模型名与 max_tokens 均由模型内部根据 level 自行决定
        model = self._get_model_by_level(level)
        max_tokens = self.MAX_TOKENS

        # 将 system/context 角色消息提取为顶层 system，避免出现连续 user 消息
        system_text, messages = split_system_messages(messages)

        from datetime import datetime
        start_time = datetime.now()

        try:
            url = f"{self.base_url}/v1/messages"

            headers = {
                "x-api-key": self.auth_token,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }

            payload = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages
            }
            if system_text:
                payload["system"] = system_text

            # 结构性打印 payload 数据
            logger.info(
                "📤 Zhipu 发送 payload:\n%s",
                json.dumps(payload, ensure_ascii=False, indent=2),
            )

            # 失败一直重试（429 限流 / 5xx / 网络异常等），直到成功
            backoff = 1.0
            attempt = 0
            while True:
                attempt += 1
                try:
                    response = requests.post(url, headers=headers, json=payload, timeout=60)
                    elapsed = (datetime.now() - start_time).total_seconds()

                    if response.status_code == 200:
                        result = response.json()
                        logger.info(f"✅ Zhipu API 调用成功 - model={model}, elapsed={elapsed:.2f}s, status=200, attempt={attempt}")
                        logger.debug(f"📄 响应内容: {str(result)[:500]}...")
                        return result

                    logger.warning(
                        "⚠️ Zhipu 调用失败将重试 - status=%s, attempt=%d, %.1fs 后重试, error=%s",
                        response.status_code, attempt, backoff, response.text[:200],
                    )
                except requests.exceptions.Timeout as e:
                    logger.warning("⚠️ Zhipu 请求超时将重试 - attempt=%d, %.1fs 后重试: %s", attempt, backoff, e)
                except requests.exceptions.ConnectionError as e:
                    logger.warning("⚠️ Zhipu 连接错误将重试 - attempt=%d, %.1fs 后重试: %s", attempt, backoff, e)
                except Exception as e:
                    logger.warning("⚠️ Zhipu 请求异常将重试 - attempt=%d, %.1fs 后重试: %s", attempt, backoff, e)

                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

        except requests.exceptions.Timeout as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ Zhipu API 请求超时 - elapsed={elapsed:.2f}s", exc_info=True)
            return f"请求超时: {str(e)}"
        except requests.exceptions.ConnectionError as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ Zhipu API 连接错误 - elapsed={elapsed:.2f}s, url={url}", exc_info=True)
            return f"连接错误: {str(e)}"
        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ Zhipu API 请求异常 - elapsed={elapsed:.2f}s, error={str(e)}", exc_info=True)
            return f"请求异常: {e}"

    def get_status(self) -> dict:
        """
        获取模型状态

        Returns:
            dict: 包含模型状态信息的字典
        """
        return {
            "base_url": self.base_url,
            "is_loaded": self.is_loaded,
            "api_type": "zhipu"
        }

    def cleanup(self):
        """清理资源"""
        self.is_loaded = False
        print("🧹 Zhipu API 资源已清理")


# 全局单例实例
_zhipu_model_instance: Optional[AEZhipuModel] = None


def get_zhipu_model(base_url: str = None, auth_token: str = None) -> AEZhipuModel:
    """
    获取 Zhipu 模型单例实例

    Args:
        base_url: API 基础 URL（仅首次调用时有效）
        auth_token: 认证 token（仅首次调用时有效）

    Returns:
        AEZhipuModel: Zhipu 模型实例
    """
    global _zhipu_model_instance
    if _zhipu_model_instance is None:
        _zhipu_model_instance = AEZhipuModel(base_url, auth_token)
    return _zhipu_model_instance


def cleanup_zhipu_model():
    """清理全局 Zhipu 模型实例"""
    global _zhipu_model_instance
    if _zhipu_model_instance is not None:
        _zhipu_model_instance.cleanup()
        _zhipu_model_instance = None


# ==================== 向后兼容的函数 ====================
# 保留 call_zhipu_api 函数以保持与其他模型一致的调用风格

def call_zhipu_api(
    messages: list,
    level: AEAiLevel,
):
    zhipu_model = get_zhipu_model()
    return zhipu_model.generate(
        messages=messages,
        level=level,
    )
