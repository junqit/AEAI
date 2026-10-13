"""
AERoleExcuteLLM - LLM 直接作答角色 Flow（直继 AERoleBase，不经 AERoleExcutor 编排层）。

已是选定角色（无需再选角色）：自身驱动前置链路（角色信息 → 问题优化），在 receiveOptimizeInput
之后（input.goal 就绪）经 requestRoleSelect 决策「是否需要多个 LLM 进行分析」：
  - choice=True（入口）：requestRoleSelect 发起 requestMultiLLMDecision 决策请求
    （仅决策，不在此发起多 LLM 查询）。回包 receiveMultiLLMDecision：
      单一问题 → 自身 requestLLMAnswer 作答；
      多子问题 → 创建 choice=False 的子 AERoleExcuteLLM 并行查询，全部完成后由 summarize_to_llm 汇总。
  - choice=False（被派生的子节点）：跳过决策，直接 requestLLMAnswer 作答，避免递归。
_role()=llm；requestRoleSelect 为决策入口（替代默认的角色选择）。

与 AERoleExcutor 的差异：本类直继 AERoleBase，自带 on_flow_start / receiveRoleInfomation /
receiveOptimizeInput 三个编排方法驱动前置链路；receiveOptimizeInput 推进至 requestRoleSelect
（决策入口），不经 requestRoleChoice。多 LLM 子节点直接实例化 AERoleExcuteLLM，不经 _instantiate_role_flow
工厂（故无需 AESubRoleChoice mixin）。
"""
import logging

from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Roles.RoleBase.AERoleBase import AERoleBase
from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE, AEFlowRole
from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT, AE_IDENT
from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
from WorkFlows.FlowWork.AEFlowOutput import AEFlowOutput
from WorkFlows.FlowWork.AEFlowDelegate import AEFlowCompletEvent
from Tools.Excutor.AERuntimeExcutor import AEFunctional

logger = logging.getLogger(__name__)


class AERoleExcuteLLMFunction(AEFunctional):
    """AERoleExcuteLLM 专属回包功能性方法名。"""
    receiveMultiLLMDecision = "receiveMultiLLMDecision"  # 接收 LLM 对「是否需要多个 LLM 查询」的决策


class AERoleExcuteLLM(AERoleBase):
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

    # ==================== 前置链路编排（直继 AERoleBase 自带，不经 AERoleExcutor）====================

    def on_flow_start(self, flowInput) -> bool:
        """启动：基类置 input；未启动则错误完成，避免父 flow 等待卡死。"""
        if not super().on_flow_start(flowInput):
            logger.warning("[%s][d=%s] on_flow_start 失败：基类未启动", self.title, self.deepth)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_CONTENT: "flow 启动失败"},
                AEFlowCompletEvent.error,
            )
            return False
        self.requestRoleInformation()
        return True

    def receiveRoleInfomation(self, data: dict) -> bool:
        """接收角色信息：判断基类处理结果决定下一步（闭环 / 推进）。
        基类写入 title/responsibility，成功返回 True；失败（任一为空）返回 False（基类不闭环）。
        成功则推进 requestOptimizeInput（问题优化）；失败则以错误完成本 flow 闭环避免卡死，并返回 False 如实反映失败。"""
        result = super().receiveRoleInfomation(data)
        if not result or not self.title or not self.responsibility:
            logger.warning("[%s][d=%s] title 或 responsibility 为空，以错误完成本 flow 避免卡死", self.title, self.deepth)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident,
                 AE_CONTENT: "角色信息（title/responsibility）生成失败"},
                AEFlowCompletEvent.error,
            )
            return False
        self.requestOptimizeInput()
        return result

    def receiveOptimizeInput(self, data: dict) -> bool:
        """接收角色目标：基类存储后 input.goal 为空则错误完成；否则调 requestRoleSelect 推进（决策入口）。

        与 AERoleExcutor 不同处：推进至 requestRoleSelect（本类决策入口），而非 requestRoleChoice——
        LLM 角色已是选定角色，无需再选角色，直接进入「是否多 LLM 查询」决策。"""
        result = super().receiveOptimizeInput(data)  # 存储 input.goal
        if not result or not (self.input.get_goal() if self.input is not None else ""):
            logger.warning("[%s][d=%s] input.goal 为空，以错误完成本 flow 避免卡死",
                           self.title, self.deepth)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_CONTENT: "问题优化失败"},
                AEFlowCompletEvent.error,
            )
            return False
        self.requestRoleSelect()
        return result

    # ==================== 决策与作答 ====================

    def requestRoleSelect(self) -> None:
        """input.goal 就绪后的决策入口：choice=False 直接作答；choice=True 发起「是否多 LLM 查询」决策请求。"""
        if not self.choice:
            self.requestLLMAnswer()
            return
        self.requestMultiLLMDecision()

    def requestMultiLLMDecision(self) -> None:
        """请求 LLM 判断是否需要拆分为多个独立子问题分别查询。回包经 receiveMultiLLMDecision 处理。"""
        # input.goal 已由 receiveOptimizeInput 设置（为空时已错误完成）
        if not (self.input.get_goal() if self.input is not None else ""):
            logger.warning("[%s][d=%s] 无可作答问题，以错误完成本 flow 避免卡死", self.title, self.deepth)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_CONTENT: "无可作答问题"},
                AEFlowCompletEvent.error,
            )
            return
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: (self.input.get_goal() if self.input is not None else "")})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "判断上述问题是否需要拆分为多个独立子问题，分别交由不同 LLM 查询后再汇总：\n"
                "- 若问题单一、可一次性直接作答，返回空数组；\n"
                "- 若需多角度 / 多维度分别查询，返回各独立子问题（每个可独立完成、互不依赖）。\n"
                "输出 JSON 数组填入 questions 字段。"
            ),
        })
        flow_out = self.generateFlowOutput(AERoleExcuteLLMFunction.receiveMultiLLMDecision)
        flow_out.set_llm_out({"questions": [{AE_CONTENT: llm_generate("独立子问题，可独立完成且必须能解决目标")}]})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveMultiLLMDecision(self, data: dict) -> bool:
        """接收「是否多 LLM 查询」决策：单一问题 → 自身作答；多子问题 → 派生 choice=False 子节点并行查询。

        子节点直接实例化 AERoleExcuteLLM（不经 _instantiate_role_flow 工厂），故本类无需 AESubRoleChoice mixin。
        """
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
        # 多子问题：派生 choice=False 的子 AERoleExcuteLLM 并行查询，自身等待汇总
        created = 0
        for sq in sub_questions:
            child = AERoleExcuteLLM(
                flowOutput=AEFlowOutput(ident=self.ident, out_schema={AE_CONTENT: llm_generate("对用户的回复")}),
            )
            child.choice = False
            self.add_flow(child)
            child.receive_flow_input(AEFlowInput(content=sq, ident=child.ident))
            created += 1
        logger.info("[%s][d=%s] 拆分为 %d 个子 AERoleExcuteLLM 并行查询，等待汇总", self.title, self.deepth, created)
        return True

    def requestLLMAnswer(self) -> None:
        """直接请求 LLM 作答（不拆解、不执行脚本）。回包经 receive_summarize_result 完成本 flow。"""
        if not (self.input.get_goal() if self.input is not None else ""):
            # 无可作答问题：以错误完成本 flow，避免父 flow 干等卡死导致整体失败
            logger.warning("[%s][d=%s] 无可作答问题，以错误完成本 flow 避免卡死", self.title, self.deepth)
            self.flow_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_CONTENT: "无可作答问题"},
                AEFlowCompletEvent.error,
            )
            return
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: (self.input.get_goal() if self.input is not None else "")})
        # 以收到的 rolePrompt 作为作答指令（空则回退默认直接作答指令）
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: self.rolePrompt or "请直接回答上述问题",
        })
        flow_out = self.generateFlowOutput(AEFunctional.receive_summarize_result)
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)
