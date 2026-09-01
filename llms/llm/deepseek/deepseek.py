"""
DeepSeek API 模型类
封装 DeepSeek API 的调用、配置和资源管理

与 claude/zhipu/gpt 一致，走内部网关 Anthropic 兼容的 /v1/messages 接口
（同样的域名同样的地址），仅模型名替换为 deepseek-v4-pro，并附带
X-Model-Provider-Id: tongyi 头指定网关后端供应商。
"""
import json
import requests
import time
import logging
from typing import Optional, List, Dict, Any, Callable

from AEAiLevel import AEAiLevel
from common.llm_utils import split_system_messages, fire_progress

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class _StreamIncomplete(Exception):
    """流式响应未正常结束（缺少 message_stop）时抛出，触发重试"""
    pass


# ==================== Anthropic SSE 协议常量（不可变） ====================
# SSE 行前缀与终止标记
_DS_SSE_DATA_PREFIX = "data:"
_DS_SSE_DONE = "[DONE]"

# SSE 事件类型（event.type）
_DS_EVT_MESSAGE_START = "message_start"
_DS_EVT_CONTENT_BLOCK_START = "content_block_start"
_DS_EVT_CONTENT_BLOCK_DELTA = "content_block_delta"
_DS_EVT_CONTENT_BLOCK_STOP = "content_block_stop"
_DS_EVT_MESSAGE_DELTA = "message_delta"
_DS_EVT_MESSAGE_STOP = "message_stop"

# delta.type 取值
_DS_DELTA_TEXT = "text_delta"
_DS_DELTA_THINKING = "thinking_delta"

# 事件字段键
_DS_F_TYPE = "type"
_DS_F_DELTA = "delta"
_DS_F_TEXT = "text"
_DS_F_THINKING = "thinking"
_DS_F_MESSAGE = "message"
_DS_F_ID = "id"
_DS_F_MODEL = "model"
_DS_F_USAGE = "usage"
_DS_F_STOP_REASON = "stop_reason"
_DS_F_INDEX = "index"
_DS_F_CONTENT_BLOCK = "content_block"
_DS_F_CONTENT = "content"
_DS_F_ROLE = "role"

# 拼回 message 结构用的固定取值
_DS_ROLE_ASSISTANT = "assistant"
_DS_MSG_TYPE_MESSAGE = "message"
_DS_BLOCK_TYPE_TEXT = "text"


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

    def _consume_stream(
        self,
        response,
        model: str,
        max_tokens: int,
        think_process: Optional[Callable[[Dict[str, Any]], None]] = None,
        delta_process: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        消费 Anthropic 兼容的 SSE 流式响应，累加文本 delta，拼回与
        非流式调用一致的 message 结构（content 块数组），供 _parse_response 复用。

        事件序列：message_start → content_block_start →
                  content_block_delta(thinking_delta / text_delta) → content_block_stop →
                  message_delta(stop_reason/usage) → message_stop

        回调契约（思考内容与回答内容区分上报）：
        - think_process：每个 thinking_delta 到达时回调（final=False），上报累计「思考内容」进度。
        - delta_process：每个 text_delta 到达时回调（final=False），上报累计「回答内容」进度；
          流正常结束后再回调一次最终结果（final=True，完整回答）。非流式模型仅回调最终结果一次。
        进度信息结构与其它模型统一，见 common.llm_utils.make_progress_info。

        Raises:
            _StreamIncomplete: 未收到 message_stop，流被中途截断
            requests.exceptions.* : 网络层读取异常（由上层捕获重试）
        """
        accumulated_text: List[str] = []      # 回答内容（text_delta 累计）
        accumulated_thinking: List[str] = []  # 思考内容（thinking_delta 累计）
        stop_reason = None
        usage: Dict[str, Any] = {}
        msg_id = None
        got_message_stop = False

        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            # SSE 数据行以 data: 开头，其余（event:、注释、空行）跳过
            if not raw_line.startswith(_DS_SSE_DATA_PREFIX):
                continue
            data_str = raw_line[len(_DS_SSE_DATA_PREFIX):].lstrip()
            if data_str == _DS_SSE_DONE:
                break
            try:
                event = json.loads(data_str)
            except json.JSONDecodeError:
                # 跳过无法解析的行，避免单行异常中断整条流
                continue

            etype = event.get(_DS_F_TYPE)
            if etype == _DS_EVT_MESSAGE_START:
                msg = event.get(_DS_F_MESSAGE, {}) or {}
                msg_id = msg.get(_DS_F_ID)
                usage = msg.get(_DS_F_USAGE, {}) or {}
            elif etype == _DS_EVT_CONTENT_BLOCK_DELTA:
                delta = event.get(_DS_F_DELTA, {}) or {}
                dtype = delta.get(_DS_F_TYPE)
                if dtype == _DS_DELTA_THINKING:
                    # thinking_delta：思考内容在 delta.thinking 字段（非 text），逐 delta 上报 think_process（final=False）
                    piece = delta.get(_DS_F_THINKING, "")
                    accumulated_thinking.append(piece)
                    fire_progress(
                        think_process, "".join(accumulated_thinking), max_tokens, False
                    )
                elif dtype == _DS_DELTA_TEXT:
                    # text_delta：回答内容（delta），逐 delta 上报 delta_process（final=False）；
                    # 最终结果由 delta_process 在流结束后以 final=True 上报
                    piece = delta.get(_DS_F_TEXT, "")
                    accumulated_text.append(piece)
                    fire_progress(
                        delta_process, "".join(accumulated_text), max_tokens, False
                    )
            elif etype == _DS_EVT_MESSAGE_DELTA:
                delta = event.get(_DS_F_DELTA, {}) or {}
                if delta.get(_DS_F_STOP_REASON):
                    stop_reason = delta.get(_DS_F_STOP_REASON)
                u = event.get(_DS_F_USAGE)
                if u:
                    usage.update(u)
            elif etype == _DS_EVT_MESSAGE_STOP:
                got_message_stop = True

        if not got_message_stop:
            raise _StreamIncomplete("缺少 message_stop 事件")

        full_text = "".join(accumulated_text)
        # 流正常结束：回调一次最终结果（final=True），与非流式模型契约一致
        fire_progress(delta_process, full_text, max_tokens, True)

        return {
            _DS_F_ID: msg_id,
            _DS_F_TYPE: _DS_MSG_TYPE_MESSAGE,
            _DS_F_ROLE: _DS_ROLE_ASSISTANT,
            _DS_F_MODEL: model,
            _DS_F_CONTENT: [{_DS_F_TYPE: _DS_BLOCK_TYPE_TEXT, _DS_F_TEXT: full_text}],
            _DS_F_STOP_REASON: stop_reason,
            _DS_F_USAGE: usage,
        }

    def generate(
        self,
        messages: List[Dict[str, str]],
        level: AEAiLevel,
        stream: bool = True,
        think_process: Optional[Callable[[Dict[str, Any]], None]] = None,
        delta_process: Optional[Callable[[Dict[str, Any]], None]] = None,
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
        if stream:
            payload["stream"] = True

        # 请求/响应内容由 AEBaseProvider.generate 统一打印，模型层不再输出

        # 最多重试 10 次（429 限流 / 5xx / 网络异常等），全部失败则返回失败
        MAX_RETRY = 10
        backoff = 1.0
        last_error = "未知错误"
        for attempt in range(1, MAX_RETRY + 1):
            try:
                if stream:
                    # 流式：连接超时 10s，单次读取间隔超时 60s（token 持续流入即不会触发）
                    response = requests.post(
                        url, headers=headers, json=payload,
                        timeout=(10, 60), stream=True,
                    )
                    try:
                        if response.status_code != 200:
                            last_error = f"status={response.status_code}, error={response.text[:200]}"
                            # 4xx 客户端错误（除 429 限流外）不可重试
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
                        else:
                            result = self._consume_stream(
                                response, model, max_tokens, think_process, delta_process
                            )
                            elapsed = (datetime.now() - start_time).total_seconds()
                            logger.info(
                                f"✅ DeepSeek API 流式调用成功 - model={model}, elapsed={elapsed:.2f}s, status=200, attempt={attempt}"
                            )
                            return result
                    finally:
                        response.close()
                else:
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
            except _StreamIncomplete as e:
                last_error = f"流式响应未正常结束: {e}"
                logger.warning("⚠️ DeepSeek 流式响应未结束将重试 - attempt=%d/%d, %.1fs 后重试: %s", attempt, MAX_RETRY, backoff, e)
            except requests.exceptions.Timeout as e:
                last_error = f"请求超时: {e}"
                logger.warning("⚠️ DeepSeek 请求超时将重试 - attempt=%d/%d, %.1fs 后重试: %s", attempt, MAX_RETRY, backoff, e)
            except requests.exceptions.ChunkedEncodingError as e:
                # 即原 InvalidChunkLength 的包装——流式下连接被中途截断
                last_error = f"流式读取中断(ChunkedEncodingError): {e}"
                logger.warning("⚠️ DeepSeek 流式读取中断将重试 - attempt=%d/%d, %.1fs 后重试: %s", attempt, MAX_RETRY, backoff, e)
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
