"""AEFlowContext - 步骤结论上下文。

记录两部分：
1. action_results：当前 flow 各 action 的结论（clarify/optimize/gather/synthesize/verify/execute）。
2. subflow_results：子 flow 的目标与结果（子 flow 完成时记录）。

请求 LLM 时（flow_send_llm_request）添加的是 subflow_results（子 flow 目标与结果）作为背景。
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class AEStepResult:
    """单步结果：action + target + result。

    action 非空时为 action 结论；action 空时为 subflow 结果（只有 target + result）。
    """
    action: str = ""
    target: str = ""
    result: str = ""

    # 合并 action + target + result 返回（action 空则跳过）
    def to_prompt(self) -> str:
        parts = []
        if self.action:
            parts.append(f"[{self.action}]")
        if self.target:
            parts.append(f"目标：{self.target}")
        if self.result:
            parts.append(f"结果：{self.result}")
        return "\n".join(parts)


@dataclass
class AEFlowContext:
    """步骤结论上下文：记录 action 结果与 subflow 目标/结果（私有字段，经方法访问）。"""

    _action_results: List[AEStepResult] = field(default_factory=list)
    _subflow_results: List[AEStepResult] = field(default_factory=list)
    _action_catalog: Dict[str, str] = field(default_factory=dict)

    # ==================== 状态查询 ====================

    def has_subflow_results(self) -> bool:
        """是否已有子 flow 结果。"""
        return bool(self._subflow_results)

    def get_action_description(self, action: str) -> str:
        """获取单个 action 的规则与范围描述。"""
        return self._action_catalog.get(action, "")

    def get_action_count(self) -> int:
        """获取已收到的 action 个数。"""
        return len(self._action_catalog)

    # ==================== 写入方法 ====================

    def record_action_result(self, action: str, target: str = "", result: str = "") -> None:
        """记录当前 flow 一个 action 的结论。"""
        self._action_results.append(AEStepResult(action=action, target=target, result=result))

    def set_action(self, action: str, description: str) -> None:
        """添加/更新单个 action 的规则与范围描述。"""
        self._action_catalog[action] = description

    def record_subflow_result(self, flow) -> None:
        """记录一个子 flow 的目标与结果（接收 flow，按 target 去重）。"""
        target = flow.input.get_target() if flow.input else ""
        result = flow.output.outResult or "" if flow.output else ""
        for s in self._subflow_results:
            if s.target == target:
                s.result = result
                return
        self._subflow_results.append(AEStepResult(action="", target=target, result=result))

    # ==================== 序列化（请求 LLM 时添加 subflow 目标与结果） ====================

    def to_prompt(self) -> str:
        """输出 subflow 目标与结果（请求 LLM 时作为背景添加）。"""
        if not self._subflow_results:
            return ""
        return "\n\n".join(s.to_prompt() for s in self._subflow_results)
