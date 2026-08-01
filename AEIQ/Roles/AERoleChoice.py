"""
AERoleChoice - 角色选择能力 mixin。

提供 requestRoleSelect / receiveRoleSelect（据问题与各角色能力返回一个或多个任务，按 role 派发对应角色 flow；
空则以错误完成闭环），
由 AERoleExcutor 继承获得。入口（AERefiner, role=None）选全部角色，深层（role 已配置）选 roles_below。
task 由 AETaskRole 经 requestRoleSelect → requestScripts 直接处理，不经 requestRoleSelect。
"""
import logging

from WorkFlows.FlowWork.AEFlow import AEFlowCompletEvent
from WorkFlows.FlowWork.AEFlowOutput import AEFlowOutput
from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
from WorkFlows.FlowWork.AEFlowInfo import AE_IDENT, AE_ANSWER, AE_TITLE
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
                f"目标：{AE_USER_QUESTION_PREFIX}\n\n"
                f"请基于上述目标和可选角色的能力，拆解为可独立执行的工作流，输出 JSON 数组填入 workflows 字段。\n"
                f"每个工作流包含：\n"
                f"  - title：简短标题\n"
                f"  - goal：该工作流的具体目标，必须可独立完成\n"
                f"  - role：执行角色，从可选角色中选（{', '.join(allowed)}）\n\n"
                f"要求：\n"
                f"1. 所列工作流合起来必须完整解决目标，不得遗漏\n"
                f"2. 每个工作流必须能独立完成，不依赖其他工作流的结果\n"
                f"3. 工作流数量尽可能少，避免过度拆解\n"
                f"4. 不需要创建总结或汇总类工作流，系统会自动汇总全部结果"
            ),
        })
        flow_out = self.generateFlowOutput(AERoleFunction.receiveRoleSelect)
        flow_out.set_llm_out({
            "workflows": [{
                AE_TITLE: llm_generate("标题"),
                "goal": llm_generate("工作流目标，可独立完成且必须能解决目标"),
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

    def _create_role_flows(self, roles: list, is_subflow: bool = True) -> int:
        """根据工作流列表创建角色 flow 并启动。

        Args:
            roles: 工作流列表，每项含 role / goal / title。
            is_subflow: True → 加入自己的 _flows（self.addFlow，AE_IDENT=self.ident）；
                        False → 加入 delegate 作为兄弟 flow（delegate.receive_add_flow，AE_IDENT=delegate.ident）。

        Returns:
            创建并启动的 flow 数量。
        """
        if not is_subflow and self.delegate is None:
            return 0
        target_ident = self.ident if is_subflow else self.delegate.ident
        allowed_roles = list(ROLE_PARAMS.keys()) if self.role is None else roles_below(self.role)
        allowed_set = set(allowed_roles)
        created = 0
        for spec in roles:
            if isinstance(spec, str):
                content = spec
                role_enum = None
            elif isinstance(spec, dict):
                content = spec.get("goal") or spec.get(AE_TITLE) or ""
                role_str = (spec.get("role") or "").strip()
                if role_str.lower().startswith("type:"):
                    role_str = role_str.split(":", 1)[1].strip()
                try:
                    role_enum = AEFlowRole(role_str)
                except ValueError:
                    logger.warning("[%s][d=%s] 子任务 role 无法解析: %r", self.title, self.deepth, role_str)
                    role_enum = None
            else:
                continue
            if role_enum is None or role_enum not in allowed_set:
                logger.warning("[%s][d=%s] 子任务 role 非法或不在可选范围，跳过: spec=%r",
                               self.title, self.deepth, spec)
                continue
            content = str(content or "")
            sub = self._instantiate_role_flow(role_enum, target_ident)
            if is_subflow:
                self.addFlow(sub)
            else:
                self.delegate.receive_add_flow(sub)
            sub.startFlow(AEFlowInput(content=content))
            created += 1
        return created

    def receiveRoleSelect(self, data: dict) -> bool:
        """接收 LLM 返回的一个或多个工作流：空 → 错误完成；非空 → 每项按 role 创建子 flow，等待全部完成后汇总。"""
        workflows = data.get("workflows") if isinstance(data, dict) else None
        if workflows is None and isinstance(data, str):
            workflows = [workflows] if workflows.strip() else []
        elif not isinstance(workflows, list):
            workflows = []
        if not workflows:
            logger.warning("[%s][d=%s] 返回空工作流，以错误完成闭环", self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.delegate.ident if self.delegate is not None else self.ident, AE_ANSWER: "未返回可执行工作流"},
                AEFlowCompletEvent.error,
            )
            return True
        if self.delegate is None:
            logger.warning("[%s][d=%s] delegate 未设置，以错误完成", self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.ident, AE_ANSWER: "delegate 未设置"},
                AEFlowCompletEvent.error,
            )
            return True
        created = self._create_role_flows(workflows, is_subflow=True)
        if created == 0:
            logger.warning("[%s][d=%s] 全部工作流 role 非法被跳过，以错误完成闭环", self.title, self.deepth)
            self.flow_receive_complete(
                {AE_IDENT: self.ident, AE_ANSWER: "全部工作流 role 非法被跳过"},
                AEFlowCompletEvent.error,
            )
            return True
        logger.info("[%s][d=%s] 创建 %d 个子 flow，等待完成后汇总", self.title, self.deepth, created)
        return True
