"""AEWorkgroupRole - 工作组角色执行 Flow（继承 AERoleExcutor，_role()=workgroup）。"""
from Roles.AERoleType import AEFlowRole
from Roles.Defs.AERoleExcutor import AERoleExcutor


class AEWorkgroupRole(AERoleExcutor):
    """工作组：拆解为 employee/task 子任务。"""

    @classmethod
    def _role(cls):
        return AEFlowRole.workgroup
