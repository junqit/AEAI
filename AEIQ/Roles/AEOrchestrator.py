"""
AEOrchestrator - LLM 驱动的自主决策编排器。

替代 AERoleExcutor 的硬编码执行链：LLM 理解问题全貌后，自主判断需要什么能力
来全面解决问题，按需调用对应能力（角色信息/目标优化/背景确认/任务拆解/作答/脚本），
结果回写 flow 自身状态 + AEFlowContext（只存 background/action_history/errors），继续决策直到完成。

现有能力 mixin（AERoleClarify/AERoleOptimize/AERoleGather/
AERoleDecompose/AERoleAnswer/AERoleExecute）作为 action handler 被调用，
不再是固定序列中的步骤。
"""
import logging

from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_CONTENT
from WorkFlows.FlowWork.AEFlowDelegate import AEFlowCompletEvent
from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
from WorkFlows.FlowWork.AEFlowOutput import AEFlowOutput
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE, AEAction
from Roles.capability.AERoleClarify import AERoleClarify
from Roles.capability.AERoleOptimize import AERoleOptimize
from Roles.capability.AERoleGather import AERoleGather
from Roles.capability.AERoleVerify import AERoleVerify
from Roles.capability.AERoleSynthesize import AERoleSynthesize
from Roles.capability.AERoleComplete import AERoleComplete
from Roles.RoleBase.AERoleBase import AERoleBase
from Roles.capability.AERoleDecompose import AERoleDecompose
from Roles.capability.AERoleAnswer import AERoleAnswer
from Roles.capability.AERoleExecute import AERoleExecute

logger = logging.getLogger(__name__)


class AEOrchestratorFunction(AEFunctional):
    """Orchestrator 回包功能性方法名。"""
    receive_orchestrate = "receive_orchestrate"
    receive_action_catalog = "receive_action_catalog"


class AEOrchestrator(AERoleClarify, AERoleOptimize, AERoleGather, AERoleExecute,
                     AERoleDecompose, AERoleVerify, AERoleSynthesize, AERoleComplete, AERoleAnswer,
                     AERoleBase):
    """LLM 驱动的自主决策编排器：LLM 理解问题 → 自主选能力 → 执行 → 结果回写 → 继续决策。

    替代 AERoleExcutor 的硬编码链路（on_flow_start→requestRoleInformation→...→flow_complete），
    改为 LLM 看上下文全貌自主决定下一步。现有能力 mixin 作为 action handler 按需调用。
    flow 自身状态（title/responsibility/input.goal 等）直接读取，不经 AEFlowContext 中转。
    """

    # 已发起的决策轮数（每个 action 后 LLM 决定下一步的计数；温度递增与防循环用）
    decision_round: int = 0

    def on_flow_start(self, flowInput=None) -> bool:
        if not super().on_flow_start(flowInput):
            logger.warning("[%s][d=%s] on_flow_start 失败：基类未启动", self.title, self.deepth)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "flow 启动失败"},
                AEFlowCompletEvent.error,
            )
            return False
        self._init_action_catalog()
        return True

    # ==================== action catalog 初始化（LLM 生成） ====================

    # action 固定功能描述（做什么，不针对问题）
    ACTION_DESCRIPTIONS = {
        AEAction.clarify_role: "界定问题所需的角色身份（title）、能力范围（responsibility）与角色指令（rolePrompt），明确解决该问题需要扮演什么角色及其职责边界",
        AEAction.optimize_goal: "将原始问题或模糊目标转化为可执行、可完成的目标，明确成功标准与约束条件，确保目标能够准确、完整地回答输出",
        AEAction.gather_context: "识别解决当前目标所需但尚未明确的外部事实、数据或来源，生成可自行完成的目标以获取该信息",
        AEAction.execute_script: "通过脚本完成所有可程序化执行的工作，包括查询、计算、爬取、程序化处理、系统操作等，产出 stdout 结果",
        AEAction.decompose: "将当前目标拆解为更小、互不重叠、合起来完整覆盖目标的子任务，每个子任务为最小颗粒度的可独立完成的原子任务",
        AEAction.verify: "验证子任务结果是否齐备、有效、完整覆盖原始目标，产出 PASS 或 FAIL 与具体缺口描述",
        AEAction.synthesize: "汇总子任务结果与背景信息为连贯、完整的候选答案，直接回答原始目标",
        AEAction.complete: "输出最终结论，结果优先使用显式结论，无则用目标或问题兜底",
        AEAction.answer: "无需拆解与汇总，可直接推理作答的简单问题旁路终态",
    }

    def _init_action_catalog(self) -> None:
        """LLM 根据当前目标 + action 固定功能，生成每个 action 的规则与范围（针对目标）。"""
        target = self.input.get_target() if self.input is not None else ""
        action_list = "\n".join(f"- {a.value}：{self.ACTION_DESCRIPTIONS[a]}" for a in AEAction)
        messages = [
            {
                AE_ROLE: AEConentRole.SYSTEM.value,
                AE_CONTENT: (
                    "根据下方目标，为每个动作生成针对性的规则与范围描述，包含：\n"
                    "- 可以做什么：该动作在当前目标下能执行的具体操作\n"
                    "- 不可以做什么：该动作的职责边界与禁止事项\n"
                    "- 选择规则：什么情况下应该选择该动作\n"
                    "要求：必须为以下所有动作生成描述，不得遗漏任何一个。\n"
                    "每个动作的固定功能如下：\n"
                    f"{action_list}"
                ),
            },
            {
                AE_ROLE: AEConentRole.USER.value,
                AE_CONTENT: f"目标：{target}",
            },
        ]
        flow_out = self.generateFlowOutput(AEOrchestratorFunction.receive_action_catalog)
        catalog = {a.value: llm_generate(f"{a.value} 针对当前目标的规则与范围") for a in AEAction}
        flow_out.set_llm_out(catalog)
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema, temperature=0.3)
        logger.info("[%s][d=%s] 生成 action catalog", self.title, self.deepth)
        self.flow_send_llm_request(payload)

    def receive_action_catalog(self, data: dict) -> bool:
        """LLM 回包：初始化 action catalog，确认收到的个数；不完整则重新生成。"""
        if not isinstance(data, dict):
            data = {}
        for action in AEAction:
            desc = str(data.get(action.value, "") or "").strip()
            if desc:
                self.flow_context.set_action(action.value, desc)
        received = self.flow_context.get_action_count()
        expected = len(AEAction)
        if received < expected:
            logger.warning("[%s][d=%s] action catalog 不完整：收到 %d/%d，重新生成",
                           self.title, self.deepth, received, expected)
            self._init_action_catalog()
            return True
        logger.info("[%s][d=%s] action catalog 就绪（%d/%d）",
                    self.title, self.deepth, received, expected)
        self._orchestrate()
        return True

    # ==================== 决策循环 ====================

    def _orchestrate(self) -> None:
        """请求 LLM 决策：看上下文全貌 + 可用动作，选择下一步。"""
        # 决策温度递增：首次 0.3，每次 +0.2，上限 0.9
        decision_temp = min(0.3 + self.decision_round * 0.2, 0.9)

        messages = self._build_decision_messages()
        flow_out = self.generateFlowOutput(AEOrchestratorFunction.receive_orchestrate)
        available_action_names = " / ".join(a.value for a in AEAction if a != self.born_action)
        flow_out.set_llm_out({
            "action": llm_generate(f"动作名：{available_action_names}"),
            "target": llm_generate("选择该动作的原因转变成需要完成的目标"),
            "reason": llm_generate("选择该动作的原因"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema, temperature=decision_temp)
        logger.info("[%s][d=%s] 编排决策第 %d 轮（temperature=%.1f）",
                    self.title, self.deepth, self.decision_round + 1, decision_temp)
        self.decision_round += 1
        self.flow_send_llm_request(payload)

    def receive_orchestrate(self, data: dict) -> bool:
        """LLM 决策回包：执行选定的动作。"""
        self.decision_round = 0  # 每次收到重置，下轮决策从 0 开始
        if not isinstance(data, dict):
            data = {}
        action_str = data.get("action", "")
        target = str(data.get("target", "") or "").strip()
        reason = str(data.get("reason", "") or "").strip()

        logger.info("[%s][d=%s] LLM 决策: action=%s, target=%s, reason=%s",
                    self.title, self.deepth, action_str, target[:80], reason[:80])

        # 按动作分发；无效 action 直接 error 终止，不重试（防循环）
        try:
            action = AEAction(action_str)
        except ValueError:
            logger.warning("[%s][d=%s] 未识别的动作 %s，error 终止", self.title, self.deepth, action_str)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: f"未识别的动作：{action_str}"},
                AEFlowCompletEvent.error,
            )
            return True

        # 更新 born_action 为当前 action，下次决策不可重复此步骤
        self.born_action = action

        if action == AEAction.clarify_role:
            self.requestRoleInformation()
        elif action == AEAction.optimize_goal:
            self.requestOptimizeInput()
        elif action == AEAction.gather_context:
            self.requestContextNeeded()
        elif action == AEAction.decompose:
            self.do_decompose()
        elif action == AEAction.execute_script:
            self.do_execute()
        elif action == AEAction.synthesize:
            self.do_synthesize()
        elif action == AEAction.verify:
            self.do_verify()
        elif action == AEAction.answer:
            self.requestLLMAnswer()
        elif action == AEAction.complete:
            self.requestComplete()
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

        # SYSTEM: 决策规则
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: (
                "决策规则：\n"
                "- decompose 的子任务必须是当前目标的细化分解（更小范围的子问题），合起来完整覆盖当前目标，不得发散\n"
                "- detail 必须是可完成的目标或参数，不得是疑问、提问或要求用户交互，不得对目标或问题提出疑问或质疑\n"
                "- 涉及用户上下文信息时，用技术手段获取，除权限问题外\n"
                "输出 JSON：action（动作名）、detail（参数）。"
            ),
        })

        # USER: 当前目标
        target = self.input.get_target() if self.input is not None else ""
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"当前目标：{target}\n\n"
                "依据当前上下文，选择下一步动作。"
            ),
        })
        return messages

    def _action_catalog(self) -> str:
        """动作清单（action catalog 由 LLM 在 on_flow_start 时生成，存 flow_context）。"""
        born_action = self.born_action
        lines = ["可用动作："]
        if born_action:
            lines.append(f"（本 flow 由 {born_action.value} 创建，不可再选 {born_action.value}，避免同动作递归）")
        for action in AEAction:
            if action == born_action:
                continue
            desc = self.flow_context.get_action_description(action.value)
            lines.append(f"- {action.value}：{desc}")
        return "\n".join(lines)

    # ==================== LLM 请求：加父 flow 步骤结论作为背景，确保上下文完整 ====================

    def flow_send_llm_request(self, payload: "AELLMPayload") -> None:
        """发送 LLM 请求前加自己的步骤结论作为背景；super 层层调用，每层加各自的 context。"""
        context = self.flow_context.to_prompt()
        if context:
            payload.messages.insert(0, {
                AE_ROLE: AEConentRole.SYSTEM.value,
                AE_CONTENT: f"步骤结论：\n{context}",
            })
        super().flow_send_llm_request(payload)

    # ==================== 子 flow 创建（gather_context / decompose 统一调用） ====================

    def _create_subflow(self, target: str):
        """创建子 flow 处理独立目标（已 add_flow，未 on_flow_start，由调用方决定启动）。"""
        from Roles.AEOrchestrator import AEOrchestrator
        sub = AEOrchestrator(
            flowOutput=AEFlowOutput(ident=self.ident, out_schema={AE_CONTENT: llm_generate("子任务结论")}),
        )
        sub.update_flow_input(AEFlowInput(content=target, ident=sub.ident, role=self.role.role if self.role is not None else None))
        sub.born_action = self.born_action
        self.add_flow(sub)
        return sub

    # ==================== 子 flow 完成：记录子 flow 目标与结果 ====================

    def receive_flow_complete(self, flowOutput) -> bool:
        """子 flow 完成回调：通过 flowOutput.ident 直接获取对应子 flow，记录 subflow_result；其余交 super。"""
        ident = flowOutput.ident if flowOutput is not None else ""
        sub = self._flows.get(ident) if ident else None
        if sub is not None:
            self.flow_context.record_subflow_result(sub)
        return super().receive_flow_complete(flowOutput)

    # 全完成时回 _orchestrate 走收敛链（替代基类 summarize_to_llm 直接 flow_complete）
    def summarize_to_llm(self) -> None:
        self._orchestrate()

    # ==================== 能力回包 → 判断 super 返回值，正确推进 / 失败 error 终止 ====================

    def receiveRoleInfomation(self, data: dict) -> bool:
        """角色信息回包：super 写入 title/responsibility；正确继续决策，失败 error 终止。"""
        result = super().receiveRoleInfomation(data)
        if result:
            self._orchestrate()
        else:
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "角色信息生成失败"},
                AEFlowCompletEvent.error,
            )
        return True

    def receiveOptimizeInput(self, data: dict) -> bool:
        """目标优化回包：super 写入 input.goal；正确继续决策，失败 error 终止。"""
        result = super().receiveOptimizeInput(data)
        if result:
            self._orchestrate()
        else:
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "目标优化失败"},
                AEFlowCompletEvent.error,
            )
        return True

    def receive_synthesize(self, data: dict) -> bool:
        """综合汇总回包：super 写入 synthesis；正确继续决策，失败 error 终止。"""
        result = super().receive_synthesize(data)
        if result:
            self._orchestrate()
        else:
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "综合汇总失败"},
                AEFlowCompletEvent.error,
            )
        return True

    def receive_verify(self, data: dict) -> bool:
        """验证回包：super 写入 verification；通过继续决策，未通过 error 终止。"""
        result = super().receive_verify(data)
        if result:
            self._orchestrate()
        else:
            gaps = data.get("gaps", "") if isinstance(data, dict) else ""
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: f"验证未通过：{gaps}" if gaps else "验证未通过"},
                AEFlowCompletEvent.error,
            )
        return True
