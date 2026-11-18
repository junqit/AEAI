"""AERoleContext - 背景确认能力 mixin。

以当前能力（title+responsibility）与确认目标（input.goal）判断是否需要背景确认：
  requestContextNeeded → receiveContextNeeded：请求 LLM 判定「需要 / 不需要」。
需要时派发一个新子 flow（AEOrchestrator）执行背景确认，并设 completeIdent=contextComplete；
子 flow 完成时由 contextComplete 接收结果并存入 flow_context.background，
再经 _orchestrate 推进主流程。不需要时直接 _orchestrate。
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
                "基于当前角色与能力，根据下方【目标】及现有信息，识别解决此问题尚未明确的必要背景信息，"
                "在 target 中生成一个准确的单一目标（prompt）以获取该信息。\n"
                "要求：\n"
                "- 目标仅用于提供必要背景信息，不解决原问题，与当前用户无关；\n"
                "- 目标须可完成：信息在上下文存在则提取，不存在则明确如何通过网络查询等方式获取；\n"
                "- 若问题所需信息已完整准确，target 留空。\n"
                "\n"
                "【目标】\n" + goal
            ),
        })
        flow_out = self.generateFlowOutput(AERoleContextFunction.receiveContextNeeded)
        flow_out.set_llm_out({
            "target": llm_generate("获取必要背景信息的单一明确目标（prompt）；无需则留空"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema, temperature=0.3)
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

    # 创建执行背景确认的子 flow（AEOrchestrator）
    def _dispatch_context_flow(self, target: str):
        from Roles.AEOrchestrator import AEOrchestrator  # 懒导入避免循环（AEOrchestrator → AERoleBase → 本模块）
        sub = AEOrchestrator(
            flowOutput=AEFlowOutput(ident=self.ident, out_schema={AE_CONTENT: llm_generate("背景确认结果")}),
        )
        sub.update_flow_input(AEFlowInput(content=target, ident=sub.ident, role=self.role.role if self.role is not None else None))
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
