"""AERoleClarify - 角色信息能力 mixin：一次请求生成 title / responsibility / rolePrompt。
角色信息属性（role / title / responsibility / rolePrompt）由基类持有。"""
import logging

from WorkFlows.FlowWork.AEFlowInfo import AE_TITLE, AE_RESPONSIBILITY, AE_CONTENT
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
from Roles.RoleBase.AERole import AERole

logger = logging.getLogger(__name__)


class AERoleClarifyFunction(AEFunctional):
    """角色信息回包功能性方法名。"""
    receiveRoleInfomation = "receiveRoleInfomation"


class AERoleClarify(AERole):
    """角色信息能力 mixin：一次请求生成 title / responsibility / rolePrompt。"""

    # 请求 LLM 生成 title / responsibility / rolePrompt（一次请求），回包经 receiveRoleInfomation 写入
    def requestRoleInformation(self) -> None:
        messages = []
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: (
                "根据下方问题，生成解决该问题所需的角色信息，包含三个字段：\n"
                "- title（工作名称）：准确匹配该问题所需的解决角色名称\n"
                "- responsibility（职责范围）：该角色解决此问题的能力（能做什么、如何解决），明确职责边界与禁止事项；客观、完整，不含问题本身\n"
                "- rolePrompt（角色指令）：基于工作名称与职责范围的角色指令，指导如何将输入转化为符合该角色职责的可执行目标；仅基于角色定位，不引用具体问题；简洁、明确"
            ),
        })
        user_question = self.input.get_content() if self.input else ""
        user_msg = f"问题：\n{user_question}\n\n请生成上述三个字段。" if user_question else "请生成上述三个字段。"
        messages.append({AE_ROLE: AEConentRole.USER.value, AE_CONTENT: user_msg})
        flow_out = self.generateFlowOutput(AERoleClarifyFunction.receiveRoleInfomation)
        flow_out.set_llm_out({
            AE_TITLE: llm_generate("准确匹配该问题所需的解决角色名称"),
            AE_RESPONSIBILITY: llm_generate("该角色解决此问题的能力范围，明确能做什么、如何解决及职责边界，不含问题本身"),
            "rolePrompt": llm_generate("基于工作名称与职责范围的角色指令，指导如何将输入转化为符合该角色职责的可执行目标，不引用具体问题，简洁明确"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema, temperature=0.3)
        self.flow_send_llm_request(payload)

    # 写入 title / responsibility / rolePrompt；均非空返回 True，否则 False
    def receiveRoleInfomation(self, data: dict) -> bool:
        if not isinstance(data, dict):
            data = {}
        self.title = data.get(AE_TITLE, "") or ""
        self.responsibility = data.get(AE_RESPONSIBILITY, "") or ""
        self.rolePrompt = data.get("rolePrompt", "") or ""
        if not self.title or not self.responsibility or not self.rolePrompt:
            return False
        logger.info(
            "[%s][d=%s] 角色信息就绪:\n"
            "========================================\n"
            "  title: %s\n  responsibility: %s\n  rolePrompt: %s\n"
            "========================================",
            self.title, self.deepth, self.title, self.responsibility, self.rolePrompt,
        )
        return True
