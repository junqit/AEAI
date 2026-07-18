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

    expert = "expert"
    """专家（Expert）

    意义：
        针对当前用户问题，由 AEExpertAssistant 动态创建的领域专家。是整个 Flow
        协作链路的「总指挥」，负责理解问题、拆解目标、调度下游角色并整合最终产出。

    工作范围：
        1. 解析用户问题，明确问题领域与解决目标；
        2. 将目标按维度 / 目录拆解为若干可独立完成的子目标，分派给各 workgroup；
        3. 为每个 workgroup 提供领域背景、约束与验收标准；
        4. 汇总各 workgroup 的产出，必要时进行二次编排或补充；
        5. 对外输出统一、连贯的最终结果，并对整体质量负责。
    """

    workgroup = "workgroup"
    """工作组（Work Group）

    意义：
        承接专家分派的「单一维度 / 目录」目标，是该维度内的执行单元（AEWorkGroup，
        继承 AEFlow）。各工作组相互独立、可并行，互不阻塞。

    工作范围：
        1. 接收并理解本工作组负责的维度目标（FlowInput.content 即该维度目标）；
        2. 将维度目标进一步分解为具体可执行的子任务，分派给 employee；
        3. 协调组内员工的执行顺序与依赖，收集并整合组内产出；
        4. 仅关注本维度，不跨界干涉其他工作组，保证并行独立性；
        5. 向专家输出本维度的结构化结果。
    """

    employee = "employee"
    """员工（Employee）

    意义：
        工作组内执行具体子任务的最小作业单元，直接调用 LLM / Tools 完成原子化工作。

    工作范围：
        1. 接收工作组下发的单一明确子任务及其上下文；
        2. 调用模型或工具完成该子任务（如检索、分析、生成、转换等）；
        3. 产出可直接被工作组整合的结构化结果；
        4. 不做跨任务、跨维度的规划与决策，聚焦单点执行；
        5. 遇到不明确处向上回传给所属工作组，由工作组或专家裁决。
    """

    reviewer = "reviewer"
    """评审者（Reviewer）

    意义：
        独立于执行链路的质量把关角色，对专家 / 工作组 / 员工的产出进行审查、
        验收与纠偏，确保最终结果满足用户意图与验收标准。

    工作范围：
        1. 依据验收标准对产出进行正确性、完整性、一致性检查；
        2. 识别事实错误、逻辑漏洞、遗漏维度与越界内容；
        3. 对不合格产出给出具体修改意见并要求返工，或判定通过；
        4. 必要时推动多轮迭代，直到产出收敛达标；
        5. 不替代执行角色产出内容，仅行使审查与一票否决 / 通过权。
    """


@dataclass(frozen=True)
class RoleParamInfo:
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
            "title": self.title,
            "responsibility": self.responsibility,
        }


# 各角色默认参数信息注册表：AEFlowRole -> RoleParamInfo
# 仅定义角色能力（title / responsibility），与 AEFlow.role_brief 组装口径一致
ROLE_PARAMS: Dict[AEFlowRole, RoleParamInfo] = {
    AEFlowRole.expert: RoleParamInfo(
        role=AEFlowRole.expert,
        title="领域专家",
        responsibility="整体规划与最终产出收口",
    ),
    AEFlowRole.workgroup: RoleParamInfo(
        role=AEFlowRole.workgroup,
        title="工作组",
        responsibility="单一维度目标的完成，可由多名员工协作",
    ),
    AEFlowRole.employee: RoleParamInfo(
        role=AEFlowRole.employee,
        title="员工",
        responsibility="单一的流水线工作",
    ),
    AEFlowRole.reviewer: RoleParamInfo(
        role=AEFlowRole.reviewer,
        title="评审者",
        responsibility="产出审查与验收",
    ),
}


def get_role_param(role: AEFlowRole) -> RoleParamInfo:
    """按 AEFlowRole 取其默认参数信息；未注册时抛出 KeyError。"""
    return ROLE_PARAMS[role]
