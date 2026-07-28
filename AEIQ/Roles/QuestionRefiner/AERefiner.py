"""
AERefiner - 问题精炼 Flow，继承 AERole。

将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题，再请求 LLM 选择解决该问题
的角色：选人员角色（expert/workgroup/employee/task）则创建 AERoleExcutor（该角色）经
delegate 添加并以 startFlow 事件启动；选 llm 则直接作答。
"""
import logging

from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInfo import AE_IDENT, AE_ANSWER
from WorkFlows.AEFlowDelegate import AEFlowCompletEvent
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Roles.AERoleType import AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT, AEFlowRole, ROLE_PARAMS
from Roles.AERole import AERole
from Roles.AERoleExcutor import AERoleExcutor
from Roles.LLM.AELLMRole import AELLMRole

logger = logging.getLogger(__name__)


class AERefiner(AERole):
    """问题精炼 Flow：改写用户问题，再让 LLM 选择解决角色——
    人员角色则派发 AERoleExcutor（该角色）执行；llm 则直接作答。"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        # 职称 / 职责要求
        self.title = "Question Refiner"
        self.responsibility = (
            "将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题。\n"
            "要求：\n"
            "1. 保持用户原始意图不变。\n"
            "2. 不增加用户未明确表达的新需求。\n"
            "3. 不进行分析、推理或回答问题。\n"
            "4. 不补充事实信息。\n"
            "5. 只优化表达方式。\n"
            "6. 输出应该直接作为后续 AI 的输入。\n"
            "如果问题已经清晰，则仅做轻微优化。"
        )

    def outResult_summary(self) -> str:
        """覆写：以统一前缀（AE_USER_QUESTION_PREFIX）返回 outResult 的回答。"""
        answer = self.outResult.get(AE_ANSWER, "") if isinstance(self.outResult, dict) else ""
        return f"{AE_USER_QUESTION_PREFIX}{answer}"

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收优化后的问题：交基类存入 optimizePromptResult，再请求 LLM 判定是否需要角色人员回答。

        Args:
            data: 回包内层 llm_out，形如 {AE_ANSWER: <优化后的问题>}；若直接为字符串则视为问题

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        super().receiveOptimizeInput(data)  # 基类提取 AE_ANSWER 存入 optimizePromptResult + 打印摘要
        self._request_role_select()
        return True

    def _request_role_select(self) -> None:
        """请求 LLM 根据问题选择最适合解决此工作内容的角色（ROLE_PARAMS + llm 直接作答）。"""

        messages = []
        question = self.optimizePromptResult or (self.input.content if self.input is not None else "")
        if len(question) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{question}"})
        # 角色选择规则（system）：网络请求类必须选角色；复杂度分级
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: (
                "角色选择规则：\n"
                "- 若问题需要获取网络数据、实时数据、资讯等需通过网络请求的内容，必须选择角色（不得选 llm）；\n"
                "- 复杂/需规划或多步骤的问题选高层级角色；仅需脚本或单步执行选 task/employee；简单知识问题选 llm。"
            ),
        })
        # 角色花名册（system）：ROLE_PARAMS 中可派发的人员角色 + llm 直答
        role_lines = []
        for r, info in ROLE_PARAMS.items():
            role_lines.append(f"- {r.value}（{info.title}）：{info.responsibility}")
        role_lines.append("- llm（直接作答）：仅凭 LLM 自身知识即可回答的简单问题，无需人员")
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: "可选角色：\n" + "\n".join(role_lines),
        })
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"请根据{AE_USER_QUESTION_PREFIX}的内容与复杂度，选择最适合解决此问题的角色，"
                "将选择结果填入 role 字段（填角色 type，如 expert / workgroup / employee / task / llm）。"
            ),
        })
        flow_out = self.flowOutput("receiveRoleSelect")
        flow_out.set_llm_out({"role": llm_generate("expert / workgroup / employee / task / llm 之一")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveRoleSelect(self, data: dict) -> bool:
        """接收 LLM 选定的角色：llm 或非法 → 直接作答；人员角色 → 按该角色派发 AERoleExcutor。"""
        role_str = data.get("role") if isinstance(data, dict) else None
        if role_str is None and isinstance(data, str):
            role_str = data
        role_str = (role_str or "").strip().lower()
        if role_str == "llm" or not role_str:
            logger.info("[%s][%s][d=%s] 选择 llm 直接作答", type(self).__name__, self.title, self.deepth)
            self._request_direct_answer()
            return True
        try:
            role_enum = AEFlowRole(role_str)
        except ValueError:
            logger.warning("[%s][%s][d=%s] 非法 role=%r，回退直接作答", type(self).__name__, self.title, self.deepth, role_str)
            self._request_direct_answer()
            return True
        logger.info("[%s][%s][d=%s] 选择角色 %s，派发 AERoleExcutor", type(self).__name__, self.title, self.deepth, role_enum.value)
        self._dispatch_role_executor(role_enum)
        return True

    def _dispatch_role_executor(self, role: AEFlowRole) -> None:
        """创建 AERoleExcutor（指定 role），经 delegate 添加并以 startFlow 事件启动，
        由 delegate 据事件 startFlow 该执行 flow（input 取优化后的问题）。"""
        if self.delegate is None:
            logger.warning("[%s][%s][d=%s] delegate 未设置，无法添加 AERoleExcutor", type(self).__name__, self.title, self.deepth)
            return
        delegate_ident = self.delegate.ident
        excutor = AERoleExcutor(
            flowOutput=AEFlowOutput({AE_IDENT: delegate_ident, AE_ANSWER: llm_generate("任务结论")}),
        )
        excutor.role = role
        self.delegate.receive_add_flow(excutor)
        # 完成 refiner 自身：以 startFlow 事件向上通知，delegate 据此 startFlow 该 AERoleExcutor
        self.flow_receive_complete(
            {AE_IDENT: excutor.ident, AE_ANSWER: self.optimizePromptResult},
            AEFlowCompletEvent.startFlow,
        )

    def _request_direct_answer(self) -> None:
        """无需角色人员：创建 AELLMRole 子 flow 经 delegate 添加并以 startFlow 事件启动，
        由 delegate 据事件 startFlow 该 AELLMRole（input 取优化后的问题），LLM 回包即完成该子 flow。"""
        if self.delegate is None:
            logger.warning("[%s][%s][d=%s] delegate 未设置，无法添加 AELLMRole", type(self).__name__, self.title, self.deepth)
            return
        delegate_ident = self.delegate.ident
        llm_role = AELLMRole(
            flowOutput=AEFlowOutput({AE_IDENT: delegate_ident, AE_ANSWER: llm_generate("llm回答")}),
        )
        self.delegate.receive_add_flow(llm_role)
        # 完成 refiner 自身：以 startFlow 事件向上通知，delegate 据此 startFlow 该 AELLMRole（input 取优化后的问题）
        self.flow_receive_complete(
            {AE_IDENT: llm_role.ident, AE_ANSWER: self.optimizePromptResult},
            AEFlowCompletEvent.startFlow,
        )

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：交基类置 input，拼装 AELLMPayload 发送。

        - messages: system(title) / system(responsibility) / user(input.content)
        - out_schema: 本 flow 的输出结构（output 已在构造时设置，含 reply 占位，由 LLM 生成精炼后的问题）

        Args:
            flowInput: flow 输入数据（content 即用户原始问题）
        """
        if not super().startFlow(flowInput):
            logger.warning("[%s][%s][d=%s] startFlow 失败：基类未启动（非 default 状态），忽略", type(self).__name__, self.title, self.deepth)
            return

        self.requestOptimizeInput()
