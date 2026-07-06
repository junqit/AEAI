"""
AEFlow - Flow 基类，同时实现 AEFlowInterface 与 AEFlowDelegate 两个协议。

AEFlowInterface 实现（flow 自身接口）：
  - ident / delegate（属性）
  - receiveInputSchemaData()   接收输入数据
  - addFlow()                  添加子 flow

AEFlowDelegate 实现（子 flow 通过本类向外流转）：
  - next_flow_input_schema()   获取（下一个）子 flow 的输入数据结构
  - flow_llm()                 发送 AELLMPayload 调用 LLM
  - flow_complete()            Flow 完成，整理结果
"""
import json
import logging
import weakref
from enum import Enum
from typing import Dict, Optional, TYPE_CHECKING

from .AEFlowInfo import AEFlowInfo
from .AEFlowInput import AEFlowInput
from .AEFlowOutput import AEFlowOutput

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlowInterface import AEFlowInterface
    from Context.Context.AELLMPayload import AELLMPayload


class AEFlowStatus(str, Enum):
    """Flow 执行状态"""
    default = "default"            # 初始状态
    processing = "processing"      # 执行中
    complete = "complete"          # 已完成


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

    def startFlow(self, flowInput: AEFlowInput, flowOutput: AEFlowOutput) -> None:
        """启动 flow：仅在 default 状态下接收 flowInput / flowOutput，并切换到 processing。

        - 非 default 状态下调用将被忽略（仅 default 可接收）
        - 接收后置 input / output，状态切换为 processing
        """
        if self.status != AEFlowStatus.default:
            logger.warning(
                "[AEFlow:%s][%s] startFlow 仅在 default 状态可接收，当前 %s，忽略",
                self.ident, self.title, self.status,
            )
            return
        self.input = flowInput
        self.output = flowOutput
        self.status = AEFlowStatus.processing
        logger.info("[AEFlow:%s][%s] startFlow → processing", self.ident, self.title)

    def receiveInputSchemaData(self, data: dict) -> None:
        """
        接收输入数据（map），按其中的 ident 路由：

          - 先通过 ident 在 _flows 内获取子 flow；命中 → 转发内层 out_schema 给该子 flow
          - 不存在 ident（或未命中子 flow）→ 自己处理：交 flow_receive_llm
            （子类在 flow_receive_llm 中处理收到的数据）

        data 约定为 flow_llm 向上转发时的封装形态：{"ident": <目标 ident>, "llm_out": <...>}，
        每层路由消费一层 ident，逐层下传内层 out_schema；最内层叶子无 ident，由该层 flow 自己处理。

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
        # 先通过 ident 在 _flows 内获取子 flow；命中则转发内层 out_schema
        flow = self._flows.get(ident) if ident is not None else None
        if flow is not None:
            flow.receiveInputSchemaData(data.get("llm_out"))
            return
        
        # 不存在 ident（或未命中子 flow）：自己处理
        self.flow_receive_llm(data.get("llm_out", data))

    def flow_receive_llm(self, out_schema: "Optional[dict]") -> None:
        """
        收到经 receiveInputSchemaData 路由到自身、已解析出的 out_schema 数据。

        按当前 status 分发到对应处理方法（每个方法标识下一个状态并处理）：
          - default    → flow_receive_default     （→ processing）
          - processing → flow_receive_processing  （→ complete）
          - complete   → flow_receive_complete    （已 complete 不应再收到数据，打印错误）

        子类覆写各状态方法以处理收到的数据，而非覆写本方法。

        Args:
            out_schema: 从输入 map 中解析出的 out_schema 数据
        """
        if self.status == AEFlowStatus.default:
            self.flow_receive_default(out_schema)
        elif self.status == AEFlowStatus.processing:
            self.flow_receive_processing(out_schema)
        else:  # AEFlowStatus.complete
            self.flow_receive_complete(out_schema)

    def flow_receive_default(self, out_schema: "Optional[dict]") -> None:
        """
        status=default：收到的数据即 LLM 生成的输入数据，将 status 切换为 processing，
        并通过 delegate.flow_complete 通知返回。子类覆写时调用 super 以保留状态切换与通知。
        """
        logger.info("[AEFlow:%s][%s] 阶段=default → processing", self.ident, self.title)
        self.status = AEFlowStatus.processing
        if self.delegate is not None:
            self.delegate.flow_complete(self.to_map(), self.status)

    def flow_receive_processing(self, out_schema: "Optional[dict]") -> None:
        """
        status=processing：接收数据时将 status 切换为 complete，并通过 delegate.flow_complete 通知返回。
        子类覆写时调用 super 以保留状态切换与通知。
        """
        logger.info("[AEFlow:%s][%s] 阶段=processing → complete", self.ident, self.title)
        self.status = AEFlowStatus.complete
        if self.delegate is not None:
            self.delegate.flow_complete(self.to_map(), self.status)

    def flow_receive_complete(self, out_schema: "Optional[dict]") -> None:
        """
        status=complete：已 complete 不应再收到数据，打印错误。
        """
        logger.error(
            "[AEFlow:%s][%s] 阶段=complete，不应再收到数据: %r",
            self.ident, self.title, out_schema,
        )

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

        校验 delegate 后，用当前 flow 的 ident / title 包装 payload.out_schema，再向上转发
        （回程按 ident 路由回本 flow）。

        Args:
            payload: AELLMPayload 结构体

        Raises:
            RuntimeError: delegate 未设置时
        """
        if self.delegate is None:
            raise RuntimeError("AEFlow delegate 未设置，无法发送 LLM 请求")
        payload.out_schema = {
            "ident": self.ident,
            "title": self.title,
            "llm_out": payload.out_schema,
        }
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
        如 AENetRouteCenter 适配器）完成。本方法校验 delegate 后，用当前 flow 的 ident / title
        包装 payload.out_schema，再向上转发（回程按 ident 路由回本 flow）。

        Args:
            payload: AELLMPayload 结构体

        Raises:
            RuntimeError: delegate 未设置时
        """
        if self.delegate is None:
            raise RuntimeError("AEFlow delegate 未设置，无法发送 LLM 请求")
        # 用当前 flow 的 ident / title 包装 payload.out_schema
        payload.out_schema = {
            "ident": self.ident,
            "title": self.title,
            "llm_out": payload.out_schema,
        }
        self.delegate.flow_llm(payload)

    def flow_complete(self, result: dict, flowStatus: "AEFlowStatus") -> None:
        """
        Flow 完成通知：result 为完成 flow 的元信息（map），flowStatus 为其状态。

        - 命中直接子 flow → 把数据交给该子 flow 处理（receiveInputSchemaData），不再做自身状态处理
        - 未命中子 flow → 按自身 flowStatus 处理：
            - processing → flow_complete_processing
            - default    → flow_complete_default
            - complete   → flow_complete_complete
        无返回值。

        Args:
            result: 完成 flow 的元信息 map（含 ident / outResult）
            flowStatus: 完成 flow 的状态
        """
        ident = result.get("ident") if isinstance(result, dict) else None
        flow = self._flows.get(ident) if ident else None
        # 命中子 flow：把 result 内的 llm_out 交给子 flow 处理
        if flow is not None:
            self._current_index += 1
            llm_out = result.get("llm_out") if isinstance(result, dict) else None
            logger.info(
                "[AEFlow:%s][%s] flow_complete 命中子 flow(%s)，传入 llm_out:\n%s",
                self.ident, self.title, ident,
                json.dumps(llm_out, ensure_ascii=False, indent=2) if llm_out is not None else repr(llm_out),
            )
            flow.receiveInputSchemaData(llm_out)
            return
        # 未命中子 flow：按自己的状态进行处理
        if flowStatus == AEFlowStatus.processing:
            self.flow_complete_processing(result)
        elif flowStatus == AEFlowStatus.default:
            self.flow_complete_default(result)
        else:  # AEFlowStatus.complete
            self.flow_complete_complete(result)

    def flow_complete_default(self, result: dict) -> None:
        """status=default：未命中子 flow 的完成通知，非预期，记录告警。"""
        logger.warning(
            "[AEFlow:%s] flow_complete status=default，忽略: %r",
            self.ident, result,
        )

    def flow_complete_processing(self, result: dict) -> None:
        """status=processing：未命中子 flow 的完成通知，非预期，记录告警。"""
        logger.warning(
            "[AEFlow:%s] flow_complete status=processing，忽略: %r",
            self.ident, result,
        )

    def flow_complete_complete(self, result: dict) -> None:
        """status=complete：子 flow 已完成，向上委托通知。"""
        if self.delegate is not None:
            self.delegate.flow_complete(result, AEFlowStatus.complete)
