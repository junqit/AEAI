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
from Assistant.AERole import AERole

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlowInterface import AEFlowInterface
    from Context.AELLMPayload import AELLMPayload


class AEFlowStatus(str, Enum):
    """Flow 执行状态"""
    default = "default"            # 初始状态
    inputSchemed = "inputSchemed"  # input_schema 已设置
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

    def inputSchema(self) -> "Optional[dict]":
        """
        返回当前 flow 的输入数据结构，并用本 flow 的 ident 包装。

        形态：{"ident": <self.ident>, "llm_out": <input_schema>}，
        供父 flow 取作 LLM out_schema，回程按 ident 逐层路由回本 flow。

        Returns:
            Optional[dict]: ident + input_schema 的封装；input_schema 未设置时 out_schema 为 None
        """
        return {"ident": self.ident, "llm_out": self.input_schema}

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
          - default      → flow_receive_default        （→ inputSchemed）
          - inputSchemed → flow_receive_input_schemed  （→ processing）
          - processing   → flow_receive_processing     （→ complete）
          - complete     → flow_receive_complete       （已 complete 不应再收到数据，打印错误）

        子类覆写各状态方法以处理收到的数据，而非覆写本方法。

        Args:
            out_schema: 从输入 map 中解析出的 out_schema 数据
        """
        # 持有收到的 input_schema 结构性数据
        self.input = out_schema
        if self.status == AEFlowStatus.default:
            self.flow_receive_default(out_schema)
        elif self.status == AEFlowStatus.inputSchemed:
            self.flow_receive_input_schemed(out_schema)
        elif self.status == AEFlowStatus.processing:
            self.flow_receive_processing(out_schema)
        else:  # AEFlowStatus.complete
            self.flow_receive_complete(out_schema)

    def flow_receive_default(self, out_schema: "Optional[dict]") -> None:
        """
        status=default：收到的数据即 LLM 生成的 input_schema，存入 self.input_schema，
        将 status 切换为 inputSchemed，并通过 delegate.flow_complete 通知返回。
        子类覆写时调用 super 以保留状态切换与通知。
        """
        logger.info("[AEFlow:%s][%s] 阶段=default → inputSchemed", self.ident, self.title)
        # default 状态收到的即 input_schema（autoConfigInputSchema 生成）
        self.input_schema = out_schema
        self.status = AEFlowStatus.inputSchemed
        if self.delegate is not None:
            self.delegate.flow_complete(self.to_map(), self.status)

    def flow_receive_input_schemed(self, out_schema: "Optional[dict]") -> None:
        """
        status=inputSchemed：接收数据时将 status 切换为 processing，并通过 delegate.flow_complete 通知返回。
        子类覆写时调用 super 以保留状态切换与通知。
        """
        logger.info("[AEFlow:%s][%s] 阶段=inputSchemed → processing", self.ident, self.title)
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

    def autoConfigInputSchema(self, schema: "Optional[dict]" = None) -> None:
        """
        通过 AELLMPayload 请求 LLM 主动生成本 flow 的 input_schema：
        不预设 out_schema（不约束 LLM 按既有结构输出），由 LLM 依据 title 与 responsibility
        主动生成此角色可接收任务的数据结构，回程作为 input_schema 落地。

        Args:
            schema: 输入数据结构（dict）；为 None 时沿用当前 self.input_schema（仅作记录，不下发约束 LLM）
        """
        from Context.AELLMPayload import AELLMPayload
        payload = AELLMPayload(
            messages=[
                {"role": AERole.SYSTEM.value, "content": self.title},
                {"role": AERole.SYSTEM.value, "content": f"当前的职责：{self.responsibility}"},
                {"role": AERole.USER.value, "content": "按当前的内容给出当前功能匹配的输入参数据json格式，不要多余参数"},
            ]
        )
        self.send_llm_payload(payload)

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
        如 AEContextManager 适配器）完成。本方法校验 delegate 后，用当前 flow 的 ident / title
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

        - 命中直接子 flow → 推进当前子 flow 序号，并把 result["outResult"] 传入该子 flow（若有）
        - 未取到 flow → 进行当前自己各个状态的处理：
            - inputSchemed → flow_complete_input_schemed
            - processing   → flow_complete_processing
            - default      → flow_complete_default
            - complete     → flow_complete_complete
        无返回值。

        Args:
            result: 完成 flow 的元信息 map（含 ident / outResult）
            flowStatus: 完成 flow 的状态
        """
        ident = result.get("ident") if isinstance(result, dict) else None
        flow = self._flows.get(ident) if ident else None
        # 命中直接子 flow：推进序号 + 传 outResult（若有）
        if flow is not None:
            self._current_index += 1
            out_result = result.get("outResult")
            if out_result is not None:
                flow.receiveInputSchemaData(out_result)
            return
        # 未取到 flow：进行当前自己各个状态的处理
        if flowStatus == AEFlowStatus.inputSchemed:
            self.flow_complete_input_schemed(result)
        elif flowStatus == AEFlowStatus.processing:
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

    def flow_complete_input_schemed(self, result: dict) -> None:
        """
        status=inputSchemed：完成的 flow（已拿到 input_schema）作为 next_flow。
        把当前 flow 的问题（input）转换成 next_flow.inputSchema() 的结构：
        以当前 flow 的 input 作为 messages，以 next_flow.inputSchema() 作为 out_schema，
        通过 AELLMPayload 发起请求，让 LLM 把当前问题改写/填充为下一 flow 的 input_schema 结构。

        Args:
            result: 完成 flow 的元信息 map（用其 ident 取到 next_flow）
        """
        from Context.AELLMPayload import AELLMPayload
        # 完成的 flow（已拿到 input_schema）作为 next_flow
        next_ident = result.get("ident") if isinstance(result, dict) else None
        next_flow = self._flows.get(next_ident) if next_ident else None
        if next_flow is None:
            logger.warning("[AEFlow:%s] flow_complete_input_schemed 未找到 next_flow(ident=%r)", self.ident, next_ident)
            return
        # 拼 messages：self.input 作为待转换的内容（role=system，标明为待转换内容），
        # role:user 指令引用「上面的内容」转换成要求的数据结构（即 out_schema），形成关联
        payload = AELLMPayload(messages=[
            {"role": AERole.SYSTEM.value, "content": f"需要转换的内容：\n{self.input}"},
            {"role": AERole.USER.value, "content": "把需要转换的内容转换成要求的数据结构"},
        ])
        # 要求的数据结构 = next_flow.inputSchema()
        payload.out_schema = next_flow.inputSchema()
        self.send_llm_payload(payload)

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
