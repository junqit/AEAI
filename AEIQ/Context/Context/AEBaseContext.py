import uuid
import asyncio
import hashlib
import logging
from typing import Dict, Optional, TYPE_CHECKING

from Network.Core import AENetReq, AENetRsp
from Network.Core.AENetReq import AENetCont, AENetQues, AENetReqInfo
from Network.Core.AENetRsp import AENetRspCode
from Chat.AEChat import AEChat
from WorkFlows.AEFlow import AEFlowStatus, AE_IDENT, AE_ANSWER
from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput, AE_LLM_OUT
from .AEContextType import AEContextType

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .AEContextDelegate import AEContextDelegate
    from .AELLMPayload import AELLMPayload


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

    # ==================== 公开方法（外部调用 / 子类覆写） ====================

    def set_delegate(self, delegate: 'AEContextDelegate') -> None:
        """注入 delegate（AEContextDelegate）。"""
        self.delegate = delegate

    def context_config(self) -> Dict[str, str]:
        return {
            AE_IDENT: self.ident,
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
        """接收 AENetQues 与 AENetReqInfo：内部创建 AEChat 并持有，构建 input 后交 startFlow 启动
        （不等回，flow 内部异步流转）。

        - 新建 AEChat（构造时传入本 chat 输出结构 {ident, reply}），delegate 设为当前 context，
          req 存入 chat，按 chat.ident 存入 _chat_map（添加持有）
        - 由 question 构建 AEFlowInput，startFlow 丢到线程池后立即返回；后续 LLM 往返经 loop 异步流转
        """
        if question is None:
            logger.error("[Context:%s] 收到的 AENetQues 为空，忽略", self.ident)
            return
        # chat 的 ident 显式生成，同时写入 flowOutput.out_schema.ident，保证 complete 回程路由回本 chat
        from .AELLMPayload import llm_generate
        chat_ident = uuid.uuid4().hex
        chat = AEChat(
            ident=chat_ident,
            flowOutput=AEFlowOutput({AE_IDENT: chat_ident, AE_ANSWER: llm_generate("对用户的回复")}),
        )
        chat.req = req
        chat.set_delegate(self)
        self._chat_map[chat.ident] = chat
        logger.info(
            "AEChat created - chat_ident=%s, context=%s, question type=%s ident=%s content=%r",
            chat.ident, self.ident, question.type, question.ident, question.content,
        )
        flow_input = AEFlowInput(content=question.content or "")
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, chat.startFlow, flow_input)

    # ==================== AEFlowDelegate 实现（作为所属 chat 的 delegate） ====================

    def flow_llm_request(self, payload: "AELLMPayload") -> None:
        """AEFlowDelegate: 转发 flow 的 LLM 请求，经本 Context 的 send_llm_request 上送；
        用 context.ident 包装 out_schema，回程按 ident 路由回本 Context"""
        payload.out_schema = {AE_IDENT: self.ident, "type": self.context_type.value, AE_LLM_OUT: payload.out_schema}
        self.send_llm_request(payload)

    def flow_complete(self, result: dict, flowStatus: "AEFlowStatus") -> None:
        """AEFlowDelegate: flow 完成通知。status=complete 时组装 AENetRsp 经 delegate 发送给客户端。"""
        flow_ident = result.get(AE_IDENT) if isinstance(result, dict) else None
        if flowStatus != AEFlowStatus.complete:
            return
        # complete：找到所属 chat，回填 req 组装 response 发送
        chat = self._chat_map.get(flow_ident)
        if chat is None:
            logger.warning(
                "[Context:%s] complete 但 _chat_map 未找到 chat(ident=%s)，无法发送 response",
                self.ident, flow_ident,
            )
            return
        # 拿到 chat 即表示会话已结束，立即从 _chat_map 移除释放持有，避免后续重复回包
        self._chat_map.pop(flow_ident, None)
        rsp = AENetRsp(
            code=AENetRspCode.success,
            cont=AENetCont(
                type=self.context_type.value,
                ident=self.ident,
                space=self.space,
            ),
            req=chat.req,
            rsp={AE_ANSWER: result.get(AE_ANSWER)} if isinstance(result, dict) else None,
        )
        self.send_response(rsp)

    # ==================== delegate 转发 ====================

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
