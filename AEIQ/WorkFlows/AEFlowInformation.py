"""
AEFlowInformation - AEFlow 的父类：角色信息（title / responsibility）生成请求。

将 requestRoleInformation / receiveRoleInfomation 从 AEFlow 抽出至本父类，降低 AEFlow.py 体积。
本类继承 AEFlowInfo；AEFlow 多继承本类。AEFlowFunctional 在方法内懒导入以避免循环导入。
"""
import logging

from .AEFlowInfo import AEFlowInfo, AE_TITLE
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Roles.AERole import AEConentRole, AE_ROLE, AE_CONTENT, AE_USER_QUESTION_PREFIX

logger = logging.getLogger(__name__)


class AEFlowInformation(AEFlowInfo):
    """AEFlow 父类：角色信息生成（requestRoleInformation / receiveRoleInfomation）。"""

    def requestRoleInformation(self) -> None:
        """根据问题内容(input.content)请求 LLM 生成自身工作名称(title)与能力范围(responsibility)。

        - messages: system(role_brief，含已有身份与能力，可为空) / system(用户问题，AE_USER_QUESTION_PREFIX 前缀) / user(生成角色指令，引用 AE_USER_QUESTION_PREFIX)
        - out_schema: {title, responsibility 占位}，由 LLM 填充
        - 走 receiveRoleInfomation：回包后写入 self.title / self.responsibility（不完成 flow）
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
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"请根据{AE_USER_QUESTION_PREFIX}，生成你的工作名称与能力范围；"
                "工作名称需体现专业领域与定位，能力范围需明确职责边界与禁止事项。"
            ),
        })
        flow_out = self.flowOutput(AEFlowFunctional.receiveRoleInfomation)
        flow_out.set_llm_out({
            AE_TITLE: llm_generate("工作名称，体现专业领域与定位"),
            "responsibility": llm_generate("能力范围，明确职责边界与禁止事项"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveRoleInfomation(self, data: dict) -> bool:
        """接收 LLM 生成的自身工作名称与能力范围，写入 title / responsibility（不完成 flow）。

        title 与 responsibility 均非空时返回 True；任一为空返回 False。

        Args:
            data: 回包内层 llm_out，形如 {AE_TITLE: <工作名称>, "responsibility": <能力范围>}

        Returns:
            bool: title 与 responsibility 均有值时 True，否则 False
        """
        if not isinstance(data, dict):
            data = {}
        self.title = data.get(AE_TITLE, "") or ""
        self.responsibility = data.get("responsibility", "") or ""
        logger.info(
            "[AEFlow:%s] 收到角色信息:\ntitle=%r\nresponsibility=%r",
            self.ident, self.title, self.responsibility,
        )
        if not self.title or not self.responsibility:
            logger.warning("[AEFlow:%s] title 或 responsibility 为空，返回 False", self.ident)
            return False
        
        return True
