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
            system_parts.append(f"身份：{self.title}")
        if self.responsibility:
            system_parts.append(f"能力范围：{self.responsibility}")
        messages = []
        if system_parts:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: "".join(system_parts)})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "基于当前工作名称与能力范围，根据下方【确认目标】确认完成该目标需要的背景信息。\n"
                "要求：\n"
                "- 若需要额外背景信息，在 target 中给出需要确认的背景资料（只输出需要确认的信息目标）；\n"
                "- 若目标所需信息已明确、无需补充背景，target 留空。\n"
                "\n"
                "【确认目标】\n" + goal
            ),
        })
        flow_out = self.generateFlowOutput(AERoleContextFunction.receiveContextNeeded)
        flow_out.set_llm_out({
            "target": llm_generate("需要确认的背景资料；无需则留空"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.flow_send_llm_request(payload)

    # 接收背景确认；target 有值则派发子 flow（completeIdent=contextComplete），无值直接推进
    def receiveContextNeeded(self, data: dict) -> bool:
        target = ""
        if isinstance(data, dict):
            target = str(data.get("target", "") or "").strip()
        logger.info("[%s][d=%s] 背景确认需求判定: target=%s", self.title, self.deepth, target)
        if not target:
            self.contextComplete(None)  # 无 target 直接调 contextComplete（不经子 flow）
            return True
        sub = self._dispatch_context_flow(target)
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
    def _dispatch_context_flow(self, target: str):
        from Roles.AERoleExcutor import AERoleExcutor  # 懒导入避免循环（AERoleExcutor → AERoleBase → 本模块）
        sub = AERoleExcutor(
            flowOutput=AEFlowOutput(ident=self.ident, out_schema={AE_CONTENT: llm_generate("背景确认结果")}),
        )
        sub.update_flow_input(AEFlowInput(content=target, ident=sub.ident, role=self.role.role if self.role is not None else None))
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
            if result:
                logger.info("[%s][d=%s] 背景确认子 flow 完成，结果=%s", self.title, self.deepth, result)
            elif not result:
                logger.warning("[%s][d=%s] 背景确认子 flow 完成但结果为空", self.title, self.deepth)
        return bool(result)
