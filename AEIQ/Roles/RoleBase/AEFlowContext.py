"""
AEFlowContext - Orchestrator 决策辅助上下文。

只存 flow 自身没有的中间流程结论：背景信息、综合候选答案、验证结论、历史动作记录、错误信息。
question / title / responsibility / goal / sub_results 等直接从 flow 自身读取，不在此重复存储。
最终结果不在此存放——由 complete 写入 flow.output；问题的持有或优化在 flow.input。
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class AEFlowContext:
    """Orchestrator 决策辅助上下文（只存 flow 没有的中间流程结论）。"""

    # 背景信息（gather_context 后填充，flow 自身无此字段）
    background: str = ""
    # 子任务结果（每个子 flow 完成时记录：ident + 目标 + 结论配对，中间结论）
    sub_task_results: List[Dict[str, str]] = field(default_factory=list)
    # 综合候选答案（synthesize 后填充，中间结论；verify 通过后由 complete 搬到 output）
    synthesis: str = ""
    # 验证结论（verify 后填充：缺口描述，中间结论）
    verification: str = ""
    # 验证是否通过（verify 后填充）
    verified: bool = False
    # 历史动作记录（每轮决策 + 执行结果）
    action_history: List[Dict[str, Any]] = field(default_factory=list)
    # 错误信息
    errors: List[str] = field(default_factory=list)

    # ==================== 状态查询 ====================

    def has_background(self) -> bool:
        """是否已有背景信息。"""
        return bool(self.background)

    def has_sub_task_results(self) -> bool:
        """是否已有子任务结果记录。"""
        return bool(self.sub_task_results)

    def has_synthesis(self) -> bool:
        """是否已有综合候选答案。"""
        return bool(self.synthesis)

    def has_verification(self) -> bool:
        """是否已执行验证。"""
        return self.verified or bool(self.verification)

    def is_verified(self) -> bool:
        """验证是否通过。"""
        return self.verified

    # ==================== 写入方法 ====================

    def set_background(self, background: str) -> None:
        """写入背景信息。"""
        self.background = background

    def record_sub_task(self, ident: str, goal: str, result: str) -> None:
        """记录一个子 flow 的目标与结论（子 flow 完成时调用，按 ident 去重：已存在则更新）。"""
        for t in self.sub_task_results:
            if t.get("ident") == ident:
                t["goal"] = goal or ""
                t["result"] = result or ""
                return
        self.sub_task_results.append({"ident": ident, "goal": goal or "", "result": result or ""})

    def set_synthesis(self, synthesis: str) -> None:
        """写入综合候选答案（中间结论）。"""
        self.synthesis = synthesis or ""

    def set_verification(self, gaps: str, passed: bool) -> None:
        """写入验证结论（中间结论）。"""
        self.verification = gaps or ""
        self.verified = bool(passed)

    def add_error(self, error: str) -> None:
        """追加错误信息。"""
        if error:
            self.errors.append(error)

    def record_action(self, action: str, detail: str = "", result: Any = None) -> None:
        """记录一轮步骤、要做的事情与结果。"""
        self.action_history.append({
            "action": action,
            "detail": detail,
            "result": result,
        })

    # ==================== 序列化（供 LLM 决策时阅读） ====================

    def to_prompt(self, question: str = "", title: str = "", responsibility: str = "",
                  goal: str = "") -> str:
        """序列化为 LLM 可读的上下文文本。flow 字段由调用方传入，自身只补独有中间结论。"""
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
        if self.sub_task_results:
            results_text = "\n".join(
                f"- 目标：{t.get('goal', '')}\n  结论：{t.get('result', '')}"
                for t in self.sub_task_results
            )
            parts.append(f"【子任务结果】\n{results_text}")
        if self.synthesis:
            parts.append(f"【综合候选】\n{self.synthesis}")
        if self.has_verification():
            verdict = "通过" if self.verified else "未通过"
            if self.verification:
                verdict += f"：{self.verification}"
            parts.append(f"【验证结论】\n{verdict}")
        if self.errors:
            errors_text = "\n".join(f"- {e}" for e in self.errors)
            parts.append(f"【错误信息】\n{errors_text}")
        if self.action_history:
            history_text = "\n".join(
                f"- {h['action']}"
                for h in self.action_history
            )
            parts.append(f"【历史动作】\n{history_text}")
        return "\n\n".join(parts) if parts else "（暂无上下文信息）"
