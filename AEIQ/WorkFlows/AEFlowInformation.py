"""
AEFlowInformation - AEFlow 的父类：角色信息（title / responsibility / rolePrompt）生成请求。

将 requestRoleInformation / receiveRoleInfomation / requestRolePrompt / receiveRolePrompt
从 AEFlow 抽出至本父类，降低 AEFlow.py 体积。本类继承 AEFlowInfo；AEFlow 多继承本类。
AEFlowFunctional 在方法内懒导入以避免循环导入。

角色信息流程分两步：
  1. requestRoleInformation → receiveRoleInfomation：生成并写入 title / responsibility；
  2. receiveRoleInfomation 末尾调 requestRolePrompt → receiveRolePrompt：基于已定的职称/能力
     生成"针对用户问题的提问指令" rolePrompt 并写入 self.rolePrompt（不完成 flow）。
"""
import logging

from .AEFlowInfo import AEFlowInfo, AE_IDENT, AE_TITLE, AE_ANSWER
from .AEFlowDelegate import AEFlowCompletEvent
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Roles.AERoleType import AEConentRole, AE_ROLE, AE_CONTENT, AE_USER_QUESTION_PREFIX, ROLE_PARAMS

logger = logging.getLogger(__name__)


class AEFlowInformation(AEFlowInfo):
    """AEFlow 父类：角色信息生成（requestRoleInformation / receiveRoleInfomation /
    requestRolePrompt / receiveRolePrompt）。"""

    def requestRoleInformation(self) -> None:
        """根据问题内容(input.content)请求 LLM 生成自身工作名称(title)与能力范围(responsibility)。

        - messages: system(role_brief，含已有身份与能力，可为空) / system(用户问题，AE_USER_QUESTION_PREFIX 前缀) / system(生成需遵守的角色要求，来自 roleDescription) / user(生成指令，引用 AE_USER_QUESTION_PREFIX)
        - out_schema: {title, responsibility 占位}，由 LLM 填充
        - 走 receiveRoleInfomation：回包后写入 self.title / self.responsibility，并触发 requestRolePrompt 生成 rolePrompt（不完成 flow）
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
                f"根据{AE_USER_QUESTION_PREFIX}，生成工作名称与职责范围：\n"
                "- 工作名称：体现专业领域与定位；\n"
                "- 职责范围：明确职责边界与禁止事项。"
            ),
        })
        flow_out = self.flowOutput(AEFlowFunctional.receiveRoleInfomation)
        flow_out.set_llm_out({
            AE_TITLE: llm_generate("工作名称，体现专业领域与定位"),
            "responsibility": llm_generate("职责范围，明确职责边界与禁止事项"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveRoleInfomation(self, data: dict) -> bool:
        """接收 LLM 生成的工作名称与能力范围，写入 title / responsibility（不完成 flow），
        随后请求生成 rolePrompt（requestRolePrompt）。

        title 与 responsibility 均非空时返回 True 并请求 rolePrompt；任一为空时以 default 事件
        携带错误原因调 flow_receive_complete 完成本 flow（避免卡死），同样返回 True。

        Args:
            data: 回包内层 llm_out，形如 {AE_TITLE: <工作名称>, "responsibility": <能力范围>}

        Returns:
            bool: 始终 True（已处理：或继续链路，或错误兜底完成）
        """
        if not isinstance(data, dict):
            data = {}
        self.title = data.get(AE_TITLE, "") or ""
        self.responsibility = data.get("responsibility", "") or ""
        if not self.title or not self.responsibility:
            logger.warning("[%s][%s][d=%s] title 或 responsibility 为空，以错误完成本 flow 避免卡死", type(self).__name__, self.title, self.deepth)
            self.flow_receive_complete({AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_ANSWER: "角色信息（title/responsibility）生成失败"}, AEFlowCompletEvent.error)
            return True
        # title / responsibility 就绪后，请求生成 rolePrompt
        self.requestRolePrompt()
        return True

    def requestRolePrompt(self) -> None:
        """基于已生成的 title 与 responsibility，请求 LLM 生成"将用户问题转化为目标"的指令(rolePrompt)。

        rolePrompt 体现职称与能力边界，作为针对用户问题（AE_USER_QUESTION_PREFIX）的转化指令，
        用于把用户问题转化为明确、可执行的目标，使该目标契合本角色的专业能力与职责边界；
        后续步骤（requestOptimizeInput）以 rolePrompt 作为 user 指令作用于用户问题，产出目标。
        - messages: system(role_brief，含 title + responsibility) / system(用户问题，AE_USER_QUESTION_PREFIX 前缀) / user(生成指令)
        - out_schema: {rolePrompt 占位}，由 LLM 填充
        - 走 receiveRolePrompt：回包后存入 self.rolePrompt（不完成 flow）
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
                "请根据以上工作名称与能力范围，生成一个将用户问题转化为目标的指令(rolePrompt)："
                "用于把用户问题转化为明确、可执行的目标，使该目标契合你的专业能力与职责边界；只输出指令文本本身，不要解释。"
            ),
        })
        flow_out = self.flowOutput(AEFlowFunctional.receiveRolePrompt)
        flow_out.set_llm_out({"rolePrompt": llm_generate("将用户问题转化为目标的指令，体现职称与能力边界")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveRolePrompt(self, data: dict) -> bool:
        """接收 LLM 生成的 rolePrompt，存入 self.rolePrompt（不完成 flow）。

        Args:
            data: 回包内层 llm_out，形如 {"rolePrompt": <角色 prompt>}；若直接为字符串则视为 prompt

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        prompt = data.get("rolePrompt") if isinstance(data, dict) else None
        if prompt is None and isinstance(data, str):
            prompt = data
        self.rolePrompt = prompt or ""
        return True
