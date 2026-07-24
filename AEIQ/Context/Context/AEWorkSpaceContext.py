import logging
from typing import TYPE_CHECKING

from .AEBaseContext import AEBaseContext
from .AEContextType import AEContextType
from Roles.AERoleType import AEConentRole, AE_ROLE, AE_CONTENT
from WorkFlows.AEFlowOutput import AE_LLM_OUT
from WorkFlows.AEFlow import AE_IDENT

if TYPE_CHECKING:
    from .AELLMPayload import AELLMPayload

logger = logging.getLogger(__name__)


class AEWorkSpaceContext(AEBaseContext):

    def __init__(self, space: str = ""):
        super().__init__(context_type=AEContextType.workspace, space=space)

    def receive_flow_llm_request(self, payload: "AELLMPayload") -> None:
        """AEFlowDelegate: 转发 flow 的 LLM 请求，经本 Context 的 send_llm_request 上送；
        用 context.ident 包装 out_schema，回程按 ident 路由回本 Context"""
        # 注入只读约束 + 本地文件性质说明
        # payload.messages.insert(0, {
        #     AE_ROLE: AEConentRole.SYSTEM.value,
        #     AE_CONTENT: (
        #         "所有目录下的内容只可读取，不可进行任何修改、删除或写入操作。\n"
        #         "本地文件系统仅含工程文件（代码 / 配置 / 文档等），不含任何网络实时数据。"
        #     ),
        # })
        # env_param prompt 注入由基类 AEBaseContext.receive_flow_llm_request 处理
        super().receive_flow_llm_request(payload)

    def receive_llm_response(self, data: dict) -> None:
        """
        处理 LLM 回复（dispatch 已按 context.ident 路由并剥掉本层，data 为 chat.ident 层）：

        - 按 data.ident 从 _chat_map 取到 AEChat
        - 剥掉 chat.ident 层，把内层 llm_out 传给 AEChat.receive_llm_response 继续向下传递
        """
        if not isinstance(data, dict):
            logger.error(f"[WorkSpace:{self.ident}] LLM 回复非 map: {data!r}")
            return
        chat_ident = data.get(AE_IDENT)
        chat = self._chat_map.get(chat_ident)
        if chat is None:
            logger.error(f"[WorkSpace:{self.ident}] _chat_map 内未找到 chat_ident={chat_ident!r}")
            return
        # 剥掉 chat.ident 层，传给 AEChat 继续路由到子 flow
        out_schema = data.get(AE_LLM_OUT)
        if not isinstance(out_schema, dict):
            logger.error(f"[WorkSpace:{self.ident}] chat 内层 out_schema 非 map: {out_schema!r}")
            return
        chat.receive_llm_response(out_schema)
