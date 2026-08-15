"""
GPT API 模型类
封装 GPT API 的调用、配置和资源管理
"""
import re
import requests
import logging
from typing import Optional, List, Dict, Any, Callable

from AEAiLevel import AEAiLevel
from common.llm_utils import split_system_messages, extract_message_text, fire_progress

logger = logging.getLogger(__name__)


class AEGPTModel:
    """GPT API 模型封装类"""

    # AI 级别 → 模型名映射，由模型内部自行判断
    MODEL_MAP = {
        AEAiLevel.default: "ppio/pa/gpt-5.6-sol",
        AEAiLevel.middle: "ppio/pa/gpt-5.6-sol",
        AEAiLevel.high: "ppio/pa/gpt-5.6-sol",
    }
    DEFAULT_MODEL = "ppio/pa/gpt-5.6-sol"
    # 模型上下文窗口（输入与输出合计）
    CONTEXT_WINDOW = 1_000_000
    # 为输入上下文预留空间后的单次输出上限
    MAX_TOKENS = 128_000

    BASE_URL = "http://model.mify.ai.srv/anthropic"
    AUTH_TOKEN = "sk-psTx7IFlW79l67Or8JqLsBL0CqCtkhVlHoOMfRMts1Ugkdiu"

    def __init__(self):
        self.base_url = self.BASE_URL
        self.auth_token = self.AUTH_TOKEN
        self.is_loaded = False

    def _get_model_by_level(self, level: AEAiLevel) -> str:
        """
        根据 AI 级别选择 GPT 模型名（模型内部自行判断）

        Args:
            level: AI 级别

        Returns:
            str: 模型名称
        """
        return self.MODEL_MAP.get(level, self.DEFAULT_MODEL)

    def load(self):
        if self.is_loaded:
            return

        if not self.base_url or not self.auth_token:
            logger.error("GPT API 配置失败: base_url 或 auth_token 为空")
            raise ValueError("base_url 或 auth_token 不能为空")

        self.is_loaded = True
        logger.info("GPT API 加载成功")

    def generate(
        self,
        messages: List[Dict[str, str]],
        level: AEAiLevel,
        think_process: Optional[Callable[[Dict[str, Any]], None]] = None,
        delta_process: Optional[Callable[[Dict[str, Any]], None]] = None,
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
                "messages": messages,
                "max_tokens": max_tokens,
            }
            if system_text:
                payload["system"] = system_text

            response = requests.post(url, headers=headers, json=payload, timeout=99999999)

            elapsed = (datetime.now() - start_time).total_seconds()

            if response.status_code == 200:
                result = response.json()
                self._strip_thinking(result)
                logger.info(f"GPT API 调用成功 - model={model}, elapsed={elapsed:.2f}s")
                # 非流式：拿到完整结果后回调一次最终进度（final=True）
                fire_progress(
                    delta_process, extract_message_text(result), max_tokens, True
                )
                return result
            else:
                logger.error(f"GPT API 调用失败 - model={model}, status={response.status_code}, error={response.text[:200]}")
                return f"请求失败: {response.status_code}"

        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"GPT API 请求异常 - model={model}, elapsed={elapsed:.2f}s, error={str(e)}")
            return f"请求异常: {e}"

    @staticmethod
    def _strip_thinking(result: dict):
        content = result.get("content", [])
        for item in content:
            if item.get("type") == "text" and item.get("text"):
                item["text"] = re.sub(r"<think>.*?</think>\s*", "", item["text"], flags=re.DOTALL)

    def get_status(self) -> dict:
        return {
            "base_url": self.base_url,
            "is_loaded": self.is_loaded,
            "api_type": "gpt"
        }

    def cleanup(self):
        self.is_loaded = False


_gpt_model_instance: Optional[AEGPTModel] = None


def get_gpt_model() -> AEGPTModel:
    global _gpt_model_instance
    if _gpt_model_instance is None:
        _gpt_model_instance = AEGPTModel()
    return _gpt_model_instance


def cleanup_gpt_model():
    global _gpt_model_instance
    if _gpt_model_instance is not None:
        _gpt_model_instance.cleanup()
        _gpt_model_instance = None
