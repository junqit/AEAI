import logging
from typing import TYPE_CHECKING

from .AEBaseContext import AEBaseContext
from .AEContextType import AEContextType
from Assistant.AERole import AERole

if TYPE_CHECKING:
    from .AELLMPayload import AELLMPayload

logger = logging.getLogger(__name__)


class AEWorkSpaceContext(AEBaseContext):

    def __init__(self, space: str = ""):
        super().__init__(context_type=AEContextType.workspace, space=space)

    def flow_llm_request(self, payload: "AELLMPayload") -> None:
        """AEFlowDelegate: 转发 flow 的 LLM 请求，经本 Context 的 send_llm_request 上送；
        用 context.ident 包装 out_schema，回程按 ident 路由回本 Context"""
        # 注入工作目录约束（首条 system 消息）：所有修改只能在此目录下，不可操作其他目录内容
        payload.messages.insert(0, {
            "role": AERole.SYSTEM.value,
            "content": f"当前工作目录：{self.space}。所有修改只能在此目录下进行，不可操作其他目录的内容。",
        })
        # env_param prompt 注入 + 包装 out_schema + 上送，交基类处理
        super().flow_llm_request(payload)

    def receive_llm_response(self, data: dict) -> None:
        """
        处理 LLM 回复（dispatch 已按 context.ident 路由并剥掉本层，data 为 chat.ident 层）：

        - 按 data.ident 从 _chat_map 取到 AEChat
        - 剥掉 chat.ident 层，把内层 llm_out 传给 AEChat.receiveLLMResult 继续向下传递
        """
        if not isinstance(data, dict):
            logger.error(f"[WorkSpace:{self.ident}] LLM 回复非 map: {data!r}")
            return
        chat_ident = data.get("ident")
        chat = self._chat_map.get(chat_ident)
        if chat is None:
            logger.error(f"[WorkSpace:{self.ident}] _chat_map 内未找到 chat_ident={chat_ident!r}")
            return
        # 剥掉 chat.ident 层，传给 AEChat 继续路由到子 flow
        out_schema = data.get("llm_out")
        if not isinstance(out_schema, dict):
            logger.error(f"[WorkSpace:{self.ident}] chat 内层 out_schema 非 map: {out_schema!r}")
            return
        chat.receiveLLMResult(out_schema)
