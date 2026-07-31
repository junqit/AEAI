"""AEEmployeeRole - 员工角色执行 Flow（继承 AERoleExcutor，_role()=employee）。"""
from Roles.AERoleType import AEFlowRole
from Roles.Defs.AERoleExcutor import AERoleExcutor


class AEEmployeeRole(AERoleExcutor):
    """员工：拆解为 task 子任务。"""

    @classmethod
    def _role(cls):
        return AEFlowRole.employee
