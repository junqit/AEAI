"""AERoleDecompose - 任务拆解 mixin。

提供 requestWorkflow / receiveWorkflow：据已优化的问题与当前角色能力范围，拆解成多个任务，
每项含任务目标（goal）与任务需输出内容（expected_output）；receiveWorkflow 解析任务列表并打印。
"""
import logging

from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT, AE_IDENT
from WorkFlows.FlowWork.AEFlowDelegate import AEFlowCompletEvent
from WorkFlows.FlowWork.AEFlowOutput import AEFlowOutput
from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
from Roles.RoleBase.AERole import AERole

logger = logging.getLogger(__name__)


class AERoleDecomposeFunction(AEFunctional):
    """任务拆解回包功能性方法名。"""
    receiveWorkflow = "receiveWorkflow"


class AERoleDecompose(AERole):
    """任务拆解 mixin：据已优化问题与当前角色能力范围，拆成多个任务。"""

    # 据问题与角色能力拆解为最小颗粒度串行任务。
    def requestWorkflow(self) -> None:
        question = (self.input.get_goal() if self.input is not None else "")
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: (
                f"任务拆解规则：\n"
                f"按当前角色能力进行拆解：{self.role.workflow_rule}\n"
                "- 将当前问题拆解为最小颗粒度的任务（不可再分的原子任务），按串行顺序排列，合起来须完整解决该问题。\n"
                "- 每个任务必须包含：goal（该任务的目标）与 expected_output（该任务需要输出的内容）。\n"
                "- 每个任务的 goal 与 expected_output 须落在当前角色能力范围内，是最小颗粒度（不可再拆解）。\n"
                "- 任务按串行顺序执行（前一任务完成后才执行下一任务），每个任务为不可再分的原子任务；不得编造、不得拒绝。"
            ),
        })
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"问题/目标：{question}\n\n"
                f"请将上述问题拆解为最小颗粒度的串行任务，输出 JSON 数组填入 tasks 字段，"
                f"每项含 goal 与 expected_output，按串行顺序排列。"
            ),
        })
        flow_out = self.generateFlowOutput(AERoleDecomposeFunction.receiveWorkflow)
        flow_out.set_llm_out({
            "tasks": [{
                "goal": llm_generate("该最小颗粒度任务的目标"),
                "expected_output": llm_generate("该任务需要输出的内容"),
            }]
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema, temperature=0.3)
        self.flow_send_llm_request(payload)

    # 接收任务列表并派发；空则错误完成闭环。
    def receiveWorkflow(self, data: dict) -> bool:
        tasks = data.get("tasks") if isinstance(data, dict) else None
        if tasks is None and isinstance(data, str):
            tasks = [data] if data.strip() else []
        elif not isinstance(tasks, list):
            tasks = []
        logger.info("[%s][d=%s] 拆解出 %d 个任务：", self.title, self.deepth, len(tasks))
        from Roles.AEOrchestrator import AEOrchestrator  # 懒导入避免循环（AEOrchestrator → AERoleBase → 本模块）
        first_child = None
        for i, t in enumerate(tasks):
            if isinstance(t, dict):
                goal = t.get("goal") or t.get("expected_output") or ""
                logger.info("  任务 %d：goal=%s | expected_output=%s", i + 1, t.get("goal"), t.get("expected_output"))
            else:
                goal = t
                logger.info("  任务 %d：%s", i + 1, t)
            goal = str(goal or "").strip()
            if not goal:
                continue
            child = AEOrchestrator(
                flowOutput=AEFlowOutput(ident=self.ident, out_schema={AE_CONTENT: llm_generate("任务结论")}),
            )
            self.add_flow(child)
            child.update_flow_input(AEFlowInput(content=goal, ident=child.ident, role=self.role.role if self.role is not None else None))
            child.born_action = self.born_action
            if first_child is None:
                first_child = child
        if first_child is None:
            logger.warning("[%s][d=%s] 任务拆解为空或无可派发任务，以错误完成本 flow 避免卡死", self.title, self.deepth)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "任务拆解为空或无可派发任务"},
                AEFlowCompletEvent.error,
            )
            return False
        # 串行：首个启动，余者由 receive_flow_complete 的 nextFlow 逐个推进
        first_child.on_flow_start()
        logger.info("[%s][d=%s] 创建子任务并启动首个（串行），等待完成后汇总", self.title, self.deepth)
        return True

    # decompose 动作：优先用 subtasks 直接派发，未给则请求 LLM 拆解
    def do_decompose(self, subtasks: list) -> None:
        if not subtasks:
            self.requestWorkflow()
            return
        from Roles.AEOrchestrator import AEOrchestrator  # 懒导入避免循环
        first_child = None
        for goal in subtasks:
            goal = str(goal or "").strip()
            if not goal:
                continue
            child = AEOrchestrator(
                flowOutput=AEFlowOutput(ident=self.ident, out_schema={AE_CONTENT: llm_generate("任务结论")}),
            )
            self.add_flow(child)
            child.update_flow_input(AEFlowInput(content=goal, ident=child.ident, role=self.role.role if self.role is not None else None))
            child.born_action = self.born_action
            if first_child is None:
                first_child = child
        if first_child is None:
            self.flow_context.add_error("任务拆解为空或无可派发任务")
            self._orchestrate()
            return
        first_child.on_flow_start()
        logger.info("[%s][d=%s] 创建子任务并启动首个（串行）", self.title, self.deepth)
