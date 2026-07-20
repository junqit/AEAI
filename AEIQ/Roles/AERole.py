from WorkFlows.AEFlowInfo import AE_TITLE
from dataclasses import dataclass
from enum import Enum
from typing import Dict

# LLM 消息 dict 的字段名
AE_ROLE = "role"
AE_CONTENT = "content"

# 用户问题在上下文中的统一标识前缀（含书名号，system 消息 / 摘要引用均用此常量，保持一致）
AE_USER_QUESTION_PREFIX = "「当前用户的问题是：」"


class AEConentRole(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    CONTEXT = "context"


class AEFlowRole(Enum):
    """Flow 角色类型：专家 / 工作组 / 员工 / 评审者

    AEIQ 的 Flow 体系采用「组织化协作」模型：一个用户问题被拆解为多个维度的目标，
    由不同角色分工完成。各角色构成一条「专家 → 工作组 → 员工 → 评审者」的协作链路：

        expert（专家）
          └─ workgroup（工作组）× N（各维度，相互独立、可并行）
               └─ employee（员工）× N（执行具体子任务）
          └─ reviewer（评审者）对产出进行质量把关与收敛

    角色之间通过 FlowInput / FlowOutput 传递上下文与结果，专家负责整体规划与收口，
    评审者负责验收，工作组与员工负责分解与执行。
    """

    expert = "expert"        # 专家
    workgroup = "workgroup"  # 工作组
    employee = "employee"    # 员工
    reviewer = "reviewer"    # 评审者


@dataclass(frozen=True)
class AERoleParamInfo:
    """单个 Flow 角色的参数信息（仅定义角色能力）。

    title / responsibility 直接对应 AEFlow / AEFlowInfo 的同名字段，由 role_brief
    组装为「你的身份是：X；你的能力范围是：Y」供 LLM 明确角色定位。

    Attributes:
        role: 所属 AEFlowRole。
        title: 职称 / 身份定位，写入 Flow.title。
        responsibility: 能力范围，写入 Flow.responsibility。
    """

    role: AEFlowRole
    title: str
    responsibility: str

    def to_map(self) -> dict:
        """返回参数信息的 map 形态（枚举转为字符串，便于日志 / 序列化）。"""
        return {
            "role": self.role.value,
            AE_TITLE: self.title,
            "responsibility": self.responsibility,
        }


# 各角色默认参数信息注册表：AEFlowRole -> AERoleParamInfo
# title / responsibility 仅作简单概括，供 LLM 据角色标识 + 能力大意生成完整 title 与能力
ROLE_PARAMS: Dict[AEFlowRole, AERoleParamInfo] = {
    AEFlowRole.expert: AERoleParamInfo(
        role=AEFlowRole.expert,
        title="领域专家",
        responsibility="统筹规划，对最终产出收口",
    ),
    AEFlowRole.workgroup: AERoleParamInfo(
        role=AEFlowRole.workgroup,
        title="工作组",
        responsibility="完成单一维度目标，可由多名员工协作",
    ),
    AEFlowRole.employee: AERoleParamInfo(
        role=AEFlowRole.employee,
        title="员工",
        responsibility="完成单一流水线工作",
    ),
    AEFlowRole.reviewer: AERoleParamInfo(
        role=AEFlowRole.reviewer,
        title="评审者",
        responsibility="审查并验收产出",
    ),
}


def get_role_param(role: AEFlowRole) -> AERoleParamInfo:
    """按 AEFlowRole 取其默认参数信息；未注册时抛出 KeyError。"""
    return ROLE_PARAMS[role]
