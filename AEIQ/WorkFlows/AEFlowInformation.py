"""
AEFlowInformation - AEFlow 的父类：角色信息（title / responsibility / rolePrompt）生成请求。

将 requestRoleInformation / receiveRoleInfomation 从 AEFlow 抽出至本父类，降低 AEFlow.py 体积。
本类继承 AEFlowInfo；AEFlow 多继承本类。AEFlowFunctional 在方法内懒导入以避免循环导入。

角色信息为一个完整流程：requestRoleInformation 一次请求同时生成工作名称、能力范围与
"可包装所有问题的角色 prompt"，receiveRoleInfomation 一次接收并写入 self.title /
self.responsibility / self.rolePrompt（不完成 flow）。
"""
import logging

from .AEFlowInfo import AEFlowInfo, AE_TITLE
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Roles.AERole import AEConentRole, AE_ROLE, AE_CONTENT, AE_USER_QUESTION_PREFIX

logger = logging.getLogger(__name__)


class AEFlowInformation(AEFlowInfo):
    """AEFlow 父类：角色信息生成（requestRoleInformation / receiveRoleInfomation）。"""

    def requestRoleInformation(self) -> None:
        """根据问题内容(input.content)请求 LLM 一次生成自身工作名称(title)、能力范围
        (responsibility)与"可包装所有问题的角色 prompt"(rolePrompt)——三者同属一个完整流程。

        - messages: system(role_brief，含已有身份与能力，可为空) / system(用户问题，AE_USER_QUESTION_PREFIX 前缀) / system(生成需遵守的角色要求，来自 roleDescription) / user(生成指令，引用 AE_USER_QUESTION_PREFIX)
        - out_schema: {title, responsibility, rolePrompt 占位}，由 LLM 填充
        - 走 receiveRoleInfomation：回包后写入 self.title / self.responsibility / self.rolePrompt（不完成 flow）
        """
        from WorkFlows.AEFlow import AEFlowFunctional  # 懒导入避免循环
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        # 用户问题以统一前缀（AE_USER_QUESTION_PREFIX）单独作为 system 消息传入
        user_question = self.input.content if self.input else ""
        if len(user_question) > 0:
            messages.append({
                AE_ROLE: AEConentRole.SYSTEM.value,
                AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{user_question}",
            })
        # 生成角色信息时需遵守的角色要求（来自 roleDescription）
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: f"生成角色信息时需遵守以下角色要求：\n{self.roleDescription()}",
        })
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"请根据{AE_USER_QUESTION_PREFIX}，生成你的工作名称、能力范围与一个针对用户问题的提问指令(rolePrompt)；"
                "工作名称需体现专业领域与定位，能力范围需明确职责边界与禁止事项；"
                "rolePrompt 须体现你的职称与能力边界，作为针对用户问题（AE_USER_QUESTION_PREFIX）所提的提问/优化指令，"
                "使该问题在被其引导后能以本角色身份被准确优化与处理；只输出指令文本，引用 AE_USER_QUESTION_PREFIX 指代用户问题。"
            ),
        })
        flow_out = self.flowOutput(AEFlowFunctional.receiveRoleInfomation)
        flow_out.set_llm_out({
            AE_TITLE: llm_generate("工作名称，体现专业领域与定位"),
            "responsibility": llm_generate("能力范围，明确职责边界与禁止事项"),
            "rolePrompt": llm_generate("针对用户问题(AE_USER_QUESTION_PREFIX)的提问/优化指令，体现职称与能力边界"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveRoleInfomation(self, data: dict) -> bool:
        """接收 LLM 生成的角色信息，写入 title / responsibility / rolePrompt（不完成 flow）。

        title 与 responsibility 均非空时返回 True；任一为空返回 False。

        Args:
            data: 回包内层 llm_out，形如
                  {AE_TITLE: <工作名称>, "responsibility": <能力范围>, "rolePrompt": <角色 prompt>}

        Returns:
            bool: title 与 responsibility 均有值时 True，否则 False
        """
        if not isinstance(data, dict):
            data = {}
        self.title = data.get(AE_TITLE, "") or ""
        self.responsibility = data.get("responsibility", "") or ""
        self.rolePrompt = data.get("rolePrompt", "") or ""
        logger.info(
            "[AEFlow:%s] 收到角色信息:\ntitle=%r\nresponsibility=%r\nrolePrompt=%r",
            self.ident, self.title, self.responsibility, self.rolePrompt,
        )
        if not self.title or not self.responsibility:
            logger.warning("[AEFlow:%s] title 或 responsibility 为空，返回 False", self.ident)
            return False
        return True
