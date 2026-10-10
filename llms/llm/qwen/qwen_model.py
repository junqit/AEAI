"""
Qwen API 模型类
封装 Qwen API 的调用、配置和资源管理
"""
import requests
import logging
from typing import Optional, List, Dict, Any, Callable
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from AEAiLevel import AEAiLevel
from common.llm_utils import extract_message_text, fire_progress

logger = logging.getLogger(__name__)


class AEQwenModel:
    """Qwen API 模型封装类"""

    # 模型路径（本地部署模型）
    MODEL_PATH = "/Users/worker/Downloads/Qwen3.5-122B-A10B-4bit"
    DEFAULT_BASE_URL = "http://10.192.186.141:10000/v1/chat/completions"
    DEFAULT_API_KEY = "asdf"
    DEFAULT_MAX_TOKENS = 262144
    REQUEST_TIMEOUT = 600  # 请求超时时间（秒，10 分钟）
    # (connect, read)：连接 10s 超时（"No route to host" 实际瞬时失败），读 600s 等模型生成
    REQUEST_TIMEOUTS = (10, REQUEST_TIMEOUT)

    # 瞬态错误重试：VPN 隧道抖动 / 路由瞬断（Errno 65 No route to host）/ 5xx / 限流时自动重试，
    # 避免单次 requests.post 碰上瞬时网络抖动即整请求失败。
    # urllib3 默认不重试 POST（视为非幂等），故显式 allowed_methods 含 POST——
    # "No route to host" 时连接未建立、服务端未收到请求，重试安全。
    RETRY_TOTAL = 3
    RETRY_BACKOFF_FACTOR = 1  # 退避间隔：1s、2s、4s
    RETRY_STATUS_FORCELIST = (429, 500, 502, 503, 504)
    RETRY_ALLOWED_METHODS = frozenset(["GET", "POST"])

    def __init__(self, base_url: str = None, api_key: str = None, model_path: str = None, max_tokens: int = None):
        """
        初始化 Qwen 模型

        Args:
            base_url: API 基础 URL
            api_key: API 密钥
            model_path: 模型路径
            max_tokens: 最大生成 token 数
        """
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.api_key = api_key or self.DEFAULT_API_KEY
        self.model_path = model_path or self.MODEL_PATH
        self.max_tokens = max_tokens or self.DEFAULT_MAX_TOKENS
        self.is_loaded = False
        self.session: Optional[requests.Session] = self._build_session()

        logger.info(f"🚀 初始化 Qwen 模型 - base_url={self.base_url}, model={self.model_path}")

    def _build_session(self) -> requests.Session:
        """构建带瞬态错误重试的 requests Session"""
        retry = Retry(
            total=self.RETRY_TOTAL,
            backoff_factor=self.RETRY_BACKOFF_FACTOR,
            status_forcelist=self.RETRY_STATUS_FORCELIST,
            allowed_methods=self.RETRY_ALLOWED_METHODS,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def load(self):
        """
        加载 Qwen API 配置

        Raises:
            Exception: 配置验证失败时抛出异常
        """
        if self.is_loaded:
            logger.info("Qwen API 已配置，跳过重复加载")
            return

        try:
            # cleanup 后重建 session
            if self.session is None:
                self.session = self._build_session()
            # 允许通过环境变量覆盖配置
            import os
            if os.getenv("QWEN_API_URL"):
                self.base_url = os.getenv("QWEN_API_URL")
            if os.getenv("QWEN_API_KEY"):
                self.api_key = os.getenv("QWEN_API_KEY")
            if os.getenv("QWEN_MODEL_PATH"):
                self.model_path = os.getenv("QWEN_MODEL_PATH")
            if os.getenv("QWEN_MAX_TOKENS"):
                self.max_tokens = int(os.getenv("QWEN_MAX_TOKENS"))

            # 验证配置
            if not self.base_url:
                raise ValueError("base_url 不能为空")
            if not self.model_path:
                raise ValueError("model_path 不能为空")

            self.is_loaded = True
            logger.info(f"✅ Qwen API 配置成功 - base_url={self.base_url}, model={self.model_path}")

        except Exception as e:
            logger.error(f"❌ Qwen API 配置失败：{str(e)}", exc_info=True)
            self.cleanup()
            raise

    def generate(
        self,
        messages: List[Dict[str, str]],
        level: AEAiLevel = None,
        think_process: Optional[Callable[[Dict[str, Any]], None]] = None,
        delta_process: Optional[Callable[[Dict[str, Any]], None]] = None,
        max_tokens: int = None,
    ) -> Dict[str, Any]:
        """
        调用 Qwen API 生成回复

        Args:
            messages: 消息列表
            level: AI 级别（Qwen 本地模型暂不使用级别选择）
            think_process: 思考过程回调（Qwen 不支持流式，此回调不触发）
            delta_process: 最终结果回调
            max_tokens: 最大生成 token 数

        Returns:
            Dict[str, Any]: API 响应结果
        """
        if not self.is_loaded:
            self.load()

        # 使用传入的 max_tokens 或默认值
        effective_max_tokens = max_tokens if max_tokens else self.max_tokens

        from datetime import datetime
        start_time = datetime.now()

        try:
            # Qwen 本地 API 使用 OpenAI 兼容格式
            url = self.base_url

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            payload = {
                "model": self.model_path,
                "messages": messages
                # "max_tokens": effective_max_tokens
            }

            logger.info(f"🚀 发送请求到 Qwen API: {url}")

            # 发送 POST 请求（Qwen 本地 API 不支持流式响应）
            # 经 self.session 走带瞬态重试的 adapter：连接抖动 / 5xx 自动重试
            response = self.session.post(url, headers=headers, json=payload, timeout=self.REQUEST_TIMEOUTS)

            elapsed = (datetime.now() - start_time).total_seconds()

            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Qwen API 调用成功 - elapsed={elapsed:.2f}s, status=200")

                # 非流式：拿到完整结果后回调一次最终进度（final=True）
                content = self._extract_content(result)
                fire_progress(delta_process, content, effective_max_tokens, True)

                return result
            else:
                error_msg = f"请求失败：{response.status_code}"
                logger.error(f"❌ Qwen API 调用失败 - elapsed={elapsed:.2f}s, status={response.status_code}, error={response.text[:200]}")
                return {"error": error_msg, "status_code": response.status_code, "response": response.text}

        except requests.exceptions.Timeout as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ Qwen API 请求超时 - elapsed={elapsed:.2f}s", exc_info=True)
            return {"error": f"请求超时：{str(e)}"}
        except requests.exceptions.ConnectionError as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ Qwen API 连接错误 - elapsed={elapsed:.2f}s, url={url}", exc_info=True)
            return {"error": f"连接错误：{str(e)}"}
        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ Qwen API 请求异常 - elapsed={elapsed:.2f}s, error={str(e)}", exc_info=True)
            return {"error": f"请求异常：{e}"}

    def _extract_content(self, result: Dict[str, Any]) -> str:
        """
        从 Qwen API 响应中提取内容文本

        Args:
            result: API 响应结果

        Returns:
            str: 提取的内容文本
        """
        if isinstance(result, dict):
            # OpenAI 兼容格式：choices[0].message.content
            if "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    return choice["message"]["content"]
            # 备选格式
            if "content" in result:
                content = result["content"]
                if isinstance(content, list):
                    return str(content)
                return str(content)
            elif "text" in result:
                return result["text"]
            elif "response" in result:
                return result["response"]
        return str(result)

    def get_status(self) -> dict:
        """
        获取模型状态

        Returns:
            dict: 包含模型状态信息的字典
        """
        return {
            "base_url": self.base_url,
            "model_path": self.model_path,
            "is_loaded": self.is_loaded,
            "api_type": "qwen",
            "max_tokens": self.max_tokens
        }

    def cleanup(self):
        """清理资源"""
        self.is_loaded = False
        if self.session is not None:
            self.session.close()
            self.session = None
        logger.info("🧹 Qwen API 资源已清理")


# 全局单例实例
_qwen_model_instance: Optional[AEQwenModel] = None


def get_qwen_model(
    base_url: str = None,
    api_key: str = None,
    model_path: str = None,
    max_tokens: int = None
) -> AEQwenModel:
    """
    获取 Qwen 模型单例实例

    Args:
        base_url: API 基础 URL（仅首次调用时有效）
        api_key: API 密钥（仅首次调用时有效）
        model_path: 模型路径（仅首次调用时有效）
        max_tokens: 最大生成 token 数（仅首次调用时有效）

    Returns:
        AEQwenModel: Qwen 模型实例
    """
    global _qwen_model_instance
    if _qwen_model_instance is None:
        _qwen_model_instance = AEQwenModel(base_url, api_key, model_path, max_tokens)
    return _qwen_model_instance


def cleanup_qwen_model():
    """清理全局 Qwen 模型实例"""
    global _qwen_model_instance
    if _qwen_model_instance is not None:
        _qwen_model_instance.cleanup()
        _qwen_model_instance = None
