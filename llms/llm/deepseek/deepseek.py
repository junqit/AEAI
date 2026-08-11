"""
DeepSeek API 模型类
封装 DeepSeek API 的调用、配置和资源管理

与 claude/zhipu/gpt 一致，走内部网关 Anthropic 兼容的 /v1/messages 接口
（同样的域名同样的地址），仅模型名替换为 deepseek-v4-pro，并附带
X-Model-Provider-Id: tongyi 头指定网关后端供应商。
"""
import requests
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


class AEDeepSeekModel:
    """DeepSeek API 模型封装类"""

    # AI 级别 → 模型名映射，由模型内部自行判断
    # 内部网关 DeepSeek 统一使用 deepseek-v4-pro
    MODEL_MAP = {
        AEAiLevel.default: "deepseek-v4-pro",
        AEAiLevel.middle: "deepseek-v4-pro",
        AEAiLevel.high: "deepseek-v4-pro",
    }
    DEFAULT_MODEL = "deepseek-v4-pro"
    # 单次输出上限，DeepSeek-v4-pro 仅提供 1M（1_000_000）一档
    MAX_TOKENS = 1_000_000

    def __init__(self, base_url: str = None, auth_token: str = None):
        """
        初始化 DeepSeek 模型

        Args:
            base_url: API 基础 URL（与 Claude/Zhipu 共用同一内部网关入口）
            auth_token: 认证 token（与 Claude/Zhipu 共用同一 key）
        """
        self.base_url = base_url or "http://model.mify.ai.srv/anthropic"
        self.auth_token = auth_token or "sk-psTx7IFlW79l67Or8JqLsBL0CqCtkhVlHoOMfRMts1Ugkdiu"
        self.is_loaded = False
        logger.info(f"🚀 初始化 DeepSeek 模型 - base_url={self.base_url}")

    def _get_model_by_level(self, level: AEAiLevel) -> str:
        """
        根据 AI 级别选择 DeepSeek 模型名（模型内部自行判断）

        Args:
            level: AI 级别

        Returns:
            str: 模型名称
        """
        return self.MODEL_MAP.get(level, self.DEFAULT_MODEL)

    def load(self):
        """
        加载 DeepSeek API 配置

        Raises:
            Exception: 配置验证失败时抛出异常
        """
        if self.is_loaded:
            logger.info("DeepSeek API 已配置，跳过重复加载")
            return

        try:
            logger.info("🔄 开始加载 DeepSeek API 配置...")
            # 验证配置
            if not self.base_url:
                raise ValueError("base_url 不能为空")
            if not self.auth_token:
                raise ValueError("auth_token 不能为空")

            self.is_loaded = True
            logger.info(f"✅ DeepSeek API 配置成功 - base_url={self.base_url}")

        except Exception as e:
            logger.error(f"❌ DeepSeek API 配置失败: {str(e)}", exc_info=True)
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
        system_text, chat_messages = split_system_messages(messages)

        from datetime import datetime
        start_time = datetime.now()

        url = f"{self.base_url}/v1/messages"

        # Anthropic 兼容入口使用 x-api-key；X-Model-Provider-Id 指定网关后端供应商
        headers = {
            "x-api-key": self.auth_token,
            "anthropic-version": "2023-06-01",
            "X-Model-Provider-Id": "tongyi",
            "content-type": "application/json"
        }

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": chat_messages
        }
        if system_text:
            payload["system"] = system_text

        # 请求/响应内容由 AEBaseProvider.generate 统一打印，模型层不再输出

        # 最多重试 10 次（429 限流 / 5xx / 网络异常等），全部失败则返回失败
        MAX_RETRY = 10
        backoff = 1.0
        last_error = "未知错误"
        for attempt in range(1, MAX_RETRY + 1):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=60)
                elapsed = (datetime.now() - start_time).total_seconds()

                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"✅ DeepSeek API 调用成功 - model={model}, elapsed={elapsed:.2f}s, status=200, attempt={attempt}")
                    return result

                last_error = f"status={response.status_code}, error={response.text[:200]}"
                # 4xx 客户端错误（除 429 限流外）不可重试——请求体过大(413)/参数错误(400)等，重试无意义
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    logger.error(
                        "❌ DeepSeek API 不可重试的客户端错误 - status=%s, error=%s",
                        response.status_code, response.text[:200],
                    )
                    return f"请求失败（不可重试）: {last_error}"
                logger.warning(
                    "⚠️ DeepSeek 调用失败将重试 - status=%s, attempt=%d/%d, %.1fs 后重试, error=%s",
                    response.status_code, attempt, MAX_RETRY, backoff, response.text[:200],
                )
            except requests.exceptions.Timeout as e:
                last_error = f"请求超时: {e}"
                logger.warning("⚠️ DeepSeek 请求超时将重试 - attempt=%d/%d, %.1fs 后重试: %s", attempt, MAX_RETRY, backoff, e)
            except requests.exceptions.ConnectionError as e:
                last_error = f"连接错误: {e}"
                logger.warning("⚠️ DeepSeek 连接错误将重试 - attempt=%d/%d, %.1fs 后重试: %s", attempt, MAX_RETRY, backoff, e)
            except Exception as e:
                last_error = f"请求异常: {e}"
                logger.warning("⚠️ DeepSeek 请求异常将重试 - attempt=%d/%d, %.1fs 后重试: %s", attempt, MAX_RETRY, backoff, e)

            if attempt < MAX_RETRY:
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.error(f"❌ DeepSeek API 重试 {MAX_RETRY} 次仍失败 - elapsed={elapsed:.2f}s, last_error={last_error}")
        return f"请求失败（重试 {MAX_RETRY} 次）: {last_error}"

    def get_status(self) -> dict:
        """
        获取模型状态

        Returns:
            dict: 包含模型状态信息的字典
        """
        return {
            "base_url": self.base_url,
            "is_loaded": self.is_loaded,
            "api_type": "deepseek"
        }

    def cleanup(self):
        """清理资源"""
        self.is_loaded = False
        print("🧹 DeepSeek API 资源已清理")


# 全局单例实例
_deepseek_model_instance: Optional[AEDeepSeekModel] = None


def get_deepseek_model(base_url: str = None, auth_token: str = None) -> AEDeepSeekModel:
    """
    获取 DeepSeek 模型单例实例

    Args:
        base_url: API 基础 URL（仅首次调用时有效）
        auth_token: 认证 token（仅首次调用时有效）

    Returns:
        AEDeepSeekModel: DeepSeek 模型实例
    """
    global _deepseek_model_instance
    if _deepseek_model_instance is None:
        _deepseek_model_instance = AEDeepSeekModel(base_url, auth_token)
    return _deepseek_model_instance


def cleanup_deepseek_model():
    """清理全局 DeepSeek 模型实例"""
    global _deepseek_model_instance
    if _deepseek_model_instance is not None:
        _deepseek_model_instance.cleanup()
        _deepseek_model_instance = None


# ==================== 向后兼容的函数 ====================
# 保留 call_deepseek_api 函数以保持与其他模型一致的调用风格

def call_deepseek_api(
    messages: list,
    level: AEAiLevel,
):
    deepseek_model = get_deepseek_model()
    return deepseek_model.generate(
        messages=messages,
        level=level,
    )
