import uuid
import asyncio
import hashlib
import logging
from typing import Dict, Optional, TYPE_CHECKING

from Network.Core import AENetReq, AENetRsp
from Network.Core.AENetReq import AENetQues, AENetReqInfo
from Chat.AEChat import AEChat
from .AEContextType import AEContextType

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .AEContextDelegate import AEContextDelegate


class AEBaseContext:

    def __init__(self, context_type: AEContextType, space: str = ""):
        self.ident: str = self._generate_ident(context_type, space)
        self.space: str = space
        self.context_type: AEContextType = context_type
        self.delegate: Optional['AEContextDelegate'] = None
        # chat.ident -> AEChat，持有本 context 下的会话
        self._chat_map: Dict[str, AEChat] = {}

    # ==================== 私有方法 ====================

    @staticmethod
    def _generate_ident(context_type: AEContextType, space: str = "") -> str:
        if context_type == AEContextType.workspace:
            return hashlib.md5(space.encode()).hexdigest()

        if context_type == AEContextType.directory:
            return hashlib.md5(b"directory").hexdigest()

        if context_type == AEContextType.permission:
            return hashlib.md5(b"permission").hexdigest()

        return uuid.uuid4().hex

    # ==================== 接口（外部调用 / 子类覆写） ====================

    def context_config(self) -> Dict[str, str]:
        return {
            "ident": self.ident,
            "space": self.space,
            "type": self.context_type.value,
        }

    def receive_llm_response(self, data: dict) -> None:
        """
        接收 LLM 回复数据（AEUserContext 已按 ident 路由到本 Context）。

        基类默认仅记录日志；子类覆写以处理收到的数据。

        Args:
            data: LLM 回复解析后的 JSON（含 ident 及 out_schema 填充结果）
        """
        logger.info(f"Context {self.ident} 收到 LLM 回复数据: {data}")

    def receive_chat(self, question: AENetQues, req: AENetReqInfo) -> None:
        """接收 AENetQues 与 AENetReqInfo：内部创建 AEChat 并持有，把消息交给它处理（不等回，flow 内部异步流转）。

        - 新建 AEChat，delegate 设为当前 context，req 存入 chat，按 chat.ident 存入 _chat_map（添加持有）
        - receiveQuestion 丢到线程池后立即返回；后续 LLM 往返经 loop 异步流转
        """
        chat = AEChat(ident=uuid.uuid4().hex)
        chat.req = req
        chat.set_delegate(self)
        self._chat_map[chat.ident] = chat
        logger.info(f"AEChat created - chat_ident={chat.ident}, context={self.ident}")
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, chat.receiveQuestion, question)

    # ==================== delegate 转发 ====================

    def set_delegate(self, delegate: 'AEContextDelegate') -> None:
        self.delegate = delegate

    def send_request(self, request: AENetReq) -> None:
        if not self.delegate:
            raise ValueError("Context delegate is not set")
        self.delegate.send_request(request)

    def send_response(self, response: AENetRsp) -> None:
        if not self.delegate:
            raise ValueError("Context delegate is not set")
        self.delegate.send_response(response)

    def send_llm_request(self, payload) -> None:
        if not self.delegate:
            raise ValueError("Context delegate is not set")
        self.delegate.send_llm_request(payload)
