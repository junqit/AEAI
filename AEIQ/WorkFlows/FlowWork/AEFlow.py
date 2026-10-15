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

from .AEFlowInfo import AEFlowInfo, AE_IDENT
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

    def set_delegate(self, delegate: "AEFlowDelegate") -> None:
        """注入 delegate（弱引用持有，避免与子 flow 形成循环引用）"""
        self.delegate = weakref.proxy(delegate) if delegate is not None else None

    def registerFunctional(self, method: AEFunctional) -> str:
        """注册临时功能性方法。funcident 为随机字符串键，method 为方法名字符串。

        Args:
            method: 方法名字符串（如 flow_receive_*），executor 内部经 method_call 拼 script

        Returns:
            随机生成的 funcident，供写入 out_schema 的 AE_funcationkey 字段
        """
        funcident = uuid.uuid4().hex
        self.excutor.add_temporary(funcident, method, self)
        return funcident

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

    def nextFlow(self) -> "Optional[AEFlowInterface]":
        """
        获取下一个待执行的子 flow：按 add_flow 顺序首个状态为 default 的子 flow。

        Returns:
            AEFlowInterface: 首个 default 状态的子 flow；均非 default 时返回 None
        """
        for flow in self._flows.values():
            if flow.status == AEFlowStatus.default:
                return flow
        return None

    # ==================== 描述信息 hook（子类覆写提供更丰富描述）====================

    def flow_description(self) -> str:
        """flow 描述信息（hook）：返回 [d=deepth]，子类覆写可追加 role / title。"""
        return f"[d={self.deepth}]"

    def flow_complete_info(self) -> dict:
        """本 flow 的完成信息（含子 flow 递归），供上层汇总成整体 JSON 树。

        自拼 ident/title/responsibility/question/goal/answer 与子 flow 的 flow_complete_info；此处安全取值。
        """
        info = {
            "ident": self.ident,
            "title": getattr(self, "title", "") or "",
            "responsibility": getattr(self, "responsibility", "") or "",
            "question": "",
            "goal": (self.input.get_goal() if self.input is not None else ""),
            "answer": "",
            "children": [sub.flow_complete_info() for sub in self._flows.values()],
        }
        # question 取 flow 的输入（父 flow 传入的问题/子任务内容）
        inp = getattr(self, "input", None)
        if inp is not None and isinstance(inp, AEFlowInput):
            info["question"] = inp.get_content() or ""
        # answer 取 flow 产出（output.outResult，由 receive_summarize_result 填充）
        if self.output is not None:
            info["answer"] = self.output.outResult or ""
        return info

    # ==================== Delegate 实现 ====================
