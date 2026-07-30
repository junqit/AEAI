"""
AERoleChoice - 角色选择能力 mixin。

提供 requestRoleSelect / receiveRoleSelect / _dispatch_role_executor / _request_direct_answer，
由 AERole 继承获得"按问题选择角色并派发"的能力：选人员角色则派发 AERoleExcutor，选 llm 则派发 AELLMRole。
"""
import logging

from WorkFlows.AEFlow import AEFlowCompletEvent
from WorkFlows.AEFlowOutput import AEFlowOutput
from WorkFlows.AEFlowInfo import AE_IDENT, AE_ANSWER
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.AERoleType import (
    AEFlowRole, ROLE_PARAMS, roles_below,
    AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT,
)

logger = logging.getLogger(__name__)


class AERoleFunction(AEFunctional):
    """AERole 角色选择回包功能性方法名（继承 AEFunctional 基类）。"""
    receiveRoleSelect = "receiveRoleSelect"  # 接收 LLM 选定的角色，传入 map


class AERoleChoice:
    """角色选择能力 mixin：按问题选择角色并派发（AERoleExcutor 或 AELLMRole）。"""

    def requestRoleSelect(self) -> None:
        """请求 LLM 选择解决当前问题/目标所需的角色，子类可直接调用。

        - 当前未配置 role（self.role 为 None）：从全部角色（expert/workgroup/employee/task + llm 直答）中选；
        - 已配置 role：仅从其二级角色（roles_below(self.role)）中选，不得选 llm。
        选择须确保能切实解决用户的问题或目标，不得给出无法解决或拒绝的答案。
        """
        cur_role = self.role
        if cur_role is None:
            candidates = list(ROLE_PARAMS.keys())  # 全部角色（含 llm 直答）
        else:
            candidates = roles_below(cur_role)  # 仅二级角色（不含 llm）
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        question = self.optimizePromptResult or (self.input.content if self.input is not None else "")
        if len(question) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: f"{AE_USER_QUESTION_PREFIX}{question}"})
        # 角色选择规则（system）：必须解决问题 + 网络请求类必选角色 + 复杂度分级
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: (
                "角色选择规则：\n"
                "- 所选角色必须能够切实解决用户的问题或目标，不得给出无法解决或拒绝的答案；\n"
                "- 若问题需要获取网络数据、实时数据、资讯等需通过网络请求的内容，必须选择角色（不得选 llm）；\n"
                "- 复杂/需规划或多步骤的问题选高层级角色；仅需脚本或单步执行选 task/employee；简单知识问题选 llm。"
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
                f"请根据{AE_USER_QUESTION_PREFIX}的内容与复杂度，选择最适合解决此问题的角色，"
                f"将选择结果填入 role 字段（填角色 type，如 {' / '.join(allowed)}）。"
            ),
        })
        flow_out = self.flowOutput(AERoleFunction.receiveRoleSelect)
        flow_out.set_llm_out({"role": llm_generate(" / ".join(allowed) + " 之一")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveRoleSelect(self, data: dict) -> bool:
        """接收 LLM 选定的角色：llm 或非法或越界 → 直接作答；合法人员角色 → 按该角色派发 AERoleExcutor。"""
        cur_role = self.role
        allow_llm = cur_role is None
        allowed_roles = list(ROLE_PARAMS.keys()) if allow_llm else roles_below(cur_role)
        role_str = data.get("role") if isinstance(data, dict) else None
        if role_str is None and isinstance(data, str):
            role_str = data
        role_str = (role_str or "").strip().lower()
        if role_str == "llm":
            if not allow_llm:
                logger.warning("[%s][%s][d=%s] llm 不在可选范围，回退直接作答", type(self).__name__, self.title, self.deepth)
            else:
                logger.info("[%s][%s][d=%s] 选择 llm 直接作答", type(self).__name__, self.title, self.deepth)
            self._request_direct_answer()
            return True
        try:
            role_enum = AEFlowRole(role_str)
        except ValueError:
            logger.warning("[%s][%s][d=%s] 非法 role=%r，回退直接作答", type(self).__name__, self.title, self.deepth, role_str)
            self._request_direct_answer()
            return True
        if role_enum not in allowed_roles:
            logger.warning("[%s][%s][d=%s] role %s 不在可选范围 %s，回退直接作答",
                           type(self).__name__, self.title, self.deepth, role_enum.value, [r.value for r in allowed_roles])
            self._request_direct_answer()
            return True
        logger.info("[%s][%s][d=%s] 选择角色 %s，派发 AERoleExcutor", type(self).__name__, self.title, self.deepth, role_enum.value)
        self._dispatch_role_executor(role_enum)
        return True

    def _dispatch_role_executor(self, role: AEFlowRole) -> None:
        """创建 AERoleExcutor（指定 role），经 delegate 添加并以 startFlow 事件启动，
        由 delegate 据事件 startFlow 该执行 flow（input 取优化后的问题/目标）。"""
        from Roles.AERoleExcutor import AERoleExcutor  # 懒导入避免循环
        if self.delegate is None:
            logger.warning("[%s][%s][d=%s] delegate 未设置，无法添加 AERoleExcutor", type(self).__name__, self.title, self.deepth)
            return
        delegate_ident = self.delegate.ident
        excutor = AERoleExcutor(
            flowOutput=AEFlowOutput({AE_IDENT: delegate_ident, AE_ANSWER: llm_generate("任务结论")}),
        )
        excutor.role = role
        self.delegate.receive_add_flow(excutor)
        # 完成自身：以 startFlow 事件向上通知，delegate 据此 startFlow 该 AERoleExcutor
        self.flow_receive_complete(
            {AE_IDENT: excutor.ident, AE_ANSWER: self.optimizePromptResult},
            AEFlowCompletEvent.startFlow,
        )

    def _request_direct_answer(self) -> None:
        """无需角色人员：创建 AELLMRole 子 flow 经 delegate 添加并以 startFlow 事件启动，
        由 delegate 据事件 startFlow 该 AELLMRole（input 取优化后的问题），LLM 回包即完成该子 flow。"""
        from Roles.LLM.AELLMRole import AELLMRole  # 懒导入避免循环
        if self.delegate is None:
            logger.warning("[%s][%s][d=%s] delegate 未设置，无法添加 AELLMRole", type(self).__name__, self.title, self.deepth)
            return
        delegate_ident = self.delegate.ident
        llm_role = AELLMRole(
            flowOutput=AEFlowOutput({AE_IDENT: delegate_ident, AE_ANSWER: llm_generate("llm回答")}),
        )
        self.delegate.receive_add_flow(llm_role)
        self.flow_receive_complete(
            {AE_IDENT: llm_role.ident, AE_ANSWER: self.optimizePromptResult},
            AEFlowCompletEvent.startFlow,
        )
