"""
GPT API 模型类
封装 GPT API 的调用、配置和资源管理
"""
import requests
import json
import logging
from typing import Optional, List, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
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
        logger.info(f"初始化 GPT 模型 - base_url={self.base_url}")

    def load(self):
        if self.is_loaded:
            logger.info("GPT API 已配置，跳过重复加载")
            return

        try:
            logger.info("开始加载 GPT API 配置...")
            if not self.base_url:
                raise ValueError("base_url 不能为空")
            if not self.auth_token:
                raise ValueError("auth_token 不能为空")

            self.is_loaded = True
            logger.info(f"GPT API 配置成功 - base_url={self.base_url}")

        except Exception as e:
            logger.error(f"GPT API 配置失败: {str(e)}", exc_info=True)
            self.cleanup()
            raise

    def generate(
        self,
        model: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        使用 GPT API 生成文本

        Args:
            model: 模型名称
            messages: 消息列表 [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
            max_tokens: 最大 token 数
            temperature: 温度参数
            tools: 工具列表（可选）

        Returns:
            dict: API 响应结果
        """
        if not self.is_loaded:
            self.load()

        logger.info(f"开始调用 GPT API - model={model}, max_tokens={max_tokens}, messages_count={len(messages)}")
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
                "temperature": temperature,
            }

            if tools:
                payload["tools"] = tools
                logger.debug(f"添加 {len(tools)} 个 tools")

            logger.info(f"发送请求到 GPT API - url={url}")

            response = requests.post(url, headers=headers, json=payload, timeout=60)

            elapsed = (datetime.now() - start_time).total_seconds()

            if response.status_code == 200:
                result = response.json()
                logger.info(f"GPT API 调用成功 - elapsed={elapsed:.2f}s, status=200")
                return result
            else:
                error_msg = f"请求失败: {response.status_code}"
                logger.error(f"GPT API 调用失败 - elapsed={elapsed:.2f}s, status={response.status_code}, error={response.text[:200]}")
                return error_msg

        except requests.exceptions.Timeout as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"GPT API 请求超时 - elapsed={elapsed:.2f}s", exc_info=True)
            return f"请求超时: {str(e)}"
        except requests.exceptions.ConnectionError as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"GPT API 连接错误 - elapsed={elapsed:.2f}s, url={url}", exc_info=True)
            return f"连接错误: {str(e)}"
        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"GPT API 请求异常 - elapsed={elapsed:.2f}s, error={str(e)}", exc_info=True)
            return f"请求异常: {e}"

    def get_status(self) -> dict:
        return {
            "base_url": self.base_url,
            "is_loaded": self.is_loaded,
            "api_type": "gpt"
        }

    def cleanup(self):
        self.is_loaded = False
        logger.info("GPT API 资源已清理")


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
    tools: list = None,
    max_tokens: int = 4096,
    temperature: float = 0.0
):
    gpt_model = get_gpt_model()
    return gpt_model.generate(
        model=model,
        messages=messages,
        tools=tools,
        max_tokens=max_tokens,
        temperature=temperature
    )
