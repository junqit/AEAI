"""
AEFlowDelegate - Flow 内部信息向外流转的委托协议 + AEFlowCompletEvent 事件 + AEFlowDelegateImpl 实现。

Flow 在执行过程中通过该 Delegate 与外部（如 WorkFlow 运行器 / ContextManager）交互：
  1. flow_llm_request                发送 AELLMPayload 调用 LLM
  2. flow_complete           Flow 完成，按 input_schema 结构返回 map
  3. flow_add_next_flow      添加下一个待执行的子 flow

任何类只要实现以下方法即视为符合协议，无需继承。

AEFlowDelegateImpl 为协议方法的静态实现（不实例化、不作基类），调用方（AEFlow）
在薄包装方法中传入自身实例 flow，由本类完成具体逻辑。
"""
import json
import logging
from enum import Enum
from typing import Protocol, TYPE_CHECKING, runtime_checkable, Optional

from .AEFlowOutput import AE_LLM_OUT
from .AEFlowInfo import AE_IDENT, AE_ANSWER, AEFlowStatus
from .AEFlowInput import AEFlowInput
from .AEFlowInterfaceImpl import AEFlowInterfaceImpl
from Context.Context.AELLMPayload import AELLMPayload
from Excutor.AERuntimeExcutor import AEFunctional
from Roles.AERole import AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT

if TYPE_CHECKING:
    from .AEFlowInterface import AEFlowInterface

logger = logging.getLogger(__name__)


class AEFlowCompletEvent(str, Enum):
    """Flow 完成事件（delegate.flow_complete 传入）：区分完成后的后续动作"""
    default = "default"            # 完成回到默认（普通完成）
    startFlow = "startFlow"        # 完成并启动下一个 flow
    error = "error"                # 完成但出现错误


@runtime_checkable
class AEFlowDelegate(Protocol):
    """Flow 委托协议：Flow 内部信息向外流转的出口"""

    def flow_llm_request(self, payload: 'AELLMPayload') -> None:
        """
        发送 AELLMPayload 结构体调用 LLM（无返回值）。

        Args:
            payload: AELLMPayload 结构体
        """
        ...

    def flow_complete(self, result: dict, event: 'AEFlowCompletEvent') -> None:
        """
        Flow 完成通知：result 为完成 flow 的元信息（map），event 为完成事件。

        Args:
            result: 完成 flow 的元信息 map（含 ident）
            event: 完成事件（AEFlowCompletEvent.default / startFlow）
        """
        ...

    def flow_add_next_flow(self, flow: 'AEFlowInterface') -> None:
        """
        添加下一个待执行的子 flow。

        Args:
            flow: 待添加的子 flow，须符合 AEFlowInterface 协议
        """
        ...


class AEFlowDelegateImpl:
    """AEFlowDelegate 协议方法实现（静态工具类，不实例化）。调用方传入 AEFlow 实例 flow。"""

    @staticmethod
    def flow_add_next_flow(flow, next_flow) -> None:
        """添加下一个待执行的子 flow：将其作为子 flow 加入（addFlow），成为 nextFlow 候选。

        加入后由父 flow 的 receive_flow_result 在适当时机 startFlow 启动（input 取上游结果）。

        Args:
            flow: 调用方 AEFlow 实例（delegate / 父 flow）
            next_flow: 待添加的子 flow
        """
        AEFlowInterfaceImpl.addFlow(flow, next_flow)
        logger.info(
            "[AEFlow:%s][%s] flow_add_next_flow 添加子 flow: ident=%s",
            flow.ident, flow.title, next_flow.ident,
        )

    @staticmethod
    def flow_llm_request(flow, payload: "AELLMPayload") -> None:
        """
        发送 AELLMPayload 调用 LLM（无返回值）。

        AEFlow 自身不持有 LLM 客户端，真实发送由外层 delegate（具体 AEFlowDelegate 实现，
        如 AENetRouteCenter 适配器）完成。本方法校验 delegate 后，用当前 flow 的 ident / title
        包装 payload.out_schema，再向上转发（回程按 ident 路由回本 flow）。

        Args:
            flow: 调用方 AEFlow 实例
            payload: AELLMPayload 结构体

        Raises:
            RuntimeError: delegate 未设置时
        """
        if flow.delegate is None:
            raise RuntimeError("AEFlow delegate 未设置，无法发送 LLM 请求")
        # 用当前 flow 的 ident / title 包装 payload.out_schema
        payload.out_schema = {
            AE_IDENT: flow.ident,
            "title": flow.title,
            AE_LLM_OUT: payload.out_schema,
        }
        flow.delegate.flow_llm_request(payload)

    @staticmethod
    def flow_complete(flow, result: dict, event: "AEFlowCompletEvent") -> None:
        """
        Flow 完成通知：按 event 区分处理。

        - default：按 result.ident 路由结果数据（ident 命中自身 → receive_flow_result；
          命中子 flow → 转发给该子 flow 的 receive_flow_result）。
        - startFlow：从 subFlows 按 result.ident 取出子 flow 并 startFlow（input 取 result 的 AE_ANSWER）。
        - error：完成但出错，仅记录，不路由、不启动。

        Args:
            flow: 调用方 AEFlow 实例
            result: 完成 flow 的结果数据（含 ident）
            event: 完成事件（AEFlowCompletEvent.default / startFlow / error）
        """
        ident = result.get(AE_IDENT) if isinstance(result, dict) else None
        logger.info(
            "[recv][AEFlow:%s][%s] flow_complete event=%s ident=%r, result:\n%s",
            flow.ident, flow.title, event, ident, json.dumps(result, ensure_ascii=False, indent=2, default=str),
        )
        # startFlow：从 subFlows 按 ident 取出子 flow 并启动（input 取 result 的 AE_ANSWER）
        if event == AEFlowCompletEvent.startFlow:
            sub = flow._flows.get(ident) if ident is not None else None
            if sub is not None:
                answer = result.get(AE_ANSWER) if isinstance(result, dict) else None
                sub.startFlow(AEFlowInput(content=answer or ""))
                return
            logger.warning(
                "[AEFlow:%s][%s] startFlow 未命中子 flow: ident=%r",
                flow.ident, flow.title, ident,
            )
            return
        # error：完成但出错，仅记录，不路由、不启动
        if event == AEFlowCompletEvent.error:
            logger.warning(
                "[AEFlow:%s][%s] error 事件，忽略结果: ident=%r",
                flow.ident, flow.title, ident,
            )
            return
        # default：按 ident 路由结果数据——命中自身 → 交 receive_flow_result
        if ident == flow.ident:
            AEFlowDelegateImpl.receive_flow_result(flow, result)
            return
        # ident 命中子 flow：转发结果数据给该子 flow
        sub = flow._flows.get(ident) if ident is not None else None
        if sub is not None:
            AEFlowDelegateImpl.receive_flow_result(sub, result.get(AE_LLM_OUT))
            return
        logger.warning(
            "[AEFlow:%s][%s] ident=%r 既非自身也未命中子 flow，忽略: %r",
            flow.ident, flow.title, ident, result,
        )

    @staticmethod
    def receive_flow_result(flow, out_schema: "Optional[dict]") -> None:
        """
        收到经 flow_complete 路由到自身、确认由本 flow 处理的结果数据。

        判断所有子 flow 是否全部 complete：
        - 未全部 complete：把 AE_ANSWER 内容组装成 flowInput，交给首个 default 状态子 flow startFlow
        - 全部 complete：汇总所有子 flow 的 outResult 交 LLM 生成最终答案

        Args:
            flow: 调用方 AEFlow 实例
            out_schema: 结果数据（含 AE_ANSWER 字段）
        """
        answer = out_schema.get(AE_ANSWER) if isinstance(out_schema, dict) else None
        # 判断所有子 flow 是否全部 complete
        all_complete = all(f.status == AEFlowStatus.complete for f in flow._flows.values())
        if not all_complete:
            AEFlowDelegateImpl._advance_next_flow(flow, answer)
            return

        AEFlowDelegateImpl._summarize_to_llm(flow)

    @staticmethod
    def _advance_next_flow(flow, answer: Optional[str]) -> None:
        """未全部 complete：把 answer 组装成 flowInput，交给首个 default 状态子 flow startFlow。"""
        flow_input = AEFlowInput(content=answer or "")
        next_flow = flow.nextFlow()
        if next_flow is not None:
            next_flow.startFlow(flow_input)
        else:
            logger.warning(
                "[AEFlow:%s][%s] 未全部 complete 但无 default 状态子 flow，无法继续",
                flow.ident, flow.title,
            )

    @staticmethod
    def _summarize_to_llm(flow) -> None:
        """全部 complete：汇总所有子 flow 的 outResult 放入 messages，交 LLM 生成最终答案。

        问题已由上游（如 AERefiner）具象化，此处不再带原始 input.content。
        """
        flow_out = flow.flowOutput(AEFunctional.flow_receive_complete)
        messages = []
        role_brief = flow.role_brief
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        # 把所有子 flow 的 outResult 总结内容放入 messages
        for f in flow._flows.values():
            if f.outResult is not None:
                messages.append({
                    AE_ROLE: AEConentRole.SYSTEM.value,
                    AE_CONTENT: f.outResult_summary,
                })
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: f"以上内容中，{AE_USER_QUESTION_PREFIX}为用户问题；请基于所有提供的回答仔细思考，针对该用户问题输出结论",
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        flow.send_llm_payload(payload)
