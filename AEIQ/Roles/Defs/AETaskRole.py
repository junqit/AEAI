"""AETaskRole - 原子任务角色执行 Flow（继承 AERoleExcutor，_role()=task）。

task 为最底层执行单元：角色目标（self.input.goal）就绪后直接创建一个 AEScript 处理目标
（不再 LLM 拆解为多个脚本任务；AEScript 自行按当前 ruby/python/shell 能力选型 + 生成 + 执行 + 验证/重试）。
目标经公共接口 receive_flow_input 写入 AEScript.self.input.goal。input.goal 为空由
AERoleExcutor.receiveOptimizeInput 错误完成，避免卡死。
"""
import logging

from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
from WorkFlows.FlowWork.AEFlowOutput import AEFlowOutput
from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_CONTENT
from WorkFlows.FlowWork.AEFlowDelegate import AEFlowCompletEvent
from Context.Context.AELLMPayload import llm_generate
from Roles.AERoleType import AEFlowRole
from Roles.Defs.AERoleExcutor import AERoleExcutor

logger = logging.getLogger(__name__)


class AETaskRole(AERoleExcutor):
    """原子任务执行 Flow：目标就绪后创建 AEScript 处理（AEScript 自行选型/生成/执行/验证）。"""

    @classmethod
    def _role(cls):
        return AEFlowRole.task

    def requestRoleSelect(self) -> None:
        """task：不选角色，直接创建 AEScript 处理目标（不再 LLM 拆解；AEScript 自行选型+生成+执行）。
        目标经公共接口 receive_flow_input 写入 AEScript.self.input.goal。"""
        goal = self.input.goal if self.input is not None else ""
        if not goal:
            logger.warning("[%s][d=%s] 无可作答目标，以错误完成本 flow 避免卡死", self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "无可作答目标"},
                AEFlowCompletEvent.error,
            )
            return
        from Roles.Defs.AEScript import AEScript  # 懒导入避免循环
        flowOutput = AEFlowOutput(ident=self.ident, out_schema={AE_CONTENT: llm_generate("脚本执行结果")})
        script_flow = AEScript(flowOutput=flowOutput)
        self.add_flow(script_flow)
        # 公共接口：把目标传给 AEScript（self.input.goal）
        script_flow.receive_flow_input(AEFlowInput(content="", ident=script_flow.ident, goal=goal))
