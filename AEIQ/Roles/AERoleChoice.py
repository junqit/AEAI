"""
AERoleChoice - 角色选择能力 mixin。

提供 requestRoleSelect / receiveRoleSelect（据问题与各角色能力返回一个或多个任务，按 role 派发对应角色 flow；
空则 requestDirectAnswer），
由 AERoleExcutor 继承获得。入口（AERefiner, role=None）选全部角色，深层（role 已配置）选 roles_below。
task 由 AETaskRole 经 _after_role_goal → requestScripts 直接处理，不经 requestRoleSelect。
"""
import logging

from WorkFlows.AEFlow import AEFlowCompletEvent
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowInfo import AE_IDENT, AE_ANSWER, AE_TITLE
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.AERoleType import (
    AEFlowRole, ROLE_PARAMS, roles_below,
    AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT,
)

logger = logging.getLogger(__name__)


class AERoleFunction(AEFunctional):
    """AERoleBase 角色选择回包功能性方法名（继承 AEFunctional 基类）。"""
    receiveRoleSelect = "receiveRoleSelect"  # 接收 LLM 选定的角色，传入 map


class AERoleChoice:
    """角色选择能力 mixin：按问题选择角色并派发（AERoleExcutor 或 AELLMRole）。"""

    def requestRoleSelect(self) -> None:
        """请求 LLM 据问题与各角色能力返回一个或多个执行任务（每项含 role），或空数组（llm 直接作答）。

        - 当前未配置 role（self.role 为 None，入口 refiner）：从全部角色（expert/workgroup/employee/task + llm 直答）中选；
        - 已配置 role：仅从其二级角色（roles_below(self.role)）中选，不得选 llm。
        选择须确保能切实解决用户的问题或目标，不得给出无法解决或拒绝的答案。
        """
        cur_role = self.role
        if cur_role is None:
            candidates = list(ROLE_PARAMS.keys())  # 全部角色（含 llm 直答）
        else:
            candidates = roles_below(cur_role)  # 仅二级角色（不含 llm）
            if not candidates:
                # 无可选下层角色，以错误完成闭环
                self.flow_receive_complete(
                    {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_ANSWER: "无可选下层角色"},
                    AEFlowCompletEvent.error,
                )
                return
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        question = self.roleGoal or (self.input.content if self.input is not None else "")
        if len(question) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{question}"})
        # 角色选择规则（system）：必须解决问题 + 网络请求类必选角色
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: (
                "角色选择规则：\n"
                "- 所选角色必须能够切实解决用户的问题或目标，不得给出无法解决或拒绝的答案；\n"
                "- 若问题需要获取网络数据、实时数据、资讯等需通过网络请求的内容，必须选择角色（不得选 llm）。"
            ),
        })
        # 候选角色花名册（system）：candidates 已含 llm（当 cur_role 为 None 时）
        role_lines = []
        for r in candidates:
            info = ROLE_PARAMS.get(r)
            if info is not None:
                role_lines.append(f"- {r.value}（{info.title}）：{info.responsibility}")
            else:
                role_lines.append(f"- {r.value}")
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: "可选角色：\n" + "\n".join(role_lines),
        })
        allowed = [r.value for r in candidates]
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"请根据{AE_USER_QUESTION_PREFIX}这一目标与任务，结合各角色能力，在 tasks 中列出子任务（可一个或多个），每项含 title（任务标题）、task（任务内容，可独立完成）、role（从上述可选角色中选最合适的一个，如 {' / '.join(allowed)}）。\n"
                "拆解层数和子任务数量应尽可能少，避免过度拆解。\n"
                "无需创建总结性或整合性的任务——每个子任务完成后，当前工作流会自动对全部子任务结果进行统计汇总。"
            ),
        })
        flow_out = self.generateFlowOutput(AERoleFunction.receiveRoleSelect)
        flow_out.set_llm_out({
            "tasks": [{
                AE_TITLE: llm_generate("任务标题"),
                "task": llm_generate("任务内容，可独立完成"),
                "role": llm_generate(f"执行角色 type，从可选角色中选，如 {' / '.join(allowed)}"),
            }]
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def _instantiate_role_flow(self, role_enum: AEFlowRole, ident: str):
        """按 role 映射实例化对应角色 flow（懒导入避免循环）。

        注册表覆盖 ROLE_PARAMS 全部角色：expert/workgroup/employee→对应子类，
        task→AETaskRole，llm→AELLMRole；未注册的 role 抛 KeyError。
        """
        from Roles.Defs.AELLMRole import AELLMRole
        from Roles.Defs.AEExpertRole import AEExpertRole
        from Roles.Defs.AEWorkgroupRole import AEWorkgroupRole
        from Roles.Defs.AEEmployeeRole import AEEmployeeRole
        from Roles.Defs.AETaskRole import AETaskRole
        role_class = {
            AEFlowRole.expert: AEExpertRole,
            AEFlowRole.workgroup: AEWorkgroupRole,
            AEFlowRole.employee: AEEmployeeRole,
            AEFlowRole.task: AETaskRole,
            AEFlowRole.llm: AELLMRole,
        }
        cls = role_class[role_enum]
        return cls(flowOutput=AEFlowOutput({AE_IDENT: ident, AE_ANSWER: llm_generate("任务结论")}))

    def receiveRoleSelect(self, data: dict) -> bool:
        """接收 LLM 返回的一个或多个任务：空 → llm 直接作答；非空 → 每项按 role 派发对应角色 flow（兄弟 flow，各自 task 内容）。"""
        cur_role = self.role
        allow_llm = cur_role is None
        allowed_roles = list(ROLE_PARAMS.keys()) if allow_llm else roles_below(cur_role)
        allowed_set = set(allowed_roles)
        tasks = data.get("tasks") if isinstance(data, dict) else None
        if tasks is None and isinstance(data, str):
            tasks = [tasks] if tasks.strip() else []
        elif not isinstance(tasks, list):
            tasks = []
        if not tasks:
            logger.info("[%s][%s][d=%s] 返回空任务，llm 直接作答", type(self).__name__, self.title, self.deepth)
            self.requestDirectAnswer()
            return True
        if self.delegate is None:
            logger.warning("[%s][%s][d=%s] delegate 未设置，无法派发角色 flow，回退直接作答", type(self).__name__, self.title, self.deepth)
            self.requestDirectAnswer()
            return True
        delegate_ident = self.delegate.ident
        created = 0
        for spec in tasks:
            if isinstance(spec, str):
                content = spec
                role_enum = None
            elif isinstance(spec, dict):
                content = spec.get("task") or spec.get(AE_TITLE) or ""
                role_str = (spec.get("role") or "").strip()
                if role_str.lower().startswith("type:"):
                    role_str = role_str.split(":", 1)[1].strip()
                try:
                    role_enum = AEFlowRole(role_str)
                except ValueError:
                    role_enum = None
            else:
                continue
            if role_enum is None or role_enum not in allowed_set:
                logger.warning("[%s][%s][d=%s] 子任务 role 非法或不在可选范围，跳过: spec=%r",
                               type(self).__name__, self.title, self.deepth, spec)
                continue
            content = str(content or "")
            sub = self._instantiate_role_flow(role_enum, delegate_ident)
            self.delegate.receive_add_flow(sub)
            sub.startFlow(AEFlowInput(content=content))
            created += 1
        if created == 0:
            logger.warning("[%s][%s][d=%s] 全部子任务 role 非法被跳过，回退 llm 直接作答", type(self).__name__, self.title, self.deepth)
            self.requestDirectAnswer()
            return True
        logger.info("[%s][%s][d=%s] 派发 %d 个角色 flow（兄弟 flow）", type(self).__name__, self.title, self.deepth, created)
        self.flow_receive_complete(
            {AE_IDENT: delegate_ident, AE_ANSWER: self.roleGoal},
            AEFlowCompletEvent.default,
        )
        return True
