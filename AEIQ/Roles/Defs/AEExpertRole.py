"""AEExpertRole - 领域专家角色执行 Flow（继承 AERoleExcutor，_role()=expert）。"""
from Roles.AERoleType import AEFlowRole
from Roles.Defs.AERoleExcutor import AERoleExcutor


class AEExpertRole(AERoleExcutor):
    """领域专家：拆解为 workgroup/employee/task 子任务。"""

    @classmethod
    def _role(cls):
        return AEFlowRole.expert
