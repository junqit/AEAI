"""
AERoleExcuteContext - 问题解决前的背景信息与必要参数准备 mixin。

在角色选择后、执行/拆解前，请求 LLM 识别并准备解决当前问题所需的背景信息与必要参数，
确保 executor 解决问题时信息与参数完整。若存在缺失信息（missing），创建子 flow 逐个解决，
全部解决后汇总并推进到执行/拆解。必要信息与参数存于 self.input（context），供执行步骤使用。
"""
import logging

from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT, AE_IDENT
from WorkFlows.FlowWork.AEFlowOutput import AEFlowOutput
from WorkFlows.FlowWork.AEFlowInput import AEFlowInput
from Tools.Excutor.AERuntimeExcutor import AEFunctional

logger = logging.getLogger(__name__)


class AERoleExcuteContextFunction(AEFunctional):
    """背景信息准备回包功能性方法名。"""
    receiveContext = "receiveContext"


class AERoleExcuteContext:
    """问题解决前的背景信息与必要参数准备 mixin：确保 executor 解决问题时信息与参数完整。

    若 LLM 返回 missing（缺失信息），创建子 AERoleExcutor 逐个解决（串行），全部完成后
    汇总结果并推进到执行/拆解（_proceed_after_context）；无缺失则直接推进。
    """

    def requestContext(self) -> None:
        """请求 LLM 识别并准备解决当前问题所需的背景信息与必要参数。

        根据当前目标（goal）与角色能力（role_brief），让 LLM 分析解决该问题需要哪些
        背景信息与必要参数，并尽可能从已知上下文中补全。回包经 receiveContext 处理。
        无目标时跳过 LLM 请求，直接推进。
        """
        goal = (self.input.get_goal() or self.input.get_content()) if self.input is not None else ""
        if not goal:
            logger.warning("[%s][d=%s] 无目标，跳过背景信息准备", self.title, self.deepth)
            self._proceed_after_context()
            return
        messages = []
        role_brief = self.role_brief()
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: goal})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "请分析解决上述目标需要哪些必要参数，并尽可能从已知上下文中补全：\n"
                "- 识别解决问题所需的关键参数（如：时间、地点、数据来源、格式要求等）\n"
                "- 从当前目标与上下文中提取已知的参数值\n"
                "- 标注缺失的信息（如有）\n"
                "输出 JSON，含 params（必要参数，key-value）、missing（缺失信息列表）。"
            ),
        })
        flow_out = self.generateFlowOutput(AERoleExcuteContextFunction.receiveContext)
        flow_out.set_llm_out({
            "params": {llm_generate("参数名"): llm_generate("参数值")},
            "missing": [llm_generate("缺失的信息")],
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.flow_send_llm_request(payload)

    def receiveContext(self, data: dict) -> bool:
        """接收准备好的必要信息与参数，存入 self.input（context）。

        仅存储必要参数（params，key-value），不含 background 等问题相关信息。
        若有缺失信息（missing），创建子 flow 逐个解决后再推进；无缺失则直接推进到执行/拆解。
        """
        if isinstance(data, dict):
            params = data.get("params", {})
            missing = data.get("missing", [])
        else:
            params = {}
            missing = []
        # 仅存储必要信息与参数（不含 background 等问题相关信息），逐个 add_context
        if self.input is not None and isinstance(params, dict):
            for key, value in params.items():
                self.input.add_context(key, value)
        logger.info("[%s][d=%s] 必要信息与参数准备完成: params=%s, missing=%s",
                    self.title, self.deepth, params, missing)
        if missing:
            self._resolving_missing = True
            self._dispatch_missing(missing)
        else:
            self._proceed_after_context()
        return True

    def _dispatch_missing(self, missing: list) -> None:
        """为每个缺失信息创建子 AERoleExcutor 解决（串行），全部完成后由 receive_summarize_result 汇总推进。"""
        from Roles.AERoleExcutor import AERoleExcutor  # 懒导入避免循环
        first_child = None
        for item in missing:
            goal = str(item or "").strip()
            if not goal:
                continue
            child = AERoleExcutor(
                flowOutput=AEFlowOutput(ident=self.ident, out_schema={AE_CONTENT: llm_generate("解决结果")}),
            )
            self.add_flow(child)
            child.update_flow_input(AEFlowInput(content=goal, ident=child.ident, role=self.role.role if self.role is not None else None))
            if first_child is None:
                first_child = child
        if first_child is not None:
            logger.info("[%s][d=%s] 创建 %d 个子 flow 解决缺失信息（串行），首个已启动",
                        self.title, self.deepth, len(missing))
            first_child.on_flow_start()
        else:
            # 无有效缺失项，直接推进
            self._resolving_missing = False
            self._proceed_after_context()

    def receive_summarize_result(self, data: dict) -> bool:
        """覆写汇总回包：若正在解决缺失信息，将解决结果纳入 self.input（context） 后推进到执行/拆解；否则正常完成。"""
        if getattr(self, "_resolving_missing", False):
            self._resolving_missing = False
            answer = data.get(AE_CONTENT, "") if isinstance(data, dict) else str(data)
            if self.input is not None:
                self.input.add_context("resolved", answer)
            logger.info("[%s][d=%s] 缺失信息已解决，推进到执行/拆解: %s", self.title, self.deepth, answer)
            self._proceed_after_context()
            return True
        return super().receive_summarize_result(data)

    def _proceed_after_context(self) -> None:
        """背景信息准备完成后，推进到执行（叶子）或拆解（协调角色）。子类覆写以定制。"""
        pass
