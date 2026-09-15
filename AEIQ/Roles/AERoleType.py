from WorkFlows.FlowWork.AEFlowInfo import AE_TITLE, AE_RESPONSIBILITY
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List

# LLM 消息 dict 的字段名
AE_ROLE = "role"


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
    task = "task"            # 原子任务（最底层执行单元，不再拆解）
    reviewer = "reviewer"    # 评审者
    llm = "llm"              # LLM 直接作答（不拆解、不执行脚本，直接请求 LLM）
    script = "script"        # 脚本执行（调用预置脚本/工具完成具体操作，不拆解）


# 角色层级有序表（从上到下）：expert > workgroup > employee > task > llm/script
# llm、script 为叶子工具（不可再分解）；expert/workgroup/employee/task 可直接选其下层（含 llm/script）
AE_ROLE_HIERARCHY: List[AEFlowRole] = [
    AEFlowRole.expert, AEFlowRole.workgroup, AEFlowRole.employee, AEFlowRole.task,
    AEFlowRole.llm, AEFlowRole.script,
]

# 叶子角色：不可再分解（不向下拆解）
AE_LEAF_ROLES: set = {AEFlowRole.llm, AEFlowRole.script}


def roles_below(role: AEFlowRole) -> List[AEFlowRole]:
    """返回严格低于 role 的所有角色（按层级从上到下）。

    expert → [workgroup, employee, task, llm, script]；workgroup → [employee, task, llm, script]；
    employee → [task, llm, script]；task → [llm, script]；
    llm/script → []（叶子，不可再分解）。
    """
    if role in AE_LEAF_ROLES:
        return []
    try:
        idx = AE_ROLE_HIERARCHY.index(role)
    except ValueError:
        return []
    return AE_ROLE_HIERARCHY[idx + 1:]


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
            AE_RESPONSIBILITY: self.responsibility,
        }


# 各角色默认参数信息注册表：AEFlowRole -> AERoleParamInfo
# title / responsibility 仅作简单概括，供 LLM 据角色标识 + 能力大意生成完整 title 与能力
ROLE_PARAMS: Dict[AEFlowRole, AERoleParamInfo] = {
    AEFlowRole.expert: AERoleParamInfo(
        role=AEFlowRole.expert,
        title="领域专家",
        responsibility=(
            "统筹整体规划与最终收口，不直接执行。"
            "可做：把用户目标分解为若干独立维度并分配给工作组；所有维度结论到齐后整合为最终交付。"
            "不可做：不直接执行任何维度/流水线/任务（那是 workgroup/employee/task）；不调用模型或脚本产出中间结果。"
        ),
    ),
    AEFlowRole.workgroup: AERoleParamInfo(
        role=AEFlowRole.workgroup,
        title="工作组",
        responsibility=(
            "负责单一维度的拆解与整合，不直接执行。"
            "可做：承接专家分配的某一个维度目标，拆解为若干可独立执行的员工任务，整合本维度结论交回专家。"
            "不可做：不做整体规划与收口（那是 expert）；不跨维度；不直接执行任务（那是 employee/task）。"
        ),
    ),
    AEFlowRole.employee: AERoleParamInfo(
        role=AEFlowRole.employee,
        title="员工",
        responsibility=(
            "执行一条多环节流水线。"
            "可做：完成一条含多环节（检索/分析/生成/转换等）的流水线，调用模型或工具逐环节推进，产出本流水线结果。"
            "不可做：不做单一原子任务（那是 task）；不跨流水线/维度；不拆解整体目标（那是 expert/workgroup）；不调度其他流水线。"
        ),
    ),
    AEFlowRole.task: AERoleParamInfo(
        role=AEFlowRole.task,
        title="原子任务",
        responsibility=(
            "执行一个不可再分的原子任务。"
            "可做：完成单一、不可再分的目标，由模型判断用'直接作答'还是'跑脚本'完成，产出单一结果。"
            "不可做：不做多环节流水线（那是 employee）；不拆解、不规划、不调度其他角色、不跨任务。"
        ),
    ),
    AEFlowRole.llm: AERoleParamInfo(
        role=AEFlowRole.llm,
        title="LLM AI 作答",
        responsibility=(
            "仅凭训练数据直接作答，不用工具。"
            "可做：仅凭 LLM 训练好的历史数据回答简单知识性问题，给出准确、完整的结论。"
            "不可做：不拆解、不执行脚本（那是 script）、不获取网络/实时数据；仅基于训练好的历史数据作答；需实时或外部数据交由其他角色。"
        ),
    ),
    AEFlowRole.script: AERoleParamInfo(
        role=AEFlowRole.script,
        title="脚本工具",
        responsibility=(
            "运行脚本完成程序化操作，不做模型推理。"
            "可做：生成并运行 python/shell/ruby 脚本完成：检索（网络爬虫、API 调用、本地文件读取）、计算（数值运算、统计、日期时间）、分析（数据解析、日志分析、正则匹配）、转换（格式转换 JSON/CSV/文本、编码、数据清洗）、生成（按规则产出文本/代码/结构化数据）、系统（系统与环境信息），产出 stdout 结果。"
            "不可做：不做需模型推理/判断的原子任务（那是 task）；不拆解、不规划、不调度、不多环节编排。"
        ),
    ),
}


def get_role_param(role: AEFlowRole) -> AERoleParamInfo:
    """按 AEFlowRole 取其默认参数信息；未注册时抛出 KeyError。"""
    return ROLE_PARAMS[role]


# ==================== 角色铁律（随 role_brief 拼接，替代 AEContextCenter 的 blanket 注入）====================
# 直接使用工具的角色（employee/task/script）：须自行通过工具拉取网络实时信息
AE_ROLE_IRON_LAW = (
    "【铁律】仔细阅读用户问题，不得给出简单、敷衍或弱智回答。"
    "简单或指向明确的问题可直接分析作答；复杂问题须先研判自身能否独立解决——"
    "若不能（需外部数据或实时信息），必须通过工具拉取网络实时信息或数据来补充与研判，"
    "确保结论完整准确，不得凭空臆造或敷衍。必须能给出答案。"
)
# 协调 / 无工具角色（expert/workgroup/llm 及入口 refiner）：不自行拉取，交由能使用工具的其他角色处理
AE_ROLE_IRON_LAW_NO_TOOL = (
    "【铁律】仔细阅读用户问题，不得给出简单、敷衍或弱智回答。"
    "简单或指向明确的问题可直接分析作答；复杂问题须先研判自身能否独立解决——"
    "若不能（需外部数据或实时信息），应交由能使用工具的其他角色处理，"
    "确保结论完整准确，不得凭空臆造或敷衍。必须能给出答案。"
)

# 直接使用工具的角色集合（铁律用工具拉取版）
_IRON_LAW_TOOL_ROLES: set = {AEFlowRole.employee, AEFlowRole.task, AEFlowRole.script}


def get_role_iron_law(role) -> str:
    """按角色能力返回适配的铁律文本，供 role_brief 拼接。

    直接用工具的角色（employee/task/script）用「必须通过工具拉取」版；
    协调或无工具角色（expert/workgroup/llm 及入口 refiner role=None）用「交由其他角色处理」版，
    与各角色既有能力一致，避免「llm 不获取网络」与「必须工具拉取」的矛盾。
    """
    if role in _IRON_LAW_TOOL_ROLES:
        return AE_ROLE_IRON_LAW
    return AE_ROLE_IRON_LAW_NO_TOOL
