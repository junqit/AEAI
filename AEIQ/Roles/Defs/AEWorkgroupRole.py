"""AEWorkgroupRole - 工作组角色执行 Flow（_role()=workgroup）。"""
from Roles.RoleBase.AERoleType import AEFlowRole
from Roles.AERoleExcutor import AERoleExcutor


class AEWorkgroupRole(AERoleExcutor):
    """工作组：拆解为 employee/task 子任务。"""

    @classmethod
    def _role(cls):
        return AEFlowRole.workgroup
