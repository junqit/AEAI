"""AEExpertRole - 领域专家角色执行 Flow（_role()=expert）。"""
from Roles.RoleBase.AERoleType import AEFlowRole
from Roles.AERoleExcutor import AERoleExcutor


class AEExpertRole(AERoleExcutor):
    """领域专家：拆解为 workgroup/employee/task 子任务。"""

    @classmethod
    def _role(cls):
        return AEFlowRole.expert
