"""
AERoleBase - 角色 Flow 基类。

所有角色 Flow 继承本类。角色常量/枚举（AEConentRole / AEFlowRole / ROLE_PARAMS 等）
在 Roles.AERoleType 中；角色选择能力在 Roles.AERoleChoice 中（由需要角色选择/直答的子类
如 AERefiner / AERoleExcutor 显式继承，避免 AERoleBase 基类传递依赖 AERoleExcutor）；
角色信息能力（title / responsibility / rolePrompt 生成）在 Roles.AERoleInformation 中；
问题优化能力（requestOptimizeInput / receiveOptimizeInput）在 Roles.AERoleQuestionOptimize 中，
均由本类继承获得。角色信息属性（title / responsibility / roleGoal / rolePrompt）
由本类 __init__ 持有（非 AEFlow 基类职责）。
结果汇总编排（summarize_to_llm）由 AEIQFlow 实现，本类继承 AEIQFlow 获得。本类另覆写角色上下文
hook（summarize_extend_messages / outResult_summary）提供角色信息——flow 基类不体现 role 信息。
本类仅定义 AERoleBase 角色基类（需 import AEIQFlow，故与常量分文件，避免循环导入）。
"""
import logging
from typing import Optional

from WorkFlows.AEIQFlow import AEIQFlow
from WorkFlows.FlowWork.AEFlowOutput import AEFlowOutput
from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT
from Roles.AERoleType import AERoleParamInfo, AEFlowRole, ROLE_PARAMS, AE_USER_QUESTION_PREFIX, AEConentRole, AE_ROLE
from Roles.AERoleInformation import AERoleInformation
from Roles.AERoleQuestionOptimize import AERoleQuestionOptimize

logger = logging.getLogger(__name__)


class AERoleBase(AERoleInformation, AERoleQuestionOptimize, AEIQFlow):
    """角色 Flow 基类。角色选择能力（AERoleChoice）由需要的子类显式继承；
    角色信息能力（AERoleInformation）与问题优化能力（AERoleQuestionOptimize）由本类继承。
    能力 mixin 列于 AEFlow 之前，确保 cooperative __init__ 链优先经各 mixin 初始化其属性。"""

    roleParamInfo: Optional[AERoleParamInfo] = None

    def roleDescription(self) -> str:
        """角色描述：拼接 ROLE_PARAMS 全部角色的花名册（type / 职称 / 职责），供角色选择等场景使用。

        子类可覆写为仅返回自身角色的描述。
        """
        lines = []
        for role, info in ROLE_PARAMS.items():
            lines.append(f"- type: {role.value}；职称：{info.title}；职责：{info.responsibility}")
        return "\n".join(lines)

    @classmethod
    def _role(cls) -> AEFlowRole:
        """子类返回所属角色枚举（角色定义类覆写；未定义静态角色的 flow 调用将抛错）。"""
        raise NotImplementedError

    @classmethod
    def param_info(cls) -> AERoleParamInfo:
        """返回本角色参数信息（直接取 ROLE_PARAMS，不重定义）。"""
        return ROLE_PARAMS[cls._role()]

    # ==================== 角色上下文 hook（供 summarize_to_llm 调用）====================

    def flow_description(self) -> str:
        """覆写：在基类 [d=deepth] 基础上前置 [role][title]，不存在的项不输出。"""
        parts = []
        if self.title:
            parts.append(f"[{self.title}]")
        if self.role is not None:
            parts.append(f"[{self.role.value}]")
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
        """
        parts = []
        if len(self.title) > 0:
            parts.append(f"你的身份是：{self.title}")
        if len(self.responsibility) > 0:
            parts.append(f"你的能力范围是：{self.responsibility}")
        if len(parts) == 0:
            return ""
        return "".join(parts)

    def outResult_summary(self) -> str:
        """组装上下文与 outResult（回答）为总结内容，供父 flow 汇总。

        - 有 roleGoal（角色 flow 经 receiveOptimizeInput 设置）：
          「{AE_USER_QUESTION_PREFIX}{roleGoal} 我的回答：{answer}」
        - 无 roleGoal：回退到 title 作为上下文，
          「{title} 我的回答：{answer}」，避免只剩裸「我的回答：{answer}」丢失上下文。
        """
        answer = self.outResult.get(AE_CONTENT, "") if isinstance(self.outResult, dict) else ""
        question = self.roleGoal or ""
        if question:
            return f"{AE_USER_QUESTION_PREFIX}{question} 我的回答：{answer}"
        if self.title:
            return f"{self.title} 我的回答：{answer}"
        return f"我的回答：{answer}"
