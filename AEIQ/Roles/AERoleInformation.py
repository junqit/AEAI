"""AERoleInformation - 角色信息能力 mixin：生成 title / responsibility / rolePrompt，由 AERoleBase 继承。
角色信息属性（role / title / responsibility / rolePrompt / roleGoal）由基类 AERoleInfo 持有。"""
import logging

from WorkFlows.AEFlowInfo import AE_IDENT, AE_TITLE, AE_ANSWER
from WorkFlows.AEFlowDelegate import AEFlowCompletEvent
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.AERoleType import AEConentRole, AE_ROLE, AE_CONTENT, AE_USER_QUESTION_PREFIX
from Roles.AERoleInfo import AERoleInfo

logger = logging.getLogger(__name__)


class AERoleInformationFunction(AEFunctional):
    """AERoleBase 角色信息回包功能性方法名。"""
    receiveRoleInfomation = "receiveRoleInfomation"
    receiveRolePrompt = "receiveRolePrompt"


class AERoleInformation(AERoleInfo):
    """角色信息能力 mixin：提供 title / responsibility / rolePrompt 生成请求。
    角色信息属性由基类 AERoleInfo 经 cooperative __init__ 持有。"""

    def requestRoleInformation(self) -> None:
        """请求 LLM 生成 title / responsibility（此时尚未确认，不注入 role_brief）。回包经 receiveRoleInfomation 写入并触发 requestRolePrompt。"""
        messages = []
        user_question = self.input.content if self.input else ""
        if len(user_question) > 0:
            messages.append({
                AE_ROLE: AEConentRole.SYSTEM.value,
                AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{user_question}",
            })

        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"根据{AE_USER_QUESTION_PREFIX}，生成工作名称与职责范围：\n"
                "- 工作名称：体现专业领域与定位；\n"
                "- 职责范围：明确职责边界与禁止事项。\n"
                "要求：生成内容须客观、完整，不得包含用户问题本身。"
            ),
        })
        flow_out = self.generateFlowOutput(AERoleInformationFunction.receiveRoleInfomation)
        flow_out.set_llm_out({
            AE_TITLE: llm_generate("工作名称，体现专业领域与定位"),
            "responsibility": llm_generate("职责范围，明确职责边界与禁止事项"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveRoleInfomation(self, data: dict) -> bool:
        """写入 title / responsibility；均非空则请求 rolePrompt，任一为空则以错误完成本 flow 避免卡死。"""
        if not isinstance(data, dict):
            data = {}
        self.title = data.get(AE_TITLE, "") or ""
        self.responsibility = data.get("responsibility", "") or ""
        if not self.title or not self.responsibility:
            logger.warning("[%s][%s][d=%s] title 或 responsibility 为空，以错误完成本 flow 避免卡死", type(self).__name__, self.title, self.deepth)
            self.flow_receive_complete({AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_ANSWER: "角色信息（title/responsibility）生成失败"}, AEFlowCompletEvent.error)
            return True
        self.requestRolePrompt()
        return True

    def requestRolePrompt(self) -> None:
        """基于 title + responsibility 生成角色专用 rolePrompt（与具体问题无关）。回包经 receiveRolePrompt 写入。"""
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "请根据以上工作名称与能力范围，生成一个本角色专用的提问转化指令(rolePrompt)："
                "用于把任意用户问题转化为契合你专业能力与职责边界的明确、可执行目标；"
                "指令只与你的职称与能力范围有关，不得引用任何具体问题；只输出指令文本本身，不要解释。"
            ),
        })
        flow_out = self.generateFlowOutput(AERoleInformationFunction.receiveRolePrompt)
        flow_out.set_llm_out({"rolePrompt": llm_generate("本角色专用的提问转化指令，体现职称与能力边界，不含具体问题")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveRolePrompt(self, data: dict) -> bool:
        """存入 self.rolePrompt（不完成 flow）。data 须为 {"rolePrompt": <...>} map；非 map 或 rolePrompt 为空则以错误完成闭环。"""
        if not isinstance(data, dict):
            logger.warning("[%s][%s][d=%s] rolePrompt 回包非 map，以错误完成: %r", type(self).__name__, self.title, self.deepth, data)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_ANSWER: "rolePrompt 生成失败（回包非 map）"},
                AEFlowCompletEvent.error,
            )
            return True
        prompt = data.get("rolePrompt") or ""
        if not prompt:
            logger.warning("[%s][%s][d=%s] rolePrompt 为空，以错误完成本 flow 避免卡死", type(self).__name__, self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_ANSWER: "rolePrompt 生成失败"},
                AEFlowCompletEvent.error,
            )
            return True
        self.rolePrompt = prompt
        return True
