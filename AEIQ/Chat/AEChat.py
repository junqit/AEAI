"""
AEChat - 聊天 Flow，继承 AEFlow。

接收 AENetQues 网络消息并处理（构建 LLM 请求、驱动子 flow 等）。

【整体流程设计目标】
当前实现仅含 AERefiner（问题精炼）→ AERoleExcutor（角色拆解/执行）两个子 flow，
属于过渡方案，无法从根本上保证问题被完整解决。完整流程应按以下 7 个阶段串联，
每阶段有明确的输入、方法与产物，逐阶段收敛，最终产出可验证的结论并沉淀知识：

  1. 获取并确认上下文
     方法：收集信息、提出澄清问题、检索知识
     输入：用户问题、历史上下文、文档
     产物：完整的问题描述
  2. 理解并定义问题
     方法：提炼目标、识别约束、定义成功标准
     输入：上下文
     产物：Problem Statement
  3. 分析原因 / 拆解任务
     方法：Root Cause Analysis、Task Planning
     输入：Problem Statement
     产物：子任务列表、假设
  4. 制定解决方案
     方法：生成多个方案并评估 Trade-off
     输入：子任务
     产物：Execution Plan
  5. 执行
     方法：调用 Tool、API、Code、Search、Database
     输入：Execution Plan
     产物：执行结果
  6. 验证结果
     方法：自检、测试、事实校验、是否满足目标
     输入：执行结果
     产物：Pass / Fail
  7. 总结沉淀
     方法：总结经验、更新 Memory、生成文档
     输入：全流程
     产物：Knowledge、Memory

阶段 6 验证失败应回流至 3/4 重新拆解或调整方案，形成闭环，而非直接产出。
"""
import logging
from typing import Optional

from WorkFlows.AEFlow import AEFlow
from WorkFlows.AEFlowInfo import AE_IDENT, AE_ANSWER
from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowDelegate import AEFlowCompletEvent
from Network.Core.AENetReq import AENetReqInfo
from Roles.Defs.AERefiner import AERefiner

logger = logging.getLogger(__name__)


class AEChat(AEFlow):
    """聊天 Flow：由 context 构建 input 后交 startFlow 启动。

    TODO：当前仅 AERefiner → AERoleExcutor 两个子 flow（过渡实现），后续应重构为
    上述 7 阶段流水线（上下文确认 → 问题定义 → 拆解 → 方案 → 执行 → 验证 → 沉淀），
    以根本性保证问题被完整解决并形成可验证闭环。
    """

    def __init__(self, flowOutput: AEFlowOutput, ident: str = ""):
        super().__init__(flowOutput=flowOutput, ident=ident)
        # 职称
        self.title = "Chat"
        # 触发本 chat 的请求信息（回响应时回填 req，供客户端按 path 路由）
        self.req: Optional[AENetReqInfo] = None
        # 添加首个子 flow：问题精炼（delegate 设为当前 chat，LLM 请求经 chat 向上转发）
        # refiner 的 output.ident 填本 chat.ident，使其完成时路由回本 chat 的 receive_flow_result
        from Context.Context.AELLMPayload import llm_generate
        refiner_output = AEFlowOutput({AE_IDENT: self.ident, AE_ANSWER: llm_generate("精炼后的问题")})
        refiner = AERefiner(flowOutput=refiner_output)
        self.addFlow(refiner)

    def summarize_user_instruction(self) -> str:
        """覆写：面向用户的最终回答用自然、人性化的口吻，不暴露内部拆解过程。

        summarize_to_llm 由 AEFlowDelegateImpl 实现，AEChat 仅覆写本指令定制口吻。
        """
        return (
            "请结合以上信息，以自然、人性化的口吻直接回答用户的问题，像在与人对话一样："
            "语言流畅亲切、通俗易懂，避免机械罗列或生硬的总结腔；"
            "务必保留所有关键事实与重要细节，不得遗漏或弱化要点，仅对冗余重复的内容去重；"
            "不要提及内部的拆解、角色、任务等执行过程，直接给出对用户有用的最终回答。"
        )

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动 chat flow：交基类置 input 并切到 processing，随后启动首个子 flow。

        - 仅当基类 startFlow 返回 True（成功启动）时，才取首个子 flow（问题精炼）启动
        - 任一启动失败均以错误回调 complete 闭环，避免会话永挂
        """
        if not super().startFlow(flowInput):
            logger.warning("[%s][%s][d=%s] startFlow 失败：基类未启动（非 default 状态），以错误完成闭环", type(self).__name__, self.title, self.deepth)
            self.flow_receive_complete({AE_IDENT: self.ident, AE_ANSWER: "会话启动失败：当前状态非初始态"}, AEFlowCompletEvent.error)
            return
        next_flow = self.nextFlow()
        if next_flow is None:
            logger.warning("[%s][%s][d=%s] startFlow 失败：无 default 状态子 flow 可启动，以错误完成闭环", type(self).__name__, self.title, self.deepth)
            self.flow_receive_complete({AE_IDENT: self.ident, AE_ANSWER: "会话启动失败：无可执行的子任务"}, AEFlowCompletEvent.error)
            return
        next_flow.startFlow(flowInput)


