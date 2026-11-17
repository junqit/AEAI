"""
AEFlowContext - Orchestrator 决策辅助上下文。

只存 flow 自身没有的信息：背景信息、历史动作记录、错误信息。
question / title / responsibility / goal / sub_results 等直接从 flow 自身读取，
不在此重复存储。
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class AEFlowContext:
    """Orchestrator 决策辅助上下文（只存 flow 没有的信息）。"""

    # 背景信息（gather_context 后填充，flow 自身无此字段）
    background: str = ""
    # 历史动作记录（每轮决策 + 执行结果）
    action_history: List[Dict[str, Any]] = field(default_factory=list)
    # 错误信息
    errors: List[str] = field(default_factory=list)

    # ==================== 状态查询 ====================

    def has_background(self) -> bool:
        """是否已有背景信息。"""
        return bool(self.background)

    def decision_count(self) -> int:
        """已决策轮数（用于温度递增）。"""
        return len(self.action_history)

    # ==================== 写入方法 ====================

    def set_background(self, background: str) -> None:
        """写入背景信息。"""
        self.background = background

    def add_error(self, error: str) -> None:
        """追加错误信息。"""
        if error:
            self.errors.append(error)

    def record_action(self, action: str, result: Any = None, params: Dict[str, Any] = None) -> None:
        """记录一轮动作与结果。"""
        self.action_history.append({
            "action": action,
            "params": params or {},
            "result": result,
        })

    # ==================== 序列化（供 LLM 决策时阅读） ====================

    def to_prompt(self, question: str = "", title: str = "", responsibility: str = "",
                  goal: str = "", sub_results: List[str] = None) -> str:
        """序列化为 LLM 可读的上下文文本。flow 字段由调用方传入，自身只补独有信息。"""
        parts = []
        if question:
            parts.append(f"【原始问题】\n{question}")
        if title:
            role_info = f"身份：{title}"
            if responsibility:
                role_info += f"\n能力范围：{responsibility}"
            parts.append(f"【角色信息】\n{role_info}")
        if goal:
            parts.append(f"【优化目标】\n{goal}")
        if self.background:
            parts.append(f"【背景信息】\n{self.background}")
        if sub_results:
            results_text = "\n".join(f"- {r}" for r in sub_results)
            parts.append(f"【子任务结果】\n{results_text}")
        if self.errors:
            errors_text = "\n".join(f"- {e}" for e in self.errors)
            parts.append(f"【错误信息】\n{errors_text}")
        if self.action_history:
            history_text = "\n".join(
                f"- 动作: {h['action']}, 结果: {str(h['result'])[:100]}"
                for h in self.action_history
            )
            parts.append(f"【历史动作】\n{history_text}")
        return "\n\n".join(parts) if parts else "（暂无上下文信息）"
