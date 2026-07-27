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
                f"请根据{AE_USER_QUESTION_PREFIX}这一目标与任务，结合你的专业能力判断："
                "该任务是否需要拆解？以最小代价解决问题为原则——"
                "若目标简单可直接执行，无需拆解，返回空数组 []；"
                "若确需拆解，在 tasks 中列出子任务，每项含 title（任务标题）、task（任务内容，可独立完成）、role（从上述下层角色中选最合适的执行层级）。"
                "拆解层数和子任务数量应尽可能少，避免过度拆解。"
                "无需创建总结性或整合性的任务——每个子任务完成后，当前工作流会自动对全部子任务结果进行统计汇总。"
            ),
        })
        logger.info("[%s][%s][d=%s] role=%s → 拆解，可选下层: %s", type(self).__name__, self.title, self.deepth, self.role.value, [r.value for r in below])
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
        为空则转 requestQuestionType 走脚本/直接作答。

        注：requestDecompose 已在发请求前判断 below 是否为空，为空则直接 requestQuestionType
        不会发拆解请求，故本方法无需重复判断 below。
        role 必须在 roles_below(self.role) 范围内，不在则报错跳过该子任务。
        若全部子任务都被跳过（0 个 subFlow 创建），回退到 requestQuestionType 直接执行。
        """
        from Roles.AERoleType import roles_below
        from Roles.AERoleExcutor import AERoleExcutor
        tasks = data.get("tasks") if isinstance(data, dict) else None
        if tasks is None and isinstance(data, str):
            tasks = [tasks] if tasks.strip() else []
        elif not isinstance(tasks, list):
            tasks = []
        if not tasks:
            self.requestQuestionType()
            return True
        below_set = set(roles_below(self.role))
        created = 0
        for spec in tasks:
            if isinstance(spec, str):
                content = spec
                role_enum = None
            elif isinstance(spec, dict):
                content = spec.get("task") or spec.get(AE_TITLE) or ""
                role_str = (spec.get("role") or "").strip()
                # 兼容 LLM 返回 "type: task" 格式，去掉 "type:" 前缀
                if role_str.lower().startswith("type:"):
                    role_str = role_str.split(":", 1)[1].strip()
                try:
                    role_enum = AEFlowRole(role_str)
                except ValueError:
                    role_enum = None
            else:
                continue
            if role_enum is None or role_enum not in below_set:
                logger.error("[%s][%s][d=%s] 子任务 role 非法或不在可选下层内，跳过: spec=%r",
                             type(self).__name__, self.title, self.deepth, spec)
                continue
            content = str(content or "")
            has_next = bool(roles_below(role_enum))
            sub = AERoleExcutor(
                flowOutput=AEFlowOutput({AE_IDENT: self.ident, "reply": llm_generate("任务结论")}),
            )
            sub.role = role_enum
            self.addFlow(sub)
            sub.startFlow(AEFlowInput(content=content))
            created += 1
            logger.info("[%s][%s][d=%s] 创建 subFlow(role=%s, 可继续拆解=%s): 子任务=%s",
                        type(self).__name__, self.title, self.deepth, role_enum.value, has_next, content)
        # 全部子任务被跳过，无 subFlow 创建 → 回退直接执行
        if created == 0:
            logger.warning("[%s][%s][d=%s] 全部子任务 role 非法被跳过，回退直接执行", type(self).__name__, self.title, self.deepth)
            self.requestQuestionType()
        return True
