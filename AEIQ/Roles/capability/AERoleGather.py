"""AERoleGather - 背景确认能力 mixin。

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


class AERoleGatherFunction(AEFunctional):
    """背景确认回包功能性方法名。"""
    receiveContextNeeded = "receiveContextNeeded"


class AERoleGather(AERole):
    """背景确认能力 mixin：以能力+目标判定是否需要背景确认，需要则派发子 flow 执行背景确认（并行）。"""

    # 以当前能力与确认目标，请求 LLM 判定是否需要背景确认（true/false）
    def requestContextNeeded(self) -> None:
        target = self.input.get_target() if self.input is not None else ""
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
                "根据下方【目标】及现有信息，识别解决此问题尚未明确的必要背景信息，"
                "在 target 中生成一个系统可自行完成的单一目标以获取该信息。\n"
                "要求：\n"
                "- 若已提供角色与能力范围，基于之判定所需背景；否则基于目标本身判定\n"
                "- target 必须是系统可自行完成的目标（通过脚本/API/技术手段获取），不得是疑问、提问或要求用户交互，不得对目标或问题提出疑问或质疑\n"
                "- 涉及用户上下文信息时，用技术手段获取（如 IP 定位获取地理位置、系统命令获取环境信息等），除需用户授权的权限问题外\n"
                "- 若问题所需信息已完整准确，target 留空\n"
                "\n"
                "【目标】\n" + target
            ),
        })
        flow_out = self.generateFlowOutput(AERoleGatherFunction.receiveContextNeeded)
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
            self._orchestrate()  # 无 target，不需要背景确认，继续决策
            return True
        from Roles.AEOrchestrator import AEOrchestrator
        sub = AEOrchestrator(
            flowOutput=AEFlowOutput(ident=self.ident, out_schema={AE_CONTENT: llm_generate("背景确认结果")}),
        )
        sub.update_flow_input(AEFlowInput(content=target, ident=sub.ident, role=self.role.role if self.role is not None else None))
        sub.born_action = self.born_action
        self.add_flow(sub)
        sub.on_flow_start()
        logger.info("[%s][d=%s] 已派发背景确认子 flow", self.title, self.deepth)
        return True

    # 背景确认结果由 receive_flow_complete 统一记录 subflow_result，不再需要 contextComplete 回调
