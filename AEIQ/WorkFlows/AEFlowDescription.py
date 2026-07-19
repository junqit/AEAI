"""
AEFlowDescription - AEFlow 的父类：角色信息（title / responsibility）生成请求。

将 requestRoleInfo / receiveRole 从 AEFlow 抽出至本父类，降低 AEFlow.py 体积。
本类继承 AEFlowInfo；AEFlow 多继承本类。AEFlowFunctional 在方法内懒导入以避免循环导入。
"""
import logging

from .AEFlowInfo import AEFlowInfo
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Roles.AERole import AEConentRole, AE_ROLE, AE_CONTENT

logger = logging.getLogger(__name__)


class AEFlowDescription(AEFlowInfo):
    """AEFlow 父类：角色信息生成（requestRoleInfo / receiveRole）。"""

    def requestRoleInfo(self) -> None:
        """根据问题内容(input.content)请求 LLM 生成自身工作名称(title)与能力范围(responsibility)。

        - messages: system(role_brief，含已有身份与能力，可为空) / user(问题内容 + 生成角色指令)
        - out_schema: {title, responsibility 占位}，由 LLM 填充
        - 走 receiveRole：回包后写入 self.title / self.responsibility（不完成 flow）
        """
        from WorkFlows.AEFlow import AEFlowFunctional  # 懒导入避免循环
        messages = []
        role_brief = self.role_brief
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "请根据以下问题内容，生成你的工作名称与能力范围；工作名称需体现专业领域与定位，"
                f"能力范围需明确职责边界与禁止事项。\n问题内容：{self.input.content if self.input else ''}"
            ),
        })
        flow_out = self.flowOutput(AEFlowFunctional.receiveRole)
        flow_out.set_llm_out({
            "title": llm_generate("工作名称，体现专业领域与定位"),
            "responsibility": llm_generate("能力范围，明确职责边界与禁止事项"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveRole(self, data: dict) -> bool:
        """接收 LLM 生成的自身工作名称与能力范围，写入 title / responsibility（不完成 flow）。

        Args:
            data: 回包内层 llm_out，形如 {"title": <工作名称>, "responsibility": <能力范围>}

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        if not isinstance(data, dict):
            data = {}
        self.title = data.get("title", "") or ""
        self.responsibility = data.get("responsibility", "") or ""
        logger.info(
            "[AEFlow:%s] 收到角色信息:\ntitle=%r\nresponsibility=%r",
            self.ident, self.title, self.responsibility,
        )
        return True
