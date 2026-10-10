"""AERoleChoice - 角色选择能力 mixin。

提供 requestRoleChoice / receiveRoleChoice：据已生成的角色名称与解决问题的能力，从全部
角色中选一个其基本能力匹配的，设为当前角色能力（self.role）；空或无效则以错误完成闭环。
"""
import logging

from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.Role.AERoleType import (
    AEFlowRole, ROLE_PARAMS,
    AEConentRole, AE_ROLE,
)
from Roles.Role.AERole import AERole

logger = logging.getLogger(__name__)


class AERoleChoiceFunction(AEFunctional):
    """角色选择的回包功能性方法名。"""
    receiveRoleChoice = "receiveRoleChoice"


class AERoleChoice(AERole):
    """角色选择能力 mixin：据已生成的角色名称与解决问题的能力，从 AEFlowRole 中选一个匹配角色。"""

    def requestRoleChoice(self) -> None:
        """据已生成的角色名称与解决问题的能力，从全部 AEFlowRole 角色中选一个匹配的来处理当前问题。

        角色名称（title）与解决问题的能力（responsibility）已生成；据此从可选 AEFlowRole 角色中
        选一个其基本能力匹配该问题的角色。LLM 返回 AEFlowRole 其中之一。不得拒绝或推诿。
        """
        candidates = list(ROLE_PARAMS.keys())
        question = ((self.input.get_goal() or self.input.get_content()) if self.input is not None else "")
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: (
                "角色选择规则：\n"
                "- 据上述已生成的角色名称与解决问题的能力，从可选角色中选一个其基本能力匹配该问题的角色，不得拒绝或推诿。\n"
                "- 只选一个角色（不拆解为多个工作流），由该角色以其基本能力处理问题。\n"
                "- 简单、可直接作答的知识性问题选 llm；需要网络/实时数据的问题选具备工具能力的角色。"
            ),
        })
        role_lines = []
        for r in candidates:
            info = ROLE_PARAMS.get(r)
            if info is not None:
                role_lines.append(f"- {r.value}（{info.title}）：{info.responsibility}")
            else:
                role_lines.append(f"- {r.value}")
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: "可选角色（名称与基本能力）：\n" + "\n".join(role_lines),
        })
        allowed = [r.value for r in candidates]
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"问题/目标：{question}\n\n"
                f"请从可选角色中选一个其基本能力匹配该问题的角色，输出 JSON 填入 title 字段"
                f"（值为以下角色之一：{', '.join(allowed)}）。"
            ),
        })
        flow_out = self.generateFlowOutput(AERoleChoiceFunction.receiveRoleChoice)
        flow_out.set_llm_out({
            AE_ROLE: llm_generate(f"角色，从可选角色中选一个：{' / '.join(allowed)}"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveRoleChoice(self, data: dict) -> bool:
        """接收选中的角色，设为当前角色能力（self.role）。成功返回 True；无效返回 False（不闭环）。"""
        if not isinstance(data, dict):
            data = {}
        role_str = (data.get(AE_ROLE) or "").strip()
        if role_str.lower().startswith("type:"):
            role_str = role_str.split(":", 1)[1].strip()
        try:
            role_enum = AEFlowRole(role_str)
        except ValueError:
            logger.warning("[%s][d=%s] 未选到有效角色: %r", self.title, self.deepth, role_str)
            return False
        if role_enum not in ROLE_PARAMS:
            logger.warning("[%s][d=%s] 所选角色不在可选范围: %r", self.title, self.deepth, role_str)
            return False
        self.role = ROLE_PARAMS[role_enum]
        logger.info("[%s][d=%s] 选定角色 %s 作为当前角色能力", self.title, self.deepth, role_enum.value)
        return True
