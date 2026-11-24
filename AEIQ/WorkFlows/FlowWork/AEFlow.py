"""
AEFlow - Flow 基类。

方法分区：
  - set_delegate / flow_receive_default|processing|complete / nextFlow
  - flow_send_llm_request / add_flow / on_flow_start

本类只管工作流流转（路由 / 转发 / 完成判定 / 子 flow 编排）。
"""
import logging
import uuid
import weakref
from typing import Dict, Optional, TYPE_CHECKING

from .AEFlowInfo import AEFlowInfo
from .AEFlowDelegate import AEFlowDelegateImpl
from .AEFlowInterface import AEFlowInterfaceImpl
from .AEFlowInput import AEFlowStatus, AEFlowInput
from .AEFlowOutput import AEFlowOutput
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Tools.Excutor import AERuntimeExcutor


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlowInterface import AEFlowInterface


class AEFlow(AEFlowInfo, AEFlowDelegateImpl, AEFlowInterfaceImpl):
    """Flow 基类。"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = "", flowInput: Optional[AEFlowInput] = None):
        super().__init__(flowOutput=flowOutput, ident=ident, flowInput=flowInput)
        self.delegate: "Optional[AEFlowDelegate]" = None
        self._flows: "Dict[str, AEFlowInterface]" = {}
        self.excutor = AERuntimeExcutor()

    # ==================== 接口实现 ====================

    # 注入 delegate（弱引用）
    def set_delegate(self, delegate: "AEFlowDelegate") -> None:
        self.delegate = weakref.proxy(delegate) if delegate is not None else None

    # 注册临时功能性方法，返回随机 funcident
    def registerFunctional(self, method: AEFunctional) -> str:
        funcident = uuid.uuid4().hex
        self.excutor.add_temporary(funcident, method, self)
        return funcident

    # 收到结果置 default 状态，子类可覆写
    def flow_receive_default(self, out_schema: "Optional[dict]") -> bool:
        self.status = AEFlowStatus.default
        return True

    # 收到结果置 processing 状态，子类可覆写
    def flow_receive_processing(self, out_schema: "Optional[dict]") -> bool:
        self.status = AEFlowStatus.processing
        return True

    # 返回首个 default 状态的子 flow，无则 None
    def nextFlow(self) -> "Optional[AEFlowInterface]":
        for flow in self._flows.values():
            if flow.status == AEFlowStatus.default:
                return flow
        return None

    # ==================== 描述信息 hook（子类覆写提供更丰富描述）====================

    # flow 描述信息 hook，子类可覆写
    def flow_description(self) -> str:
        return f"[d={self.deepth}]"

    # 返回本 flow 完成信息（含子 flow 递归）
    def flow_complete_info(self) -> dict:
        info = {
            "ident": self.ident,
            "title": self.title,
            "responsibility": self.responsibility,
            "question": "",
            "goal": self.input.get_goal() if self.input else "",
            "answer": "",
            "children": [sub.flow_complete_info() for sub in self._flows.values()],
        }
        # question 取 flow 的输入（父 flow 传入的问题/子任务内容）
        if self.input is not None and isinstance(self.input, AEFlowInput):
            info["question"] = self.input.get_content() or ""
        # answer 取 flow 产出（output.outResult，由 receive_summarize_result 填充）
        if self.output is not None:
            info["answer"] = self.output.outResult or ""
        return info

    # ==================== Delegate 实现 ====================
