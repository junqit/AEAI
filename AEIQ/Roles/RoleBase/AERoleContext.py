"""AERoleContext - 背景确认能力 mixin。

以当前能力（title+responsibility）与确认目标（input.goal）判断是否需要背景确认：
  requestContextNeeded → receiveContextNeeded：请求 LLM 判定「需要 / 不需要」。
需要时派发一个新子 flow（AERoleExcutor）执行背景确认，并设 completeIdent=contextComplete；
子 flow 完成时由 contextComplete（定义在 AERoleExcutor）接收结果并存入父 flow 的 input.context，
再经 _proceed_after_context 推进主流程。不需要时直接 _proceed_after_context。
"""
import logging

from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT
from WorkFlows.FlowWork.AEFlowOutput import AEFlowOutput
from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
from Roles.RoleBase.AERole import AERole

logger = logging.getLogger(__name__)


class AERoleContextFunction(AEFunctional):
    """背景确认回包功能性方法名。"""
    receiveContextNeeded = "receiveContextNeeded"


class AERoleContext(AERole):
    """背景确认能力 mixin：以能力+目标判定是否需要背景确认，需要则派发子 flow 执行背景确认（并行）。"""

    # 以当前能力与确认目标，请求 LLM 判定是否需要背景确认（true/false）
    def requestContextNeeded(self) -> None:
        goal = self.input.get_goal() if self.input is not None else ""
        if not goal:
            logger.warning("[%s][d=%s] 无 input.goal，跳过背景确认", self.title, self.deepth)
            return
        # SYSTEM 放角色身份（title+responsibility，不含铁律）
        system_parts = []
        if self.title:
            system_parts.append(f"你的身份是：{self.title}")
        if self.responsibility:
            system_parts.append(f"你的能力范围是：{self.responsibility}")
        messages = []
        if system_parts:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: "".join(system_parts)})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "基于当前工作名称、能力范围与下方【确认目标】，判断是否需要额外的背景信息与上下文确认才能完成该目标。\n"
                "要求：\n"
                "- 仅判断「需要 / 不需要」二者其一；\n"
                "- 目标所需信息已明确、无需补充背景时判「不需要」；"
                "存在缺失参数、外部数据、前置条件等待确认时判「需要」；\n"
                "- 若判「需要」，在 target 中给出需要解决问题的背景资料（只输出需要确认的信息目标）。\n"
                "\n"
                "【确认目标】\n" + goal
            ),
        })
        flow_out = self.generateFlowOutput(AERoleContextFunction.receiveContextNeeded)
        flow_out.set_llm_out({
            "needed": llm_generate("true 或 false：是否需要背景确认"),
            "target": llm_generate("需要解决问题的背景资料，只输出需要确认的信息目标"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.flow_send_llm_request(payload)

    # 接收是否需要背景确认；不需要直接推进，需要则派发子 flow（completeIdent=contextComplete）
    def receiveContextNeeded(self, data: dict) -> bool:
        needed = data.get("needed") if isinstance(data, dict) else False
        target = ""
        if isinstance(data, dict):
            target = str(data.get("target", "") or "").strip()
        logger.info("[%s][d=%s] 背景确认需求判定: needed=%s, target=%s", self.title, self.deepth, needed, target)
        if not needed:
            self._proceed_after_context()
            return True
        goal = self.input.get_goal() if self.input is not None else ""
        sub = self._dispatch_context_flow(goal, target)
        if sub is None:
            logger.warning("[%s][d=%s] 背景确认子 flow 创建失败，跳过", self.title, self.deepth)
            return False
        # 子 flow 完成回包路由回自身（flowOutput.ident=self.ident），由 completeIdent 调 contextComplete
        self.completeIdent = self.registerFunctional("contextComplete")
        self.add_flow(sub)
        sub.on_flow_start()
        logger.info("[%s][d=%s] 已派发背景确认子 flow（completeIdent=contextComplete）", self.title, self.deepth)
        return True

    # 创建执行背景确认的子 flow（AERoleExcutor）；有 target 时针对该确认目标，否则泛化确认
    def _dispatch_context_flow(self, goal: str, target: str = ""):
        from Roles.AERoleExcutor import AERoleExcutor  # 懒导入避免循环（AERoleExcutor → AERoleBase → 本模块）
        if target:
            sub_goal = (
                f"针对目标：\n{goal}\n\n需确认的背景资料：\n{target}"
                if goal else f"需确认的背景资料：\n{target}"
            )
        else:
            sub_goal = (
                f"确认完成以下目标需要哪些背景信息与上下文：\n{goal}"
                if goal else "确认完成当前目标需要哪些背景信息与上下文"
            )
        sub = AERoleExcutor(
            flowOutput=AEFlowOutput(ident=self.ident, out_schema={AE_CONTENT: llm_generate("背景确认结果")}),
        )
        sub.update_flow_input(AEFlowInput(content=sub_goal, ident=sub.ident, role=self.role.role if self.role is not None else None))
        sub.skip_context_confirm = True  # 背景确认子 flow 跳过自身背景确认，避免递归
        return sub

    # 背景确认子 flow 完成回调（completeIdent）：确认结果有无并存入父 flow 的 input.context，返回是否有结果
    def contextComplete(self, flowOutput) -> bool:
        result = ""
        if flowOutput is not None:
            result = getattr(flowOutput, "outResult", "") or ""
            if not result:
                out = getattr(flowOutput, "out_schema", None)
                if isinstance(out, dict):
                    result = out.get(AE_CONTENT, "") or ""
        if result and self.input is not None:
            self.input.add_context("background", result)
            logger.info("[%s][d=%s] 背景确认子 flow 完成，结果已存入 input.context", self.title, self.deepth)
        else:
            logger.warning("[%s][d=%s] 背景确认子 flow 完成但结果为空", self.title, self.deepth)
        return bool(result)
