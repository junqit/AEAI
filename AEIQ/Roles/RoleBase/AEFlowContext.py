"""AEFlowContext - 步骤结论上下文。

只保存每个步骤的结论（AEStepResult：action + target + result），供 LLM 决策
与 subflow / 当前 flow 请求时作为背景信息。输出时把每步的 action + target + result 合并返回。
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class AEStepResult:
    """单步结果：action + target + result。

    Attributes:
        action: 该步的 action 名（如 clarify_role / optimize_goal / gather_context 等）。
        target: 该步的目标（goal or content），即该步要处理的问题或目标。
        result: 该步的结论 / 产出（如角色信息、优化目标、背景数据、脚本结果、综合候选、验证结论等）。
    """
    action: str = ""
    target: str = ""
    result: str = ""

    # 合并 action + target + result 返回（供 to_prompt 拼接）
    def to_prompt(self) -> str:
        parts = [f"[{self.action}]"]
        if self.target:
            parts.append(f"目标：{self.target}")
        if self.result:
            parts.append(f"结果：{self.result}")
        return "\n".join(parts)


@dataclass
class AEFlowContext:
    """步骤结论上下文：保存每个步骤的结论，供 LLM 决策与请求时作为背景信息。"""

    steps: List[AEStepResult] = field(default_factory=list)

    # ==================== 状态查询 ====================

    def has_steps(self) -> bool:
        """是否已有步骤结论。"""
        return bool(self.steps)

    # ==================== 写入方法 ====================

    def record_step(self, action: str, target: str = "", result: str = "") -> None:
        """记录一个步骤的结论（action + target + result）。"""
        self.steps.append(AEStepResult(action=action, target=target, result=result))

    # ==================== 序列化（供 LLM 决策 / 请求时作为背景信息） ====================

    def to_prompt(self) -> str:
        """输出所有步骤结论（每步 action + target + result 合并）作为背景信息。"""
        if not self.steps:
            return ""
        return "\n\n".join(s.to_prompt() for s in self.steps)
