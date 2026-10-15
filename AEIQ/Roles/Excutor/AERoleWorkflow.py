"""AERoleWorkflow - 任务拆解 mixin。

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


class AERoleWorkflowFunction(AEFunctional):
    """任务拆解回包功能性方法名。"""
    receiveWorkflow = "receiveWorkflow"


class AERoleWorkflow(AERole):
    """任务拆解 mixin：据已优化问题与当前角色能力范围，拆成多个任务。"""

    def requestWorkflow(self) -> None:
        """据已优化的问题（goal）与当前角色能力范围（role_brief），拆解成多个任务。

        每项任务含 goal（任务目标）与 expected_output（任务需输出内容）。
        须确保拆解出的任务合起来能完整解决用户问题，且每项落在当前角色能力范围内。
        """
        question = ((self.input.get_goal() or self.input.get_content()) if self.input is not None else "")
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: (
                f"任务拆解规则：\n"
                f"按当前角色能力进行拆解：{self.role.workflow_rule}\n"
                "- 将当前问题拆解为若干可独立完成的任务，合起来须完整解决该问题。\n"
                "- 每个任务必须包含：goal（该任务的目标）与 expected_output（该任务需要输出的内容）。\n"
                "- 每个任务的 goal 与 expected_output 须落在当前角色能力范围内，可独立完成。\n"
                "- 任务数量尽可能少，避免过度拆解；不得编造、不得拒绝。"
            ),
        })
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"问题/目标：{question}\n\n"
                f"请将上述问题拆解为多个任务，输出 JSON 数组填入 tasks 字段，"
                f"每项含 goal 与 expected_output。"
            ),
        })
        flow_out = self.generateFlowOutput(AERoleWorkflowFunction.receiveWorkflow)
        flow_out.set_llm_out({
            "tasks": [{
                "goal": llm_generate("该任务的目标，可独立完成"),
                "expected_output": llm_generate("该任务需要输出的内容"),
            }]
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveWorkflow(self, data: dict) -> bool:
        """接收拆解出的任务列表：解析+打印+派发（经 _dispatch_workflow_tasks hook）；
        空或无可派发则以错误完成闭环。成功派发返回 True，否则 False。"""
        tasks = data.get("tasks") if isinstance(data, dict) else None
        if tasks is None and isinstance(data, str):
            tasks = [data] if data.strip() else []
        elif not isinstance(tasks, list):
            tasks = []
        logger.info("[%s][d=%s] 拆解出 %d 个任务：", self.title, self.deepth, len(tasks))
        for i, t in enumerate(tasks):
            if isinstance(t, dict):
                logger.info(
                    "  任务 %d：goal=%s | expected_output=%s",
                    i + 1, t.get("goal"), t.get("expected_output"),
                )
            else:
                logger.info("  任务 %d：%s", i + 1, t)
        subtask_count = self._dispatch_workflow_tasks(tasks)
        if not subtask_count:
            logger.warning("[%s][d=%s] 任务拆解为空或无可派发任务（子任务 %d 个），以错误完成本 flow 避免卡死",
                           self.title, self.deepth, subtask_count)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "任务拆解为空或无可派发任务"},
                AEFlowCompletEvent.error,
            )
            return False
        return True

    def _dispatch_workflow_tasks(self, tasks: list) -> int:
        """任务派发：为每个任务创建子 AERoleExcutor（自行选角色执行），把 goal 作为 content 传入。
        子 flow 的 flowOutput.ident 取当前 self.ident（子 flow 为本 flow 的子任务，完成回程路由回本 flow）。
        返回派发的子任务数量（0 表示无可派发，由 receiveWorkflow 据此错误完成闭环）。"""
        from Roles.AERoleExcutor import AERoleExcutor  # 懒导入避免循环（AERoleExcutor → AERoleBase → 本模块）
        dispatched = 0
        for t in tasks:
            if isinstance(t, dict):
                goal = t.get("goal") or t.get("expected_output") or ""
            else:
                goal = t
            goal = str(goal or "").strip()
            if not goal:
                continue
            child = AERoleExcutor(
                flowOutput=AEFlowOutput(ident=self.ident, out_schema={AE_CONTENT: llm_generate("任务结论")}),
            )
            self.add_flow(child)
            child.receive_flow_input(AEFlowInput(content=goal, ident=child.ident))
            dispatched += 1
        logger.info("[%s][d=%s] 创建 %d 个子任务 AERoleExcutor，等待完成后汇总", self.title, self.deepth, dispatched)
        return dispatched
