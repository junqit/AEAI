"""
AEWorkFlow - 管理多个 Flow 的有序执行
"""
import logging
from typing import List, Dict, Any, Optional

from .AEFlow import AEFlow

logger = logging.getLogger(__name__)


class AEWorkFlow:
    """
    WorkFlow 管理器，按顺序执行多个 Flow。
    每个 Flow 的结果作为后续 Flow 的上下文。
    """

    def __init__(self, flows: List[AEFlow]):
        self._flows: List[AEFlow] = flows
        self._current_index: int = 0
        self._context: Dict[str, Any] = {}
        self._results: Dict[str, Any] = {}

    @property
    def is_completed(self) -> bool:
        return self._current_index >= len(self._flows)

    @property
    def current_flow(self) -> Optional[AEFlow]:
        if self._current_index < len(self._flows):
            return self._flows[self._current_index]
        return None

    def get_current_prompt(self) -> Optional[str]:
        """获取当前 Flow 的完整 prompt"""
        flow = self.current_flow
        if not flow:
            return None
        return flow.build_full_prompt(self._context)

    def receive_response(self, llm_output: str) -> Optional[str]:
        """
        接收 LLM 返回结果，解析后推进到下一个 Flow。

        Args:
            llm_output: LLM 原始输出

        Returns:
            下一个 Flow 的 prompt，全部完成返回 None
        """
        flow = self.current_flow
        if not flow:
            return None

        parsed = flow.parse_response(llm_output)
        if parsed is None:
            logger.warning(f"Flow [{flow.name}] 解析失败: {llm_output[:100]}")
            return None

        self._results[flow.name] = parsed
        self._context[flow.name] = parsed

        self._current_index += 1
        return self.get_current_prompt()

    def get_results(self) -> Dict[str, Any]:
        """获取所有已完成 Flow 的结果"""
        return self._results

    def get_status(self) -> dict:
        return {
            "total": len(self._flows),
            "current_index": self._current_index,
            "current_flow": self.current_flow.name if self.current_flow else None,
            "is_completed": self.is_completed,
            "completed_flows": list(self._results.keys()),
        }
