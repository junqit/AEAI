"""
AERefiner - 问题精炼 Flow，继承 AERole。

将用户输入的问题改写为更清晰、更完整、更易于 AI 理解的问题，再请求 LLM 判定是否需要
角色人员回答：需要则创建 AERoleExcutor（expert）经 delegate 添加并以 startFlow 事件启动；
不需要则直接请求 LLM 作答。
"""
import logging

from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInfo import AE_IDENT, AE_ANSWER
from WorkFlows.AEFlowDelegate import AEFlowCompletEvent
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Roles.AERoleType import AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT, AEFlowRole
from Roles.AERole import AERole
from Roles.AERoleExcutor import AERoleExcutor
from Roles.LLM.AELLMRole import AELLMRole

logger = logging.getLogger(__name__)


class AERefiner(AERole):
    """问题精炼 Flow：改写用户问题，再判定是否需要角色人员回答——
    需要则派发 AERoleExcutor（expert）执行；不需要则直接请求 LLM 作答。"""

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
        self._request_need_role()
        return True

    def _request_need_role(self) -> None:
        """请求 LLM 判定优化后的问题是否需要角色人员（专家/工作组/员工）经拆解与脚本执行来回答。"""
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        question = self.optimizePromptResult or (self.input.content if self.input is not None else "")
        if len(question) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{question}"})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"请判断{AE_USER_QUESTION_PREFIX}是否需要派人员去解决，还是可直接由 LLM 作答：\n"
                "- 需要（need_role=true）：问题需要编写程序/脚本、获取网络数据、查询实时消息"
                "（如天气/股价/新闻/物流等）或其他外部信息，须由执行人员（专家/工作组/员工）处理；\n"
                "- 不需要（need_role=false）：仅凭 LLM 自身知识即可直接作答的简单问题。\n"
                "将判定结果填入 need_role 字段。"
            ),
        })
        flow_out = self.flowOutput("receiveNeedRole")
        flow_out.set_llm_out({"need_role": llm_generate("true 或 false")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveNeedRole(self, data: dict) -> bool:
        """接收 LLM 判定：需要角色 → 派发 AERoleExcutor；不需要 → 直接请求 LLM 作答。"""
        need = data.get("need_role") if isinstance(data, dict) else None
        if need is None and isinstance(data, str):
            need = data
        need_role = str(need or "").strip().lower() in ("true", "yes", "1", "需要", "是")
        if need_role:
            logger.info("[%s][%s][d=%s] 需要角色人员，派发 AERoleExcutor", type(self).__name__, self.title, self.deepth)
            self._dispatch_role_executor()
        else:
            logger.info("[%s][%s][d=%s] 无需角色人员，直接请求 LLM 作答", type(self).__name__, self.title, self.deepth)
            self._request_direct_answer()
        return True

    def _dispatch_role_executor(self) -> None:
        """创建 AERoleExcutor（expert），经 delegate 添加并以 startFlow 事件启动，
        由 delegate 据事件 startFlow 该执行 flow（input 取优化后的问题）。"""
        if self.delegate is None:
            logger.warning("[%s][%s][d=%s] delegate 未设置，无法添加 AERoleExcutor", type(self).__name__, self.title, self.deepth)
            return
        delegate_ident = self.delegate.ident
        excutor = AERoleExcutor(
            flowOutput=AEFlowOutput({AE_IDENT: delegate_ident, AE_ANSWER: llm_generate("任务结论")}),
        )
        excutor.role = AEFlowRole.expert
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
