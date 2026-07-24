"""AEExpert - 专家级拆解能力 mixin。

提供 requestDecompose / receiveDecompose：按层级向下分解目标为子任务。
AERoleExcutor 继承本 mixin 获得拆解能力（expert/workgroup/employee 共用）。
"""
import logging

from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowInfo import AE_IDENT, AE_TITLE
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Roles.AERoleType import AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT, AEFlowRole

logger = logging.getLogger(__name__)


class AEExpertMixin:
    """专家级拆解能力：按层级将目标分解为更小的角色子任务。"""

    def requestDecompose(self) -> None:
        """按层级向下分解：请求 LLM 将目标拆解为子任务，每个子任务可分配给当前角色以下任一层级。
        已到最底层(task)则不再拆解，直接 requestQuestionType 执行。
        """
        from Roles.AERoleType import roles_below, ROLE_PARAMS
        from Roles.AERoleExcutor import AERoleExcutorFunction
        below = roles_below(self.role)
        if not below:
            logger.info("[%s] role=%s 已为最底层，转执行类型判定", self.ident, self.role.value)
            self.requestQuestionType()
            return
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{self.optimizePromptResult}",
        })
        role_lines = []
        for r in below:
            info = ROLE_PARAMS.get(r)
            if info is not None:
                role_lines.append(f"- type: {r.value}；职称：{info.title}；职责：{info.responsibility}")
            else:
                role_lines.append(f"- type: {r.value}；原子任务（task），不再拆解，直接执行")
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: "可选下层角色（为每个子任务选最合适的一个 type）：\n" + "\n".join(role_lines),
        })
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"请将{AE_USER_QUESTION_PREFIX}这一目标与任务拆解为可独立完成的子任务，"
                "并为每个子任务从上述下层角色中选择最合适的执行层级。"
                "在 tasks 中列出，每项含 title（任务标题）、task（任务内容，可独立完成）、role（从上述 type 中选）；"
                "若该目标已足够原子、无需进一步拆解，返回空数组 []。"
            ),
        })
        logger.info("[%s] role=%s → 拆解，可选下层: %s", self.ident, self.role.value, [r.value for r in below])
        flow_out = self.flowOutput(AERoleExcutorFunction.receiveDecompose)
        flow_out.set_llm_out({
            "tasks": [{
                AE_TITLE: llm_generate("任务标题"),
                "task": llm_generate("任务内容，可独立完成"),
                "role": llm_generate("执行角色 type，从可选下层中选"),
            }]
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveDecompose(self, data: dict) -> bool:
        """接收 LLM 拆解出的子任务及所选层级：按每项 role 创建 AERoleExcutor subFlow 并启动；
        为空或已到最底层则转 requestQuestionType 走脚本/直接作答。
        """
        from Roles.AERoleType import roles_below
        below = roles_below(self.role)
        if not below:
            self.requestQuestionType()
            return True
        tasks = data.get("tasks") if isinstance(data, dict) else None
        if tasks is None and isinstance(data, str):
            tasks = [tasks] if tasks.strip() else []
        elif not isinstance(tasks, list):
            tasks = []
        if not tasks:
            logger.info("[%s] 目标已原子，转执行类型判定", self.ident)
            self.requestQuestionType()
            return True
        below_set = set(below)
        default_role = below[0]
        from Roles.AERoleExcutor import AERoleExcutor
        for spec in tasks:
            if isinstance(spec, str):
                content = spec
                role_enum = default_role
            elif isinstance(spec, dict):
                content = spec.get("task") or spec.get(AE_TITLE) or ""
                role_str = (spec.get("role") or "").strip()
                try:
                    role_enum = AEFlowRole(role_str)
                except ValueError:
                    role_enum = default_role
            else:
                continue
            if role_enum not in below_set:
                logger.warning("[%s] 子任务 role=%r 不在可选下层内，回退 %s",
                               self.ident, role_enum.value, default_role.value)
                role_enum = default_role
            content = str(content or "")
            sub = AERoleExcutor(
                flowOutput=AEFlowOutput({AE_IDENT: self.ident, "reply": llm_generate("任务结论")}),
            )
            sub.role = role_enum
            self.addFlow(sub)
            sub.startFlow(AEFlowInput(content=content))
            logger.info("[%s] 创建 subFlow(role=%s): ident=%s | 子任务=%s",
                        self.ident, role_enum.value, sub.ident, content)
        return True
