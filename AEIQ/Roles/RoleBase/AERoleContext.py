"""AERoleContext - 目标所需背景信息与上下文识别能力 mixin。

提供 requestContextNeeded / receiveContextNeeded：当用户问题/目标最终确认后，请求 LLM 分析
为完成该目标需要什么样的背景信息与上下文，结果存入 self.input（context），供后续执行/拆解参考。
区别于 AERoleExcuteContext（执行层：必要参数准备 + 缺失信息派发解决）：本 mixin 只做「需要什么」
的识别，不派发子 flow；方法名刻意区隔以避免与 AERoleExcuteContext.requestContext/receiveContext 冲突。
"""
import logging

from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
from Roles.RoleBase.AERole import AERole

logger = logging.getLogger(__name__)


class AERoleContextFunction(AEFunctional):
    """背景信息与上下文识别回包功能性方法名。"""
    receiveContextNeeded = "receiveContextNeeded"


class AERoleContext(AERole):
    """目标所需背景信息与上下文识别 mixin：分析完成目标需要什么背景信息与上下文，存 input.context。"""

    # 请求 LLM 分析完成目标所需的背景信息与上下文，回包经 receiveContextNeeded 写入
    def requestContextNeeded(self) -> None:
        goal = self.input.get_goal() if self.input is not None else ""
        if not goal:
            logger.warning("[%s][d=%s] 无 input.goal，跳过背景信息识别", self.title, self.deepth)
            return
        # SYSTEM 放角色身份（title+responsibility，不含铁律）
        system_parts = []
        if self.title:
            system_parts.append(f"你的身份是：{self.title}")
        if self.responsibility:
            system_parts.append(f"你的能力范围是：{self.responsibility}")
        messages = []
        if system_parts:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: "".join(system_parts)})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "基于当前工作名称与能力范围，分析完成下方【目标】需要什么样的背景信息与上下文。\n"
                "要求：\n"
                "- background：完成该目标所需的背景信息（领域知识、前置条件、约束等）；\n"
                "- context：完成该目标所需的上下文项列表（如时间、地点、数据来源、格式、相关实体等）；\n"
                "- 仅识别「需要什么」，不臆造具体值、不偏离目标。\n"
                "\n"
                "【目标】\n" + goal
            ),
        })
        flow_out = self.generateFlowOutput(AERoleContextFunction.receiveContextNeeded)
        flow_out.set_llm_out({
            "background": llm_generate("完成目标所需的背景信息"),
            "context": [llm_generate("完成目标所需的上下文项")],
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.flow_send_llm_request(payload)

    # 接收背景信息与上下文，存入 input.context；空则返回 False（不闭环）
    def receiveContextNeeded(self, data: dict) -> bool:
        if isinstance(data, dict):
            background = data.get("background", "") or ""
            context_items = data.get("context", [])
        else:
            background = ""
            context_items = []
        if not isinstance(context_items, list):
            context_items = [str(context_items)] if context_items else []
        context_items = [str(c).strip() for c in context_items if str(c).strip()]
        if not background and not context_items:
            logger.warning("[%s][d=%s] 背景信息与上下文识别为空", self.title, self.deepth)
            return False
        if self.input is not None:
            if background:
                self.input.add_context("background", background)
            if context_items:
                self.input.add_context("context_needed", context_items)
        logger.info("[%s][d=%s] 背景信息与上下文识别完成: background=%s, context_needed=%s",
                    self.title, self.deepth, background, context_items)
        return True
