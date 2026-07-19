"""
AEFlow - Flow 基类，多继承 AEFlowRolePrompt / AEFlowOptimizeQuestion，
并实现 AEFlowInterface 与 AEFlowDelegate 两个协议。

方法分区：
  - AEFlowInterface 实现：set_delegate / startFlow / receive_llm_response /
    flow_receive_llm / flow_receive_default|processing|complete / nextFlow / send_llm_payload
  - AEFlowDelegate 实现（转调 AEFlowDelegateImpl）：flow_llm_request / flow_add_next_flow / flow_complete
  - 私有方法 / 属性：outResult_summary / _extract_answer

角色描述（requestOptimizePrompt 等）、问题优化（requestOptimizeInputOptimize 等）、
角色信息（requestRoleInfo / receiveRole）分别由父类
AEFlowRolePrompt / AEFlowOptimizeQuestion / AEFlowDescription 提供。
"""
import json
import logging
import weakref
from typing import Dict, Optional, TYPE_CHECKING

from .AEFlowInfo import AEFlowInfo, AEFlowStatus, AE_IDENT, AE_ANSWER, AE_funcationkey
from .AEFlowDelegate import AEFlowCompletEvent, AEFlowDelegateImpl
from .AEFlowInterfaceImpl import AEFlowInterfaceImpl, AEFlowOptimizeQuestion
from .AEFlowRolePrompt import AEFlowRolePrompt
from .AEFlowDescription import AEFlowDescription
from .AEFlowInput import AEFlowInput
from .AEFlowOutput import AEFlowOutput, AE_LLM_OUT
from Context.Context.AELLMPayload import AELLMPayload
from Excutor import AERuntimeExcutor
from Excutor.AERuntimeExcutor import AEFunctional


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlowInterface import AEFlowInterface


class AEFlowFunctional(AEFunctional):
    """Flow 通用回包功能性方法名（继承 AEFunctional 的 flow_receive_* 常量，可按需扩展）。"""
    receiveRole = "receiveRole"                            # 接收 LLM 生成的自身工作名称与能力范围，传入 map
    receiveOptimizePrompt = "receiveOptimizePrompt"        # 接收 LLM 基于 title+能力 生成的问题优化提示，传入 map
    receiveOptimizeInputOptimize = "receiveOptimizeInputOptimize"  # 接收 LLM 综合上下文返回的最终结果，传入 map


class AEFlow(AEFlowRolePrompt, AEFlowOptimizeQuestion, AEFlowDescription):
    """Flow 基类，多继承 AEFlowRolePrompt（角色描述）/ AEFlowOptimizeQuestion（问题优化）/ AEFlowDescription（角色信息）；AEFlowDelegate 协议实现转调 AEFlowDelegateImpl 静态方法"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = "", flowInput: Optional[AEFlowInput] = None):
        # ----- AEFlowInfo 属性 -----
        # ident 可传入（默认空，为空则内部生成）；外部只读；
        # output（本 flow 输出结构）创建时必传；input 可在初始化时传入（默认 None），未传时由 startFlow 设置
        super().__init__(flowOutput=flowOutput, ident=ident, flowInput=flowInput)
        # delegate：AEFlowDelegate，Flow 内部信息向外流转的出口
        self.delegate: "Optional[AEFlowDelegate]" = None
        # ----- 内部状态 -----
        self._flows: "Dict[str, AEFlowInterface]" = {}  # 有序 map，key 为 flow.ident
        # 方法执行器：管理 functional -> 脚本映射，区分 default / temporary；
        # 默认不注册任何方法，由业务子类自行 add_default / add_temporary 添加
        self.excutor = AERuntimeExcutor()

    # ==================== AEFlowInterface 实现 ====================

    def set_delegate(self, delegate: "AEFlowDelegate") -> None:
        """注入 delegate（弱引用持有，避免与子 flow 形成循环引用）"""
        self.delegate = weakref.proxy(delegate) if delegate is not None else None

    def startFlow(self, flowInput: AEFlowInput) -> bool:
        """启动 flow（转调 AEFlowInterfaceImpl）。"""
        return AEFlowInterfaceImpl.startFlow(self, flowInput)

    def receive_llm_response(self, data: dict) -> None:
        """接收输入数据（map），按 ident 路由（转调 AEFlowInterfaceImpl）。"""
        AEFlowInterfaceImpl.receive_llm_response(self, data)

    def flow_receive_llm(self, out_schema: "Optional[dict]") -> None:
        """
        收到经 receive_llm_response 路由到自身、已解析出的 out_schema 数据。

        按 out_schema 内的 AE_funcationkey 字段从 self.excutor 取对应脚本并执行；
        该 key 由发送方 flowOutput 注册时随机生成，对应一个 flow_receive_* 方法。

        out_schema 内无 AE_funcationkey 字段、或其值未在 excutor 内注册时，打印错误信息并忽略。
        子类可经 excutor.add_default / add_temporary 自定义处理，或覆写各 flow_receive_* 方法；
        temporary 注册执行后由 excutor 自动清除。

        Args:
            out_schema: 从输入 map 中解析出的 out_schema 数据（含 AE_funcationkey / llm_out 字段）
        """
        if not isinstance(out_schema, dict):
            logger.error("[AEFlow:%s] out_schema 非 map，忽略: %r", self.ident, out_schema)
            return
        command = out_schema.get(AE_funcationkey)
        # 真正交给业务处理的内容在 llm_out 下（out_schema 形如 {ident, title, funcationkey, llm_out: <内容>}）
        inner = out_schema.get(AE_LLM_OUT)
        if not self.excutor.contains(command):
            logger.error(
                "[AEFlow:%s][%s] out_schema 内 funcationkey=%r 无效或缺失，忽略: %r",
                self.ident, self.title, command, out_schema,
            )
            return
        # inner 直接传入；target 在注册时已绑定为 self，temporary 执行后由 excutor 自动清除
        self.excutor.exec(command, inner)

    def flow_receive_default(self, out_schema: "Optional[dict]") -> bool:
        """
        status=default：收到结果数据，置本 flow 状态为 default。子类可覆写做业务处理。

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        self.status = AEFlowStatus.default
        return True

    def flow_receive_processing(self, out_schema: "Optional[dict]") -> bool:
        """
        status=processing：收到结果数据，置本 flow 状态为 processing。子类可覆写做业务处理。

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        self.status = AEFlowStatus.processing
        return True

    def flow_receive_complete(self, out_schema: "Optional[dict]", event: "AEFlowCompletEvent" = AEFlowCompletEvent.default) -> bool:
        """
        status=complete：收到结果数据，置本 flow 状态为 complete，赋值最终结果，并通过 delegate.flow_complete 通知返回。

        Args:
            out_schema: 完成回包内层 llm_out（含 ident / reply）
            event: 完成事件（AEFlowCompletEvent.default / startFlow / error），透传给 delegate.flow_complete

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        self.status = AEFlowStatus.complete
        self.outResult = out_schema
        if self.delegate is not None:
            self.delegate.flow_complete(out_schema, event)
        return True

    def nextFlow(self) -> "Optional[AEFlowInterface]":
        """
        获取下一个待执行的子 flow：按 addFlow 顺序首个状态为 default 的子 flow。

        Returns:
            AEFlowInterface: 首个 default 状态的子 flow；均非 default 时返回 None
        """
        for flow in self._flows.values():
            if flow.status == AEFlowStatus.default:
                return flow
        return None

    def send_llm_payload(self, payload: "AELLMPayload") -> None:
        """
        通过 delegate 发送 AELLMPayload（无返回值）。

        校验 delegate 后，用 ident / title 包装 payload.out_schema 向上转发
        （回程按 ident 路由回本 flow）。

        Args:
            payload: AELLMPayload 结构体

        Raises:
            RuntimeError: delegate 未设置时
        """
        if self.delegate is None:
            raise RuntimeError("AEFlow delegate 未设置，无法发送 LLM 请求")
        # 外层信封：ident / title 用于回程路由，llm_out 包装内层内容
        payload.out_schema = {
            AE_IDENT: self.ident,
            "title": self.title,
            AE_LLM_OUT: payload.out_schema,
        }
        self.delegate.flow_llm_request(payload)

    # ==================== AEFlowDelegate 实现（转调 AEFlowDelegateImpl 静态方法，传入 self）====================

    def flow_llm_request(self, payload: "AELLMPayload") -> None:
        """发送 AELLMPayload 调用 LLM（转调 AEFlowDelegateImpl）。"""
        AEFlowDelegateImpl.flow_llm_request(self, payload)

    def flow_add_next_flow(self, flow: "AEFlowInterface") -> None:
        """添加下一个待执行的子 flow（转调 AEFlowDelegateImpl）。"""
        AEFlowDelegateImpl.flow_add_next_flow(self, flow)

    def flow_complete(self, result: dict, event: "AEFlowCompletEvent") -> None:
        """Flow 完成通知（转调 AEFlowDelegateImpl）。"""
        AEFlowDelegateImpl.flow_complete(self, result, event)

    # ==================== 私有方法 / 属性 ====================

    @property
    def outResult_summary(self) -> str:
        """从 outResult 中提取总结内容（AE_ANSWER），并附带角色说明。

        形如「我是一名{title}，{responsibility}。我的回答：{answer}」；
        title / responsibility 均为空时省略角色前缀，仅返回「我的回答：{answer}」。
        """
        answer = self._extract_answer(self.outResult) or ""
        if len(self.title) > 0 or len(self.responsibility) > 0:
            return f"我是一名{self.title}，{self.responsibility}。我的回答：{answer}"
        return f"我的回答：{answer}"

    @staticmethod
    def _extract_answer(obj) -> Optional[str]:
        """递归查找 obj 内首个 AE_ANSWER 键的值。"""
        if isinstance(obj, dict):
            if AE_ANSWER in obj:
                return obj[AE_ANSWER]
            for v in obj.values():
                r = AEFlow._extract_answer(v)
                if r is not None:
                    return r
        return None
