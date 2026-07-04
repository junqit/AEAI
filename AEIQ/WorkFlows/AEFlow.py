"""
AEFlow - Flow 基类，同时实现 AEFlowInterface 与 AEFlowDelegate 两个协议。

AEFlowInterface 实现（flow 自身接口）：
  - ident / delegate（属性）
  - inputSchema()              返回输入参数数据结构
  - receiveInputSchemaData()   接收按 inputSchema 组织的输入数据
  - addFlow()                  添加子 flow

AEFlowDelegate 实现（子 flow 通过本类向外流转）：
  - next_flow_input_schema()   获取（下一个）子 flow 的输入数据结构
  - flow_llm()                 发送 AELLMPayload 调用 LLM
  - flow_complete()            Flow 完成，按下游 inputSchema 整理结果
"""
import json
import logging
import weakref
from enum import Enum
from typing import Dict, Optional, TYPE_CHECKING

from .AEFlowInfo import AEFlowInfo

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlowInterface import AEFlowInterface
    from Context.AELLMPayload import AELLMPayload


class AEFlowStatus(str, Enum):
    """Flow 执行状态"""
    default = "default"        # 初始状态
    processing = "processing"  # 执行中
    complete = "complete"      # 已完成


class AEFlow(AEFlowInfo):
    """Flow 基类，继承 AEFlowInfo，实现 AEFlowInterface 与 AEFlowDelegate 协议"""

    def __init__(self, ident: str):
        # ----- AEFlowInfo 属性 -----
        # ident 创建时必填（不可为空）；外部只读；
        # input_schema / out_schema / outResult 不在初始化阶段配置，后续按需设置
        super().__init__(ident=ident)
        # delegate：AEFlowDelegate，Flow 内部信息向外流转的出口
        self.delegate: "Optional[AEFlowDelegate]" = None
        # ----- 角色信息 -----
        self.title: str = ""           # 职称
        self.responsibility: str = ""  # 职责要求
        # ----- 内部状态 -----
        self._flows: "Dict[str, AEFlowInterface]" = {}  # 有序 map，key 为 flow.ident
        self._current_index: int = 0                    # 当前执行的子 flow 序号
        # flow 执行状态，初始为 default
        self.status: AEFlowStatus = AEFlowStatus.default

    # ==================== AEFlowInterface 实现 ====================

    def set_delegate(self, delegate: "AEFlowDelegate") -> None:
        """注入 delegate（弱引用持有，避免与子 flow 形成循环引用）"""
        self.delegate = weakref.proxy(delegate) if delegate is not None else None

    def inputSchema(self) -> "Optional[dict]":
        """
        返回当前 flow 的输入数据结构，并用本 flow 的 ident 包装。

        形态：{"ident": <self.ident>, "out_schema": <input_schema>}，
        供父 flow 取作 LLM out_schema，回程按 ident 逐层路由回本 flow。

        Returns:
            Optional[dict]: ident + input_schema 的封装；input_schema 未设置时 out_schema 为 None
        """
        return {"ident": self.ident, "out_schema": self.input_schema}

    def receiveInputSchemaData(self, data: dict) -> None:
        """
        接收输入数据（map），按其中的 ident 路由（ident 仅用于本层路由，已使用）：

          - ident 命中自身 → 解析 data 中的 out_schema，交给 flow_receive_llm 处理
            （子类在 flow_receive_llm 中处理收到的数据）
          - ident 命中 _flows 内子 flow → 将内层 out_schema 转发给该子 flow 的
            receiveInputSchemaData（ident 已消费，不再下传）
          - 均未命中 → 错误日志输出收到的数据

        data 约定为 flow_llm 向上转发时的封装形态：{"ident": <目标 ident>, "out_schema": <...>}，
        每层路由消费一层 ident，逐层下传内层 out_schema。

        Args:
            data: 输入数据 map（含 ident / out_schema）
        """
        # 先打印收到的数据
        if isinstance(data, dict):
            logger.info(
                "[AEFlow:%s][%s] receiveInputSchemaData 收到:\n%s",
                self.ident, self.title,
                json.dumps(data, ensure_ascii=False, indent=2),
            )
        else:
            logger.info("[AEFlow:%s][%s] receiveInputSchemaData 收到: %r", self.ident, self.title, data)
        if not isinstance(data, dict):
            logger.error("[AEFlow:%s] 收到的数据非 map，无法解析: %r", self.ident, data)
            return
        ident = data.get("ident")
        # ident 仅用于本层路由，已使用；后续只传内层 out_schema
        out_schema = data.get("out_schema")
        # 命中自身：交给子类处理
        if ident == self.ident:
            self.flow_receive_llm(out_schema)
            return
        # 非自身：在 _flows 内按 ident 命中子 flow，转发内层 out_schema
        flow = self._flows.get(ident)
        if flow is not None:
            flow.receiveInputSchemaData(out_schema)
        else:
            logger.error(
                "[AEFlow:%s] 未命中任何 flow（ident=%r），收到的数据: %r",
                self.ident, ident, data,
            )

    def flow_receive_llm(self, out_schema: "Optional[dict]") -> None:
        """
        处理经 receiveInputSchemaData 路由到自身、已解析出的 out_schema 数据。

        基类默认打印收到的结果数据（带本 flow 的 ident）；子类覆写以处理收到的数据
        （如按 out_schema 落地结果、驱动后续 flow）。

        Args:
            out_schema: 从输入 map 中解析出的 out_schema 数据
        """
        if isinstance(out_schema, dict):
            logger.info(
                "[AEFlow:%s] 收到自己的结果数据:\n%s",
                self.ident,
                json.dumps(out_schema, ensure_ascii=False, indent=2),
            )
        else:
            logger.info("[AEFlow:%s] 收到自己的结果数据: %r", self.ident, out_schema)

    def addFlow(self, flow: "AEFlowInterface") -> None:
        """
        添加子 flow。

        添加前把 flow.delegate 设置为当前 flow（弱引用）；
        以 flow.ident 为 key 存入有序 map。

        Args:
            flow: 待添加的 flow，须符合 AEFlowInterface 协议
        """
        flow.set_delegate(self)
        self._flows[flow.ident] = flow

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

        校验 delegate 后，用当前 flow 的 ident 包装 payload.out_schema，再向上转发
        （回程按 ident 路由回本 flow）。

        Args:
            payload: AELLMPayload 结构体

        Raises:
            RuntimeError: delegate 未设置时
        """
        if self.delegate is None:
            raise RuntimeError("AEFlow delegate 未设置，无法发送 LLM 请求")
        # 用当前 flow 的 ident 包装 payload.out_schema
        payload.out_schema = {"ident": self.ident, "out_schema": payload.out_schema}
        self.delegate.flow_llm(payload)

    # ==================== AEFlowDelegate 实现 ====================

    def next_flow_input_schema(self, info: "Optional[AEFlowInfo]" = None) -> "Optional[AEFlowInfo]":
        """
        获取子 flow 的元信息（AEFlowInfo）。

        - info 非空：按 info.ident 返回该子 flow
        - info 为空：返回本层下一个（current+1）子 flow；本层无下一个时向上委托外层 delegate

        Args:
            info: 指定 flow 的元信息（用其 ident 查找）；为 None 时取下一个

        Returns:
            AEFlowInfo: 子 flow 元信息（AEFlow 即 AEFlowInfo）；无可用时返回 None
        """
        if info is not None:
            return self._flows.get(info.ident)
        order = list(self._flows.keys())
        nxt = self._current_index + 1
        if 0 <= nxt < len(order):
            return self._flows[order[nxt]]
        # 本层无下一个子 flow：向上委托外层 delegate
        if self.delegate is not None:
            return self.delegate.next_flow_input_schema()
        return None

    def flow_llm(self, payload: "AELLMPayload") -> None:
        """
        发送 AELLMPayload 调用 LLM（无返回值）。

        AEFlow 自身不持有 LLM 客户端，真实发送由外层 delegate（具体 AEFlowDelegate 实现，
        如 AEContextManager 适配器）完成。本方法校验 delegate 后，用当前 flow 的 ident
        包装 payload.out_schema，再向上转发。

        Args:
            payload: AELLMPayload 结构体

        Raises:
            RuntimeError: delegate 未设置时
        """
        if self.delegate is None:
            raise RuntimeError("AEFlow delegate 未设置，无法发送 LLM 请求")
        # 用当前 flow 的 ident 包装 payload.out_schema
        payload.out_schema = {"ident": self.ident, "out_schema": payload.out_schema}
        self.delegate.flow_llm(payload)

    def flow_complete(self, result: "AEFlowInfo") -> None:
        """
        Flow 完成通知：result 为完成 flow 的元信息（AEFlowInfo）。

        按 result.ident 匹配 _flows：
          - 命中（本层直接子 flow 完成）→ 推进当前子 flow 序号，并通过
            receiveInputSchemaData 将 result.outResult 传入命中的子 flow
          - 未命中 → 向上委托 delegate.flow_complete(result)
        无返回值。

        Args:
            result: 完成 flow 的元信息（含 ident / outResult）
        """
        ident = result.ident
        if ident and ident in self._flows:
            self._current_index += 1
            # 将完成 flow 的 outResult 传入命中的子 flow
            self._flows[ident].receiveInputSchemaData(result.outResult)
        elif self.delegate is not None:
            self.delegate.flow_complete(result)
