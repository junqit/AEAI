"""AERoleVerify - 验证能力 mixin（收敛链 verify 阶段，汇总前闸门）。

子任务完成后、汇总前，验证子任务结果是否齐备/有效/覆盖原目标，结论写入 flow_context（中间流程结论）。
作为 mixin 混入 AERoleBase，回包 receive_verify 落在宿主实例上。
未通过由 Orchestrator 覆写 receive_verify 记 error 驱动补缺口；通过后由 synthesize 汇总。
"""
import logging

from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Tools.Excutor.AERuntimeExcutor import AEFunctional
from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
from Roles.RoleBase.AERole import AERole

logger = logging.getLogger(__name__)


class AERoleVerifyFunction(AEFunctional):
    """验证回包功能性方法名。"""
    receive_verify = "receive_verify"


class AERoleVerify(AERole):
    """验证能力 mixin：子任务完成后验证其齐备/有效/覆盖原目标，产出 PASS/FAIL + 缺口（中间结论，写入 flow_context）。"""

    # verify 动作（汇总前闸门）：校验后请求验证（无子任务结果则回退决策）
    def do_verify(self) -> None:
        if not self.flow_context.has_sub_task_results():
            logger.info("[%s][d=%s] verify 无子任务结果，回退决策（建议先 decompose）",
                        self.title, self.deepth)
            self.flow_context.add_error("verify 无子任务结果，需先 decompose")
            self._orchestrate()
            return
        self.requestVerify()

    # 验证子任务完成/有效/覆盖原目标，请求 LLM 产出 PASS/FAIL + 缺口（汇总前闸门）
    def requestVerify(self) -> None:
        sub_tasks = self.flow_context.sub_task_results
        messages = []
        role_brief = self.role_brief()
        if role_brief:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: (
                "任务完成验证规则（汇总前闸门）：\n"
                "- 每个子任务是否都已完成、结果非空（无失败/空结果）？\n"
                "- 子任务目标合起来是否完整覆盖原始目标（有无遗漏的子问题）？\n"
                "- 有无错误信息需先补做？\n"
                "- 输出 PASS 或 FAIL；FAIL 时列出具体缺口（哪个子任务失败/缺失）与补缺方案。"
            ),
        })
        sub_text = "\n".join(f"- 目标：{t.get('goal', '')}\n  结论：{t.get('result', '')}"
                             for t in sub_tasks) if sub_tasks else "（无）"
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                f"原始问题：{self.input.get_content() if self.input is not None else ''}\n"
                f"优化目标：{self.input.get_goal() if self.input is not None else ''}\n"
                f"子任务结果：\n{sub_text}\n"
                f"错误信息：{'; '.join(self.flow_context.errors) if self.flow_context.errors else '无'}\n\n"
                f"请验证子任务是否完成且覆盖原目标，输出 PASS/FAIL 与缺口。"
            ),
        })
        flow_out = self.generateFlowOutput(AERoleVerifyFunction.receive_verify)
        flow_out.set_llm_out({
            "passed": llm_generate("验证是否通过：PASS 或 FAIL"),
            "gaps": llm_generate("若 FAIL，列出缺口与补缺方案；若 PASS 留空"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema, temperature=0.2)
        self.flow_send_llm_request(payload)

    # 接收验证结论，写入 flow_context（passed/verification）；返回是否通过
    def receive_verify(self, data: dict) -> bool:
        passed_str = ""
        gaps = ""
        if isinstance(data, dict):
            passed_str = str(data.get("passed", "") or "").strip().upper()
            gaps = str(data.get("gaps", "") or "").strip()
        passed = passed_str.startswith("PASS")
        self.flow_context.set_verification(gaps, passed)
        return passed
