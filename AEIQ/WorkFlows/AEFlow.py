"""
AEFlow - Flow 基类，同时实现 AEFlowInterface 与 AEFlowDelegate 两个协议。

AEFlowInterface 实现（flow 自身接口）：
  - ident / delegate（属性）
  - receiveLLMResult()   接收输入数据
  - addFlow()                  添加子 flow

AEFlowDelegate 实现（子 flow 通过本类向外流转）：
  - flow_llm_request()                 发送 AELLMPayload 调用 LLM
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
from Context.Context.AELLMPayload import AELLMPayload
from Assistant.AERole import AERole

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlowInterface import AEFlowInterface


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

    def receiveLLMResult(self, data: dict) -> None:
        """
        接收输入数据（map），按其中的 ident 路由：

          - ident == self.ident → 本层处理，交 flow_receive_llm
            （子类在 flow_receive_llm 中处理收到的数据）
          - ident 命中 _flows 内子 flow → 转发内层 out_schema 给该子 flow（receiveLLMResult）
          - ident 既非自身、也未命中子 flow → 打印错误日志

        data 约定为 flow_llm_request 向上转发时的封装形态：{"ident": <目标 ident>, "llm_out": <...>}，
        每层路由消费一层 ident，逐层下传内层 out_schema；最内层叶子无 ident，由该层 flow 自己处理。

        Args:
            data: 输入数据 map（含 ident / out_schema）
        """
        # 先打印收到的数据
        if isinstance(data, dict):
            logger.info(
                "[AEFlow:%s][%s] receiveLLMResult 收到:\n%s",
                self.ident, self.title,
                json.dumps(data, ensure_ascii=False, indent=2),
            )
        else:
            logger.info("[AEFlow:%s][%s] receiveLLMResult 收到: %r", self.ident, self.title, data)
        if not isinstance(data, dict):
            logger.error("[AEFlow:%s] 收到的数据非 map，无法解析: %r", self.ident, data)
            return

        # 取 ident，通过 ident 获取子 flow
        ident = data.get("ident")
        flow = self._flows.get(ident) if ident is not None else None

        # ident 命中自身：本层处理
        if ident == self.ident:
            self.flow_receive_llm(data.get("llm_out"))
            return

        # ident 命中子 flow：转发内层 out_schema 给该子 flow
        if flow is not None:
            flow.receiveLLMResult(data.get("llm_out"))
            return

        # ident 既非自身、也未命中子 flow：打印错误日志
        logger.error(
            "[AEFlow:%s][%s] ident=%r 无法命中（既非自身也未匹配子 flow），忽略: %r",
            self.ident, self.title, ident, data,
        )

    def flow_receive_llm(self, out_schema: "Optional[dict]") -> None:
        """
        收到经 receiveLLMResult 路由到自身、已解析出的 out_schema 数据。

        按 out_schema 内的 status 字段分发到对应处理方法（每个方法同步状态为该 status 并处理）：
          - default    → flow_receive_default     （同步为 default）
          - processing → flow_receive_processing  （同步为 processing）
          - complete   → flow_receive_complete    （同步为 complete）

        out_schema 内无 status 字段、或 status 不匹配已知状态时，打印错误信息并忽略。

        子类覆写各状态方法以处理收到的数据，而非覆写本方法。

        Args:
            out_schema: 从输入 map 中解析出的 out_schema 数据（含 status 字段）
        """
        status = out_schema.get("status") if isinstance(out_schema, dict) else None
        if status == AEFlowStatus.default.value:
            self.flow_receive_default(out_schema)
        elif status == AEFlowStatus.processing.value:
            self.flow_receive_processing(out_schema)
        elif status == AEFlowStatus.complete.value:
            self.flow_receive_complete(out_schema)
        else:
            logger.error(
                "[AEFlow:%s][%s] out_schema 内 status=%r 无效或缺失，忽略: %r",
                self.ident, self.title, status, out_schema,
            )

    def flow_receive_default(self, out_schema: "Optional[dict]") -> None:
        """
        status=default：收到结果数据。状态由子类（业务侧）自行处理，基类默认不变更 status。
        """
        logger.info("[AEFlow:%s][%s] 阶段=default", self.ident, self.title)

    def flow_receive_processing(self, out_schema: "Optional[dict]") -> None:
        """
        status=processing：收到结果数据。状态由子类（业务侧）自行处理，基类默认不变更 status。
        """
        logger.info("[AEFlow:%s][%s] 阶段=processing", self.ident, self.title)

    def flow_receive_complete(self, out_schema: "Optional[dict]") -> None:
        """
        status=complete：收到结果数据，并通过 delegate.flow_complete 通知返回。
        """
        logger.info("[AEFlow:%s][%s] 阶段=complete", self.ident, self.title)
        if self.delegate is not None:
            self.delegate.flow_complete(out_schema, AEFlowStatus.complete)

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

        校验 delegate 后，将当前 status 注入内层 out_schema，再用 ident / title 包装
        payload.out_schema 向上转发（回程按 ident 路由回本 flow）。

        Args:
            payload: AELLMPayload 结构体

        Raises:
            RuntimeError: delegate 未设置时
        """
        if self.delegate is None:
            raise RuntimeError("AEFlow delegate 未设置，无法发送 LLM 请求")
        # 将当前 status 注入内层 out_schema（作为内容字段，非路由信封字段）
        if isinstance(payload.out_schema, dict):
            payload.out_schema["status"] = self.status.value
            
        payload.out_schema = {
            "ident": self.ident,
            "title": self.title,
            "llm_out": payload.out_schema,
        }
        self.delegate.flow_llm_request(payload)

    # ==================== AEFlowDelegate 实现 ====================

    def flow_llm_request(self, payload: "AELLMPayload") -> None:
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
        self.delegate.flow_llm_request(payload)

    def flow_complete(self, result: dict, flowStatus: "AEFlowStatus") -> None:
        """
        Flow 完成通知：仅处理 complete，按 result.ident 路由结果数据。

        - ident == self.ident → 本层接收（receive_flow_result）
        - ident 命中 _flows 内子 flow → 转发给该子 flow（receive_flow_result）

        非 complete 状态（default / processing）忽略并记录告警。

        Args:
            result: 完成 flow 的结果数据（含 ident）
            flowStatus: 完成 flow 的状态
        """
        if flowStatus != AEFlowStatus.complete:
            logger.warning(
                "[AEFlow:%s][%s] flow_complete 仅处理 complete，当前 %s，忽略",
                self.ident, self.title, flowStatus,
            )
            return
        ident = result.get("ident") if isinstance(result, dict) else None
        flow = self._flows.get(ident) if ident is not None else None
        # ident 命中自身：本层接收
        if ident == self.ident:
            self.receive_flow_result(result.get("llm_out"))
            return
        # ident 命中子 flow：转发内层数据给该子 flow
        if flow is not None:
            flow.receive_flow_result(result.get("llm_out"))
            return

    def receive_flow_result(self, out_schema: "Optional[dict]") -> None:
        """
        收到经 flow_complete 路由到自身的结果数据。

        读取 out_schema.answer，拼装 AELLMPayload：
          - role.system:  self.title
          - role.system:  self.responsibility
          - role.assistant: answer
          - role.user:    根据自己的职责条理地整理结论
        按本 flow 的 output 结构作为 out_schema 约束，发送交由 LLM 生成。

        Args:
            out_schema: 结果数据（含 answer 字段）
        """
        self.status = AEFlowStatus.complete
        answer = out_schema.get("answer") if isinstance(out_schema, dict) else None
        logger.info("[AEFlow:%s][%s] receive_flow_result 收到 answer=%r", self.ident, self.title, answer)
        messages = []
        if self.title:
            messages.append({"role": AERole.SYSTEM.value, "content": self.title})
        if self.responsibility:
            messages.append({"role": AERole.SYSTEM.value, "content": self.responsibility})
        messages.append({"role": AERole.ASSISTANT.value, "content": answer or ""})
        messages.append({"role": AERole.USER.value, "content": self.input.content if self.input else ""})
        payload = AELLMPayload(
            messages=messages,
            out_schema=self.output.out_schema if self.output else {},
        )
        self.send_llm_payload(payload)
