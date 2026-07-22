"""
AEFlowDelegate - Flow 内部信息向外流转的委托协议 + AEFlowCompletEvent 事件 + AEFlowDelegateImpl 实现。

Flow 在执行过程中通过该 Delegate 与外部（如 WorkFlow 运行器 / ContextManager）交互：
  1. receive_flow_llm_request                发送 AELLMPayload 调用 LLM
  2. receive_flow_complete           Flow 完成，按 input_schema 结构返回 map
  3. receive_add_flow      添加下一个待执行的子 flow

任何类只要实现以下方法即视为符合协议，无需继承。

AEFlowDelegateImpl 为协议方法的实例实现（mixin），由 AEFlow 继承获得这些方法，
无需再在 AEFlow 中写转调包装。方法内部以 self 引用所属 flow。
"""
import json
import logging
from enum import Enum
from typing import Protocol, TYPE_CHECKING, runtime_checkable, Optional

from .AEFlowOutput import AE_LLM_OUT
from .AEFlowInfo import AE_IDENT, AE_TITLE, AE_ANSWER, AEFlowStatus
from .AEFlowInput import AEFlowInput
from Context.Context.AELLMPayload import AELLMPayload
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.AERole import AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT

if TYPE_CHECKING:
    from .AEFlowInterface import AEFlowInterface

logger = logging.getLogger(__name__)


class AEFlowCompletEvent(str, Enum):
    """Flow 完成事件（delegate.receive_flow_complete 传入）：区分完成后的后续动作"""
    default = "default"            # 完成回到默认（普通完成）
    startFlow = "startFlow"        # 完成并启动下一个 flow
    error = "error"                # 完成但出现错误


@runtime_checkable
class AEFlowDelegate(Protocol):
    """Flow 委托协议：Flow 内部信息向外流转的出口"""

    def receive_flow_llm_request(self, payload: 'AELLMPayload') -> None:
        """
        发送 AELLMPayload 结构体调用 LLM（无返回值）。

        Args:
            payload: AELLMPayload 结构体
        """
        ...

    def receive_flow_complete(self, result: dict, event: 'AEFlowCompletEvent') -> None:
        """
        Flow 完成通知：result 为完成 flow 的元信息（map），event 为完成事件。

        Args:
            result: 完成 flow 的元信息 map（含 ident）
            event: 完成事件（AEFlowCompletEvent.default / startFlow）
        """
        ...

    def receive_add_flow(self, flow: 'AEFlowInterface') -> None:
        """
        添加下一个待执行的子 flow。

        Args:
            flow: 待添加的子 flow，须符合 AEFlowInterface 协议
        """
        ...


class AEFlowDelegateImpl(AEFlowDelegate):
    """AEFlowDelegate 协议方法的实例实现（mixin），由 AEFlow 继承获得这些方法。

    显式继承 AEFlowDelegate 协议，声明本类提供 receive_flow_llm_request /
    receive_add_flow / receive_flow_complete 三个协议方法（其余 receive_flow_result /
    _summarize_to_llm 为内部辅助方法）。方法内以 self 引用所属 flow（ident / title /
    _flows / delegate / nextFlow / flowOutput / role_brief / send_llm_payload 等均由
    AEFlow 及其基类提供）。
    """

    def receive_add_flow(self, next_flow) -> None:
        """添加下一个待执行的子 flow：将其作为子 flow 加入（addFlow），成为 nextFlow 候选。

        加入后由父 flow 的 receive_flow_result 在适当时机 startFlow 启动（input 取上游结果）。

        Args:
            next_flow: 待添加的子 flow
        """
        self.addFlow(next_flow)
        logger.info(
            "[AEFlow:%s][%s] receive_add_flow 添加子 flow: ident=%s",
            self.ident, self.title, next_flow.ident,
        )

    def receive_flow_llm_request(self, payload: "AELLMPayload") -> None:
        """
        发送 AELLMPayload 调用 LLM（无返回值）。

        AEFlow 自身不持有 LLM 客户端，真实发送由外层 delegate（具体 AEFlowDelegate 实现，
        如 AENetRouteCenter 适配器）完成。本方法校验 delegate 后，用当前 flow 的 ident / title
        包装 payload.out_schema，再向上转发（回程按 ident 路由回本 flow）。

        Raises:
            RuntimeError: delegate 未设置时
        """
        if self.delegate is None:
            raise RuntimeError("AEFlow delegate 未设置，无法发送 LLM 请求")
        # 用当前 flow 的 ident / title 包装 payload.out_schema
        payload.out_schema = {
            AE_IDENT: self.ident,
            AE_TITLE: self.title,
            AE_LLM_OUT: payload.out_schema,
        }
        self.delegate.receive_flow_llm_request(payload)

    def receive_flow_complete(self, result: dict, event: "AEFlowCompletEvent") -> None:
        """
        Flow 完成通知：按 event 区分处理。

        - default：按 result.ident 路由结果数据（ident 命中自身 → receive_flow_result；
          命中子 flow → 转发给该子 flow 的 receive_flow_result）。
        - startFlow：从 subFlows 按 result.ident 取出子 flow 并 startFlow（input 取 result 的 AE_ANSWER）。
        - error：完成但出错，仅记录，不路由、不启动。

        Args:
            result: 完成 flow 的结果数据（含 ident）
            event: 完成事件（AEFlowCompletEvent.default / startFlow / error）
        """
        ident = result.get(AE_IDENT) if isinstance(result, dict) else None
        logger.info(
            "[recv][AEFlow:%s][%s] receive_flow_complete event=%s ident=%r, result:\n%s",
            self.ident, self.title, event, ident, json.dumps(result, ensure_ascii=False, indent=2, default=str),
        )
        # startFlow：从 subFlows 按 ident 取出子 flow 并启动（input 取 result 的 AE_ANSWER）
        if event == AEFlowCompletEvent.startFlow:
            sub = self._flows.get(ident) if ident is not None else None
            if sub is not None:
                answer = result.get(AE_ANSWER) if isinstance(result, dict) else None
                sub.startFlow(AEFlowInput(content=answer or ""))
                return
            logger.warning(
                "[AEFlow:%s][%s] startFlow 未命中子 flow: ident=%r",
                self.ident, self.title, ident,
            )
            return
        # error：完成但出错，仅记录，不路由、不启动
        if event == AEFlowCompletEvent.error:
            logger.warning(
                "[AEFlow:%s][%s] error 事件，忽略结果: ident=%r",
                self.ident, self.title, ident,
            )
            return
        # default：按 ident 路由结果数据——命中自身 → 交 receive_flow_result
        if ident == self.ident:
            self.receive_flow_result(result)
            return
        # ident 命中子 flow：转发结果数据给该子 flow
        sub = self._flows.get(ident) if ident is not None else None
        if sub is not None:
            sub.receive_flow_result(result.get(AE_LLM_OUT))
            return
        logger.warning(
            "[AEFlow:%s][%s] ident=%r 既非自身也未命中子 flow，忽略: %r",
            self.ident, self.title, ident, result,
        )

    def receive_flow_result(self, out_schema: "Optional[dict]") -> None:
        """
        收到经 receive_flow_complete 路由到自身、确认由本 flow 处理的结果数据。

        - 有 default 子 flow：启动下一个 default 子 flow（异步执行）
        - 仅当所有子 flow 均已完成时，才进入 _summarize_to_llm 汇总；否则等待剩余子 flow，
          不在每次子完成时都执行汇总逻辑。

        Args:
            out_schema: 结果数据（含 AE_ANSWER 字段）
        """
        answer = out_schema.get(AE_ANSWER) if isinstance(out_schema, dict) else None
        # 先判断是否全部完成并汇总，再 startFlow 下一个子 flow。顺序不可颠倒：
        # 脚本等同步完成的子 flow 会让 startFlow 嵌套触发后续 receive_flow_result；
        # 若先 startFlow 再判断，递归回溯时每层都会重复判断 all(complete)（此时已全完成）
        # 导致重复汇总。先判断、再 startFlow，则只有最后一个子 flow 完成时汇总一次。
        if all(f.status == AEFlowStatus.complete for f in self._flows.values()):
            self._summarize_to_llm()
            return
        next_flow = self.nextFlow()
        if next_flow is not None:
            next_flow.startFlow(AEFlowInput(content=answer or ""))

    def _summarize_to_llm(self) -> None:
        """收集所有子 flow 的 outResult 放入 messages，交 LLM 做结构性整合输出。

        注意：并非"提炼最终结论"，而是把各子 flow 的全部信息结构性整合、保留细节、
        去冗余去重后输出（见下方 user 指令）。仅在所有子 flow 全部 complete 时由
        receive_flow_result 调用，故进入本方法即可直接发送。重复触发的根因（子 flow
        多发导致其 flow_receive_complete 多次通知本层）已在 AEFlow.flow_receive_complete
        用 status==complete 幂等闸阻断。
        """
        logger.info(
            "[AEFlow:%s][%s] _summarize_to_llm: 子 flow 全部完成 %d/%d，发送结构性整合请求",
            self.ident, self.title, len(self._flows), len(self._flows),
        )
        flow_out = self.flowOutput(AEFunctional.flow_receive_complete)
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        # 把所有子 flow 的 outResult 总结内容放入 messages（作为 assistant 回答）
        for f in self._flows.values():
            if f.outResult is not None:
                try:
                    summary = f.outResult_summary()
                    messages.append({
                        AE_ROLE: AEConentRole.ASSISTANT.value,
                        AE_CONTENT: summary,
                    })
                except Exception as e:
                    logger.error("[AEFlow:%s] _summarize 子 flow[%s] outResult_summary 异常: %s", self.ident, f.ident, e, exc_info=True)
            else:
                logger.warning("[AEFlow:%s] _summarize 子 flow[%s] outResult is None, 跳过, status=%s", self.ident, f.ident, f.status)
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "请将以上各子 flow 的结果进行结构性整合输出：保留全部细节，不得简化、概括或丢弃任何信息；"
                "对冗余、重复的内容去重；以结构化形式呈现完整信息，而非提炼最终结论。"
            ),
        })

        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)
