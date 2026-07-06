import json
import logging

from .AEBaseContext import AEBaseContext
from .AEContextType import AEContextType

logger = logging.getLogger(__name__)


class AEWorkSpaceContext(AEBaseContext):

    def __init__(self, space: str = ""):
        super().__init__(context_type=AEContextType.workspace, space=space)

    def receive_llm_response(self, data: dict) -> None:
        """
        处理 LLM 回复（dispatch 已按 context.ident 路由并剥掉本层，data 为 chat.ident 层）：

        - 按 data.ident 从 _chat_map 取到 AEChat
        - 剥掉 chat.ident 层，把内层 llm_out 传给 AEChat.receiveLLMResult 继续向下传递
        """
        if not isinstance(data, dict):
            logger.error(f"[WorkSpace:{self.ident}] LLM 回复非 map: {data!r}")
            return
        # 打印 LLM 回复的 JSON 结构性数据
        logger.info(
            "[WorkSpace:%s] 收到 LLM 回复:\n%s",
            self.ident,
            json.dumps(data, ensure_ascii=False, indent=2),
        )
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
