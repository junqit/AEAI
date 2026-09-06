"""
AELLMRole - LLM 直接作答角色 Flow，继承 AERoleExcutor。

已是选定角色（无需再选角色）：共用 AERoleExcutor 前置链路（角色信息 → rolePrompt → 问题优化），
在 receiveOptimizeInput 之后（input.goal 就绪）决策「是否需要多个 LLM 进行分析」：
  - choice=True（入口）：覆写 requestRoleSelect 发起 requestMultiLLMDecision 决策请求
    （仅决策，不在此发起多 LLM 查询）。回包 receiveMultiLLMDecision：
      单一问题 → 自身 requestLLMAnswer 作答；
      多子问题 → 创建 choice=False 的子 AELLMRole 并行查询，全部完成后由 summarize_to_llm 汇总。
  - choice=False（被派生的子节点）：跳过决策，直接 requestLLMAnswer 作答，避免递归。
_role()=llm；requestRoleSelect 覆写为决策入口（替代默认的角色选择）。
"""
import logging

from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Roles.AERoleType import AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AEFlowRole
from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT, AE_IDENT
from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
from WorkFlows.FlowWork.AEFlowDelegate import AEFlowCompletEvent
from Roles.Defs.AERoleExcutor import AERoleExcutor
from Tools.Excutor.AERuntimeExcutor import AEFunctional

logger = logging.getLogger(__name__)


class AELLMRoleFunction(AEFunctional):
    """AELLMRole 专属回包功能性方法名（继承 AEFunctional 基类）。"""
    receiveMultiLLMDecision = "receiveMultiLLMDecision"  # 接收 LLM 对「是否需要多个 LLM 查询」的决策


class AELLMRole(AERoleExcutor):
    """LLM 直接作答角色：问题优化后就「是否多 LLM 查询」决策，否则自身作答，则派生子节点并行查询后汇总。"""

    def __init__(self, flowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        # choice=True：入口节点，发起「是否多 LLM 查询」决策；choice=False：被派生子节点，直接作答避免递归
        self.choice = True

    @classmethod
    def _role(cls):
        return AEFlowRole.llm

    def roleDescription(self) -> str:
        """角色描述：返回本角色的职称与职责。"""
        return f"{self.title}：{self.responsibility}"

    def requestRoleSelect(self) -> None:
        """覆写 AERoleExcutor.receiveOptimizeInput 之后的 hook：input.goal 就绪后决策。
        choice=False 直接作答；choice=True 发起「是否多 LLM 查询」决策请求。
        """
        if not self.choice:
            self.requestLLMAnswer()
            return
        self.requestMultiLLMDecision()

    def requestMultiLLMDecision(self) -> None:
        """请求 LLM 判断是否需要拆分为多个独立子问题分别查询。回包经 receiveMultiLLMDecision 处理。"""
        # input.goal 已由 receiveOptimizeInput 设置（AERoleExcutor 在为空时已错误完成）
        if not (self.input.goal if self.input is not None else ""):
            logger.warning("[%s][d=%s] 无可作答问题，以错误完成本 flow 避免卡死", self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_CONTENT: "无可作答问题"},
                AEFlowCompletEvent.error,
            )
            return
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{self.input.goal if self.input is not None else ''}"})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "判断上述问题是否需要拆分为多个独立子问题，分别交由不同 LLM 查询后再汇总：\n"
                "- 若问题单一、可一次性直接作答，返回空数组；\n"
                "- 若需多角度 / 多维度分别查询，返回各独立子问题（每个可独立完成、互不依赖）。\n"
                "输出 JSON 数组填入 questions 字段。"
            ),
        })
        flow_out = self.generateFlowOutput(AELLMRoleFunction.receiveMultiLLMDecision)
        flow_out.set_llm_out({"questions": [{AE_CONTENT: llm_generate("独立子问题，可独立完成且必须能解决目标")}]})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveMultiLLMDecision(self, data: dict) -> bool:
        """接收「是否多 LLM 查询」决策：单一问题 → 自身作答；多子问题 → 派生 choice=False 子节点并行查询。"""
        questions = data.get("questions") if isinstance(data, dict) else None
        if questions is None and isinstance(data, str):
            questions = [data] if data.strip() else []
        elif not isinstance(questions, list):
            questions = []
        # 兼容 dict / str 项，过滤空项
        sub_questions = []
        for q in questions:
            s = q.get(AE_CONTENT, "") if isinstance(q, dict) else q
            s = str(s or "").strip()
            if s:
                sub_questions.append(s)
        if len(sub_questions) <= 1:
            # 单一问题：自身直接作答
            self.requestLLMAnswer()
            return True
        # 多子问题：派生 choice=False 的子 AELLMRole 并行查询，自身等待汇总
        created = 0
        for sq in sub_questions:
            child = self._instantiate_role_flow(AEFlowRole.llm, self.ident)
            child.choice = False
            self.add_flow(child)
            child.receive_flow_input(AEFlowInput(content=sq, ident=child.ident))
            created += 1
        logger.info("[%s][d=%s] 拆分为 %d 个子 AELLMRole 并行查询，等待汇总", self.title, self.deepth, created)
        return True

    def requestLLMAnswer(self) -> None:
        """直接请求 LLM 作答（不拆解、不执行脚本）。回包经 flow_receive_complete 完成本 flow。"""
        if not (self.input.goal if self.input is not None else ""):
            # 无可作答问题：以错误完成本 flow，避免父 flow 干等卡死导致整体失败
            logger.warning("[%s][d=%s] 无可作答问题，以错误完成本 flow 避免卡死", self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_CONTENT: "无可作答问题"},
                AEFlowCompletEvent.error,
            )
            return
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{self.input.goal if self.input is not None else ''}"})
        # 以收到的 rolePrompt 作为作答指令（空则回退默认直接作答指令）
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: self.rolePrompt or f"请直接回答{AE_USER_QUESTION_PREFIX}",
        })
        flow_out = self.generateFlowOutput(AEFunctional.flow_receive_complete)
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)
