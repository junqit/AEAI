"""
GPT API 模型类
封装 GPT API 的调用、配置和资源管理
"""
import re
import requests
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class AEGPTModel:
    """GPT API 模型封装类"""

    MODEL = "ppio/pa/gpt-5.5"
    BASE_URL = "http://model.mify.ai.srv/anthropic"
    AUTH_TOKEN = "sk-psTx7IFlW79l67Or8JqLsBL0CqCtkhVlHoOMfRMts1Ugkdiu"

    def __init__(self):
        self.base_url = self.BASE_URL
        self.auth_token = self.AUTH_TOKEN
        self.is_loaded = False

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
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 128000,
    ) -> Dict[str, Any]:
        if not self.is_loaded:
            self.load()

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

            response = requests.post(url, headers=headers, json=payload, timeout=99999999)

            elapsed = (datetime.now() - start_time).total_seconds()

            if response.status_code == 200:
                result = response.json()
                self._strip_thinking(result)
                logger.info(f"GPT API 调用成功 - model={model}, elapsed={elapsed:.2f}s")
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


def call_gpt_api(
    model: str,
    messages: list,
    max_tokens: int = 128000,
):
    gpt_model = get_gpt_model()
    return gpt_model.generate(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
    )
