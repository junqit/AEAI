"""
AERoleBase - 角色 Flow 基类。

提供角色上下文 hook：role_brief（身份与能力范围）、flow_description / flow_complete_info（描述与完成信息）。
"""
import logging

from Roles.RoleBase.AERoleType import ROLE_PARAMS, get_role_iron_law
from Roles.RoleBase.AERole import AERole

logger = logging.getLogger(__name__)


class AERoleBase(AERole):
    """角色 Flow hook 基类：提供角色上下文 hook（role_brief / flow_description / flow_complete_info 等）。
    不聚合具体阶段能力——各能力 mixin 由 AEOrchestrator 显式继承。"""

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

    # 组装身份与能力范围描述，末尾追加角色铁律
    def role_brief(self) -> str:
        parts = []
        if len(self.title) > 0:
            parts.append(f"身份：{self.title}")
        if len(self.responsibility) > 0:
            parts.append(f"能力范围：{self.responsibility}")
        iron_law = get_role_iron_law(self.role.role if self.role is not None else None)
        if iron_law:
            parts.append(iron_law)
        if len(parts) == 0:
            return ""
        return "".join(parts)

    # 在基类 info 上补 role/deepth/delegate 信息，供树形呈现
    def flow_complete_info(self) -> dict:
        info = super().flow_complete_info()
        role = self.role
        if role is not None:
            info["role"] = role.value
        info["deepth"] = self.deepth
        delegate = self.delegate
        dep_info = None
        if delegate is not None:
            try:
                dep_info = {
                    "ident": delegate.ident,
                    "title": delegate.title or "",
                }
            except ReferenceError:  # weakref 已失效
                dep_info = None
        info["dep"] = dep_info
        return info
