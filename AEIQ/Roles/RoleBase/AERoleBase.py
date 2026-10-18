"""
AERoleBase - 角色 Flow 基类。

提供角色上下文 hook：role_brief（身份与能力范围）、summarize_extend_messages（汇总扩展消息）、
outResult_summary（上下文与结果总结）、flow_description / flow_complete_info（描述与完成信息）。
"""
import logging
from typing import Optional

from WorkFlows.FlowWork.AEFlow import AEFlow
from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT
from Roles.RoleBase.AERoleType import AERoleParamInfo, ROLE_PARAMS, AEConentRole, AE_ROLE, get_role_iron_law
from Roles.RoleBase.AERoleInformation import AERoleInformation
from Roles.RoleBase.AERoleQuestion import AERoleQuestion
from Roles.RoleBase.AERoleChoice import AERoleChoice
from Roles.Excutor.AERoleWorkflow import AERoleWorkflow

logger = logging.getLogger(__name__)


class AERoleBase(AERoleInformation, AERoleQuestion, AERoleChoice, AERoleWorkflow, AEFlow):
    """角色 Flow 基类：提供角色上下文 hook（role_brief / summarize_extend_messages / outResult_summary 等）。"""

    roleParamInfo: Optional[AERoleParamInfo] = None

    # 拼接全部角色的花名册（type/职称/职责），供角色选择等场景使用
    def roleDescription(self) -> str:
        lines = []
        for role, info in ROLE_PARAMS.items():
            lines.append(f"- type: {role.value}；职称：{info.title}；职责：{info.responsibility}")
        return "\n".join(lines)

    # ==================== 角色上下文 hook（供 summarize_to_llm 调用）====================

    # 覆写：在基类基础上前置 [role][title]，不存在项不输出
    def flow_description(self) -> str:
        parts = []
        if self.title:
            parts.append(f"[{self.title}]")
        if self.role is not None:
            parts.append(f"[{self.role.role.value}]")
        parts.append(super().flow_description())
        return "".join(parts)

    # 把 role_brief 作为 system 消息追加到汇总 messages 头部
    def summarize_extend_messages(self) -> list:
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            return [{AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief}]
        return []

    # 组装身份与能力范围描述，末尾追加角色铁律
    def role_brief(self) -> str:
        parts = []
        if len(self.title) > 0:
            parts.append(f"你的身份是：{self.title}")
        if len(self.responsibility) > 0:
            parts.append(f"你的能力范围是：{self.responsibility}")
        iron_law = get_role_iron_law(self.role.role if self.role is not None else None)
        if iron_law:
            parts.append(iron_law)
        if len(parts) == 0:
            return ""
        return "".join(parts)

    # 组装问题、身份、结果为三段式总结，供父 flow 汇总
    def outResult_summary(self) -> str:
        answer = self.output.outResult or ""
        question = (self.input.get_goal() if self.input is not None else "")
        parts = []
        if question:
            parts.append(question)
        if self.title:
            parts.append(f"以「{self.title}」身份")
        parts.append(f"给出结果：{answer}")
        return "\n".join(parts)

    # 在基类 info 上补 role/deepth/delegate 信息，供树形呈现
    def flow_complete_info(self) -> dict:
        info = super().flow_complete_info()
        role = getattr(self, "role", None)
        if role is not None:
            info["role"] = role.value
        info["deepth"] = self.deepth
        delegate = getattr(self, "delegate", None)
        dep_info = None
        if delegate is not None:
            try:
                dep_info = {
                    "ident": getattr(delegate, "ident", ""),
                    "title": getattr(delegate, "title", "") or "",
                }
            except ReferenceError:  # weakref 已失效
                dep_info = None
        info["dep"] = dep_info
        return info
