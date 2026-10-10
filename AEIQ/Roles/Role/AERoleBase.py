"""
AERoleBase - 角色 Flow 基类。

提供角色上下文 hook：role_brief（身份与能力范围）、summarize_extend_messages（汇总扩展消息）、
outResult_summary（上下文与结果总结）、flow_description / flow_complete_info（描述与完成信息）。
"""
import logging
from typing import Optional

from WorkFlows.AEIQFlow import AEIQFlow
from WorkFlows.FlowWork.AEFlowOutput import AEFlowOutput
from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT
from Roles.Role.AERoleType import AERoleParamInfo, ROLE_PARAMS, AEConentRole, AE_ROLE, get_role_iron_law
from Roles.Role.AERoleInformation import AERoleInformation
from Roles.Role.AERoleQuestion import AERoleQuestion
from Roles.Role.AERoleChoice import AERoleChoice
from Roles.Role.AERoleWorkflow import AERoleWorkflow

logger = logging.getLogger(__name__)


class AERoleBase(AERoleInformation, AERoleQuestion, AERoleChoice, AERoleWorkflow, AEIQFlow):
    """角色 Flow 基类：提供角色上下文 hook（role_brief / summarize_extend_messages / outResult_summary 等）。"""

    roleParamInfo: Optional[AERoleParamInfo] = None

    def roleDescription(self) -> str:
        """角色描述：拼接 ROLE_PARAMS 全部角色的花名册（type / 职称 / 职责），供角色选择等场景使用。

        子类可覆写为仅返回自身角色的描述。
        """
        lines = []
        for role, info in ROLE_PARAMS.items():
            lines.append(f"- type: {role.value}；职称：{info.title}；职责：{info.responsibility}")
        return "\n".join(lines)

    # ==================== 角色上下文 hook（供 summarize_to_llm 调用）====================

    def flow_description(self) -> str:
        """覆写：在基类 [d=deepth] 基础上前置 [role][title]，不存在的项不输出。"""
        parts = []
        if self.title:
            parts.append(f"[{self.title}]")
        if self.role is not None:
            parts.append(f"[{self.role.role.value}]")
        parts.append(super().flow_description())
        return "".join(parts)

    def summarize_extend_messages(self) -> list:
        """覆写汇总扩展消息：把角色身份与能力范围（role_brief）作为 system 消息追加到汇总 messages 头部。

        flow 基类（AEFlow）默认返回空列表、不体现 role 信息；角色上下文由此处提供。
        """
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            return [{AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief}]
        return []

    def role_brief(self) -> str:
        """组装身份与能力范围信息，供 LLM 明确本 flow 的角色定位。

        返回形如「你的身份是：X；你的能力范围是：Y」的描述；对应字段为空时省略对应分句。
        末尾追加按角色能力适配的铁律（get_role_iron_law），替代 AEContextCenter 的 blanket 注入。
        """
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

    def outResult_summary(self) -> str:
        """组装上下文与 outResult（回答）为总结内容，供父 flow 汇总。

        三段式（条件出现、换行分隔），体现实为「以某问题、以某身份、给出结果」的条理：
        - 问题段（有 input.goal 时）：直接以 input.goal 作为问题段
        - 身份段（有 title 时）：「以「{title}」身份」
        - 结果段（必有）：「给出结果：{answer}」
        """
        answer = self.output.outResult or ""
        question = (self.input.get_goal() if self.input is not None else "")
        parts = []
        if question:
            parts.append(question)
        if self.title:
            parts.append(f"以「{self.title}」身份")
        parts.append(f"给出结果：{answer}")
        return "\n".join(parts)

    def flow_complete_info(self) -> dict:
        """覆写：在基类 info 上补角色（role 枚举）、深度（deepth）与 delegate（父 flow）信息，
        供 chat 完成时树形 JSON 呈现角色、层级与归属链。

        基类已有 ident/title/responsibility/question/goal/answer/children；此处补：
        - role：本 flow 所属 AEFlowRole 枚举值（角色层才有，为 None 时省略）；
        - deepth：本 flow 在树中的层级深度（根=1，子=父+1）；
        - dep：delegate（父 flow，弱引用）的 {ident, title}；delegate 为 None
          （根 flow）或 weakref 已失效（ReferenceError）时 dep=None。
        """
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
