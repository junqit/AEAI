"""AERoleInformation - 角色信息能力 mixin：生成 title / responsibility / rolePrompt，由 AERoleBase 继承。
角色信息属性（role / title / responsibility / rolePrompt）由基类 AERole 持有。"""
import logging

from WorkFlows.FlowWork.AEFlowInfo import AE_TITLE, AE_CONTENT, AE_RESPONSIBILITY
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.Role.AERoleType import AEConentRole, AE_ROLE
from Roles.Role.AERole import AERole

logger = logging.getLogger(__name__)


class AERoleInformationFunction(AEFunctional):
    """AERoleBase 角色信息回包功能性方法名。"""
    receiveRoleInfomation = "receiveRoleInfomation"
    receiveRolePrompt = "receiveRolePrompt"


class AERoleInformation(AERole):
    """角色信息能力 mixin：提供 title / responsibility / rolePrompt 生成请求。
    角色信息属性由基类 AERole 经 cooperative __init__ 持有。"""

    def requestRoleInformation(self) -> None:
        """请求 LLM 生成 title / responsibility：据当前问题生成「工作名称」与「职责范围」。回包经 receiveRoleInfomation 写入。"""
        messages = []
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: (
                "生成解决当前问题所需的「工作名称」与「职责范围」，要求：\n"
                "- 工作名称：准确、完整地解决当前问题所需的角色名称；\n"
                "- 职责范围：明确解决问题所需的能力（能做什么、如何解决），并明确职责边界与禁止事项；客观、完整，不得包含用户问题本身。"
            ),
        })
        user_question = self.input.get_content() if self.input else ""
        user_msg = "请据上述角色生成规则，生成「准确、完整解决当前问题所需的角色名称」与「解决问题的能力范围」。"
        if user_question:
            user_msg += f"\n\n用户问题：\n{user_question}"
        messages.append({AE_ROLE: AEConentRole.USER.value, AE_CONTENT: user_msg})
        flow_out = self.generateFlowOutput(AERoleInformationFunction.receiveRoleInfomation)
        flow_out.set_llm_out({
            AE_TITLE: llm_generate("准确、完整解决当前问题所需的角色名称"),
            AE_RESPONSIBILITY: llm_generate("解决问题的能力范围，明确能做什么、如何解决及边界"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveRoleInfomation(self, data: dict) -> bool:
        """写入 title / responsibility（不串联、不闭环；由 AERoleExcutor 覆写判断并推进）。
        成功（均非空）返回 True；任一为空返回 False（不在此闭环，由覆写层错误完成）。"""
        if not isinstance(data, dict):
            data = {}
        self.title = data.get(AE_TITLE, "") or ""
        self.responsibility = data.get(AE_RESPONSIBILITY, "") or ""
        if not self.title or not self.responsibility:
            return False
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
                "根据以上职称与能力范围，生成一条角色指令（rolePrompt）。\n"
                "要求：\n"
                "- 仅基于职称与能力范围，不引用任何具体问题\n"
                "- 指导如何将输入转化为符合该角色职责的可执行目标\n"
                "- 简洁、明确，只输出指令文本"
            ),
        })
        flow_out = self.generateFlowOutput(AERoleInformationFunction.receiveRolePrompt)
        flow_out.set_llm_out({"rolePrompt": llm_generate("基于职称与能力范围的角色指令，不含具体问题")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveRolePrompt(self, data: dict) -> bool:
        """存入 self.rolePrompt（不串联、不闭环；由 AERoleExcutor 覆写判断并推进）。
        成功（非空 map）返回 True；非 map 或 rolePrompt 为空返回 False（不在此闭环）。"""
        if not isinstance(data, dict):
            data = {}
        prompt = data.get("rolePrompt") or ""
        if not prompt:
            return False
        self.rolePrompt = prompt
        logger.info(
            "[%s][d=%s] 角色信息就绪:\n"
            "========================================\n"
            "  role: %s\n  deepth: %s\n  title: %s\n  responsibility: %s\n  rolePrompt: %s\n"
            "========================================",
            self.title, self.deepth,
            self.role, self.deepth, self.title, self.responsibility, self.rolePrompt,
        )
        return True
