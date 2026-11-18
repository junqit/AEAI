"""
AEOrchestrator - LLM 驱动的自主决策编排器。

替代 AERoleExcutor 的硬编码执行链：LLM 理解问题全貌后，自主判断需要什么能力
来全面解决问题，按需调用对应能力（角色信息/目标优化/背景确认/任务拆解/作答/脚本），
结果回写 flow 自身状态 + AEFlowContext（只存 background/action_history/errors），继续决策直到完成。

现有能力 mixin（AERoleInformation/AERoleQuestion/AERoleChoice/AERoleContext/
AERoleWorkflow/AERoleExcuteLLM/AERoleExcuterScript）作为 action handler 被调用，
不再是固定序列中的步骤。
"""
import logging
from enum import Enum
from typing import Dict, Any, List

from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_CONTENT
from WorkFlows.FlowWork.AEFlowDelegate import AEFlowCompletEvent
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
from Roles.RoleBase.AERoleBase import AERoleBase
from Roles.RoleBase.AEFlowContext import AEFlowContext
from Roles.Excutor.AERoleExcuteLLM import AERoleExcuteLLM
from Roles.Excutor.AERoleExcuterScript import AERoleExcuterScript

logger = logging.getLogger(__name__)


class AEAction(str, Enum):
    """LLM 可自主选择的动作。"""
    clarify_role = "clarify_role"       # 明确角色身份与能力范围
    optimize_goal = "optimize_goal"     # 优化目标
    gather_context = "gather_context"   # 获取背景信息
    decompose = "decompose"             # 拆解为子任务
    answer = "answer"                   # LLM 直接作答
    execute_script = "execute_script"   # 脚本执行
    complete = "complete"               # 完成并输出结果


class AEOrchestratorFunction(AEFunctional):
    """Orchestrator 回包功能性方法名。"""
    receive_orchestrate = "receive_orchestrate"


class AEOrchestrator(AERoleExcuteLLM, AERoleExcuterScript, AERoleBase):
    """LLM 驱动的自主决策编排器：LLM 理解问题 → 自主选能力 → 执行 → 结果回写 → 继续决策。

    替代 AERoleExcutor 的硬编码链路（on_flow_start→requestRoleInformation→...→flow_complete），
    改为 LLM 看上下文全貌自主决定下一步。现有能力 mixin 作为 action handler 按需调用。
    flow 自身状态（title/responsibility/input.goal 等）直接读取，不经 AEFlowContext 中转。
    """

    # 最大决策轮数（防止无限循环）
    MAX_DECISIONS: int = 10
    # 最大拆解深度（超过则不允许 decompose，强制 answer/complete）
    MAX_DECOMPOSE_DEPTH: int = 3

    def on_flow_start(self, flowInput=None) -> bool:
        if not super().on_flow_start(flowInput):
            logger.warning("[%s][d=%s] on_flow_start 失败：基类未启动", self.title, self.deepth)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "flow 启动失败"},
                AEFlowCompletEvent.error,
            )
            return False
        # 只初始化 flow 没有的辅助上下文（background/action_history/errors）
        self.flow_context = AEFlowContext()
        self._orchestrate()
        return True

    # ==================== 决策循环 ====================

    def _orchestrate(self) -> None:
        """请求 LLM 决策：看上下文全貌 + 可用动作，选择下一步。"""
        if self.flow_context.decision_count() >= self.MAX_DECISIONS:
            logger.warning("[%s][d=%s] 达到最大决策轮数 %d，强制完成", self.title, self.deepth, self.MAX_DECISIONS)
            self._do_complete({})
            return

        # 决策温度递增：首次 0.3，每次 +0.2，上限 0.9
        decision_temp = min(0.3 + self.flow_context.decision_count() * 0.2, 0.9)

        messages = self._build_decision_messages()
        flow_out = self.generateFlowOutput(AEOrchestratorFunction.receive_orchestrate)
        flow_out.set_llm_out({
            "action": llm_generate("动作名：clarify_role / optimize_goal / gather_context / decompose / answer / execute_script / complete"),
            "detail": llm_generate("按动作填：gather_context=要获取的信息目标；decompose=子任务（每行一个）；complete=最终结论；其余留空"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema, temperature=decision_temp)
        logger.info("[%s][d=%s] 编排决策第 %d 轮（temperature=%.1f）",
                    self.title, self.deepth, self.flow_context.decision_count() + 1, decision_temp)
        self.flow_send_llm_request(payload)

    def receive_orchestrate(self, data: dict) -> bool:
        """LLM 决策回包：执行选定的动作。"""
        if not isinstance(data, dict):
            data = {}
        action_str = data.get("action", "")
        detail = str(data.get("detail", "") or "").strip()

        logger.info("[%s][d=%s] LLM 决策: action=%s, detail=%s", self.title, self.deepth, action_str, detail[:100])

        # 记录动作
        self.flow_context.record_action(action_str)

        # 按动作分发
        try:
            action = AEAction(action_str)
        except ValueError:
            logger.warning("[%s][d=%s] 未识别的动作 %s，重新决策", self.title, self.deepth, action_str)
            self._orchestrate()
            return True

        if action == AEAction.clarify_role:
            self._do_clarify_role()
        elif action == AEAction.optimize_goal:
            self._do_optimize_goal()
        elif action == AEAction.gather_context:
            self._do_gather_context(detail)
        elif action == AEAction.decompose:
            subtasks = [s.strip() for s in detail.split("\n") if s.strip()] if detail else []
            self._do_decompose(subtasks)
        elif action == AEAction.answer:
            self._do_answer()
        elif action == AEAction.execute_script:
            self._do_execute_script()
        elif action == AEAction.complete:
            self._do_complete(detail)
        else:
            self._orchestrate()
        return True

    # ==================== 决策消息构建（直接从 flow 自身读，不经 AEFlowContext 中转） ====================

    def _build_decision_messages(self) -> list:
        """构建 LLM 决策消息：角色身份 + 可用动作 + 当前上下文 + 指令。"""
        messages = []

        # SYSTEM: 角色身份（直接从 self.title/self.responsibility 读）
        system_parts = []
        if self.title:
            system_parts.append(f"身份：{self.title}")
        if self.responsibility:
            system_parts.append(f"能力范围：{self.responsibility}")
        if system_parts:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: "".join(system_parts)})

        # SYSTEM: 可用动作清单（动态过滤已有信息的能力）
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: self._action_catalog(),
        })

        # 从 flow 自身读 question/goal/sub_results，传给 flow_context.to_prompt 补独有信息
        question = self.input.get_content() if self.input is not None else ""
        goal = self.input.get_goal() if self.input is not None else ""
        sub_results = []
        for f in self._flows.values():
            r = getattr(f.output, "outResult", "") if f.output else ""
            if r:
                sub_results.append(r)

        # USER: 当前上下文 + 决策指令
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"当前上下文：\n{self.flow_context.to_prompt(question=question, title=self.title, responsibility=self.responsibility, goal=goal, sub_results=sub_results)}\n\n"
                f"基于你对问题的整体理解，选择下一步动作来全面解决问题。\n"
                f"注意：选择 decompose 时，子任务必须是当前目标的**细化分解**（更小范围的子问题），"
                f"合起来完整覆盖当前目标，不得发散到无关方向。\n"
                f"输出 JSON：action（动作名）、detail（按动作填参数）。"
            ),
        })
        return messages

    def _action_catalog(self) -> str:
        """可用动作清单（按已有信息动态过滤），含使用条件与选择顺序建议。"""
        all_actions = [
            (AEAction.clarify_role, "仅当缺少「以什么身份/能力解决问题」且该信息会显著改变回答时使用", ""),
            (AEAction.optimize_goal, "仅当原始问题模糊、无法直接执行，需要转化为可执行目标时使用", ""),
            (AEAction.gather_context, "仅当缺少外部事实、数据或来源，且这些信息无法通过推理得到时使用", "填 detail 字段"),
            (AEAction.decompose, "仅当当前目标可以拆成若干更小、互不重叠、合起来覆盖当前目标的子任务时使用", "填 detail 字段（每行一个子任务）"),
            (AEAction.answer, "当已有足够信息，且不需要外部数据或脚本时使用", ""),
            (AEAction.execute_script, "当需要查询、计算、爬取或程序化处理时使用", ""),
            (AEAction.complete, "当问题已解决，需要输出最终结论时使用", "填 detail 字段"),
        ]
        lines = ["可用动作："]
        for action, desc, extra in all_actions:
            if action == AEAction.clarify_role and self.title:
                continue
            if action == AEAction.optimize_goal and self.input and self.input.get_goal():
                continue
            # 非顶层（depth>=2）不允许 gather_context，避免递归
            if action == AEAction.gather_context and self.deepth >= 2:
                continue
            if action == AEAction.decompose and self.deepth >= self.MAX_DECOMPOSE_DEPTH:
                continue
            line = f"- {action.value}：{desc}"
            if extra:
                line += f"；{extra}"
            lines.append(line)
        lines.append("")
        lines.append("选择顺序建议：")
        lines.append("1. 当前级任务是否已明确？不明确 → optimize_goal")
        lines.append("2. 是否缺少关键外部数据？缺少 → gather_context 或 execute_script")
        lines.append("3. 当前目标是否需要拆成多个子任务？需要 → decompose")
        lines.append("4. 是否已有足够信息直接回答？是 → answer")
        lines.append("5. 是否已完成并需输出结论？是 → complete")
        return "\n".join(lines)

    # ==================== 动作执行器（复用现有能力 mixin） ====================

    def _do_clarify_role(self) -> None:
        """调用角色信息能力（AERoleInformation.requestRoleInformation）。"""
        self.requestRoleInformation()

    def _do_optimize_goal(self) -> None:
        """调用目标优化能力（AERoleQuestion.requestOptimizeInput）。"""
        self.requestOptimizeInput()

    def _do_gather_context(self, target: str) -> None:
        """获取背景信息：派发子 flow 解决，在父目标框架下。"""
        if not target:
            self._orchestrate()
            return
        sub = self._dispatch_context_flow(target)
        if sub is None:
            self.flow_context.add_error("背景确认子 flow 创建失败")
            self._orchestrate()
            return
        self.completeIdent = self.registerFunctional("contextComplete")
        self.add_flow(sub)
        sub.on_flow_start()

    def _do_decompose(self, subtasks: list) -> None:
        """任务拆解：优先用 subtasks 直接派发，未给则请求 LLM 拆解。"""
        if subtasks:
            count = self._dispatch_workflow_tasks(subtasks)
            if count == 0:
                self.flow_context.add_error("任务拆解为空或无可派发任务")
                self._orchestrate()
        else:
            self.requestWorkflow()

    def _do_answer(self) -> None:
        """LLM 直接作答（AERoleExcuteLLM.requestLLMAnswer）。"""
        self.requestLLMAnswer()

    def _do_execute_script(self) -> None:
        """脚本执行：进入选型→生成→执行→验证循环。"""
        self._request_script_type()

    def _do_complete(self, result: str) -> None:
        """完成并输出结果。"""
        if not result:
            result = (self.input.get_goal() if self.input is not None else "") or \
                   (self.input.get_content() if self.input is not None else "")
        self.flow_complete(
            {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
             AE_CONTENT: result},
        )

    # ==================== 能力回包 → 继续决策（不再双向同步 flow 已有字段） ====================

    def receiveRoleInfomation(self, data: dict) -> bool:
        """角色信息回包：super 已写入 self.title/responsibility，直接继续决策。"""
        result = super().receiveRoleInfomation(data)
        if not result or not self.title:
            self.flow_context.add_error("角色信息生成失败")
        self._orchestrate()
        return True

    def receiveOptimizeInput(self, data: dict) -> bool:
        """目标优化回包：super 已写入 input.goal，直接继续决策。"""
        result = super().receiveOptimizeInput(data)
        if not result or not (self.input.get_goal() if self.input else ""):
            self.flow_context.add_error("目标优化失败")
        self._orchestrate()
        return True

    def contextComplete(self, flowOutput) -> bool:
        """背景确认子 flow 完成回调：结果写入 flow_context.background，继续决策。"""
        result = super().contextComplete(flowOutput)
        if result and flowOutput is not None:
            bg = getattr(flowOutput, "outResult", "") or ""
            if bg:
                self.flow_context.set_background(bg)
        self._orchestrate()
        return True

    def receiveWorkflow(self, data: dict) -> bool:
        """任务拆解回包：子 flow 完成后结果在 self._flows，直接继续决策。"""
        result = super().receiveWorkflow(data)
        return result

    def receive_summarize_result(self, data: dict) -> bool:
        """作答/汇总结果回包：这是最终结论，直接完成 flow。"""
        answer = ""
        if isinstance(data, dict):
            answer = data.get(AE_CONTENT, "") or ""
        elif isinstance(data, str):
            answer = data
        self.flow_complete(
            {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
             AE_CONTENT: answer},
        )
        return True

    # ==================== 背景确认子 flow 派发（复用 AERoleContext） ====================

    def _dispatch_context_flow(self, target: str):
        """创建执行背景确认的子 flow（复用 AERoleContext._dispatch_context_flow 逻辑）。"""
        from Roles.RoleBase.AERoleContext import AERoleContext
        return AERoleContext._dispatch_context_flow(self, target)
