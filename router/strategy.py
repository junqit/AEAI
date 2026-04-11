"""
执行策略定义
定义 Router 可以返回的执行策略类型
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any


class StrategyType(Enum):
    """策略类型枚举"""
    MCP = "mcp"           # 使用 MCP 工具执行
    RAG = "rag"           # 使用 RAG 检索知识
    LLM = "llm"           # 直接使用 LLM 生成
    HYBRID = "hybrid"     # 混合策略（RAG + MCP / RAG + LLM 等）


@dataclass
class ExecutionStrategy:
    """
    执行策略
    描述任务应该如何执行
    """
    type: StrategyType                          # 策略类型
    confidence: float                           # 置信度 (0-1)
    reason: str                                 # 选择原因
    params: Dict[str, Any] = None              # 额外参数

    def __post_init__(self):
        if self.params is None:
            self.params = {}

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "type": self.type.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "params": self.params
        }


@dataclass
class HybridStrategy(ExecutionStrategy):
    """
    混合策略
    组合多种执行方式
    """
    steps: list = None  # 执行步骤

    def __post_init__(self):
        super().__post_init__()
        if self.steps is None:
            self.steps = []

    def add_step(self, step_type: StrategyType, description: str):
        """添加执行步骤"""
        self.steps.append({
            "type": step_type.value,
            "description": description
        })

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        base = super().to_dict()
        base["steps"] = self.steps
        return base


# 策略工厂方法
def create_mcp_strategy(confidence: float = 1.0, reason: str = "需要工具执行",
                       tool_hint: Optional[str] = None) -> ExecutionStrategy:
    """创建 MCP 策略"""
    params = {}
    if tool_hint:
        params["tool_hint"] = tool_hint

    return ExecutionStrategy(
        type=StrategyType.MCP,
        confidence=confidence,
        reason=reason,
        params=params
    )


def create_rag_strategy(confidence: float = 1.0, reason: str = "需要知识检索",
                       top_k: int = 5, threshold: float = 0.7) -> ExecutionStrategy:
    """创建 RAG 策略"""
    return ExecutionStrategy(
        type=StrategyType.RAG,
        confidence=confidence,
        reason=reason,
        params={
            "top_k": top_k,
            "threshold": threshold
        }
    )


def create_llm_strategy(confidence: float = 1.0, reason: str = "直接生成回答") -> ExecutionStrategy:
    """创建 LLM 策略"""
    return ExecutionStrategy(
        type=StrategyType.LLM,
        confidence=confidence,
        reason=reason
    )


def create_hybrid_strategy(confidence: float = 1.0, reason: str = "需要混合策略",
                          steps: Optional[list] = None) -> HybridStrategy:
    """创建混合策略"""
    strategy = HybridStrategy(
        type=StrategyType.HYBRID,
        confidence=confidence,
        reason=reason,
        steps=steps or []
    )
    return strategy
