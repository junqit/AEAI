"""
动态路由器
根据任务内容动态选择执行策略
"""

import re
from typing import Optional, List, Tuple
import sys
import os

# 添加父目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from router.strategy import (
    ExecutionStrategy,
    StrategyType,
    create_mcp_strategy,
    create_rag_strategy,
    create_llm_strategy,
    create_hybrid_strategy
)

from utils.logger import get_logger


class Router:
    """
    多级路由器
    按优先级：规则路由 → 向量路由 → LLM 路由
    """

    def __init__(self, enable_vector: bool = False, enable_llm_fallback: bool = True):
        """
        初始化路由器

        Args:
            enable_vector: 是否启用向量路由（需要嵌入模型）
            enable_llm_fallback: 是否启用 LLM 兜底路由
        """
        self.enable_vector = enable_vector
        self.enable_llm_fallback = enable_llm_fallback
        self.logger = get_logger("Router")

        self.logger.info("🔧 初始化 Router",
                        enable_vector=enable_vector,
                        enable_llm_fallback=enable_llm_fallback)

        # 规则模式定义
        self._init_rules()
        self.logger.debug("规则初始化完成")

    def _init_rules(self):
        """初始化路由规则"""
        self.logger.start("_init_rules-初始化路由规则")

        self.logger.step("步骤1", "定义计算类规则")
        # 计算类规则
        self.calc_patterns = [
            r'\d+\s*[\+\-\*\/]\s*\d+',  # 基本四则运算
            r'计算',
            r'求和',
            r'相加',
            r'相减',
            r'相乘',
            r'相除'
        ]

        self.logger.step("步骤2", "定义时间类规则")
        # 时间类规则
        self.time_patterns = [
            r'时间',
            r'现在几点',
            r'当前时间',
            r'日期'
        ]

        self.logger.step("步骤3", "定义知识问答类规则")
        # 知识问答类规则
        self.qa_patterns = [
            r'是什么',
            r'什么是',
            r'介绍',
            r'解释',
            r'说明',
            r'定义'
        ]

        self.logger.step("步骤4", "定义文件操作类规则")
        # 文件操作类规则
        self.file_patterns = [
            r'写入文件',
            r'保存到',
            r'创建文件',
            r'读取文件',
            r'删除文件'
        ]

        self.logger.end("_init_rules-初始化路由规则", success=True)

    def route(self, query: str, context: Optional[dict] = None) -> ExecutionStrategy:
        """
        主路由方法

        Args:
            query: 用户查询
            context: 上下文信息（可选）

        Returns:
            ExecutionStrategy: 执行策略
        """
        self.logger.start("路由决策", query=query[:50])

        # 1. 规则路由（最高优先级，确定性强）
        self.logger.debug("尝试规则路由")
        strategy = self._rule_route(query)
        if strategy:
            self.logger.end("路由决策", success=True,
                          method="规则路由",
                          strategy=strategy.type.value,
                          confidence=strategy.confidence)
            return strategy

        # 2. 向量路由（中等优先级，基于语义）
        if self.enable_vector:
            self.logger.debug("尝试向量路由")
            strategy = self._vector_route(query)
            if strategy and strategy.confidence > 0.8:
                self.logger.end("路由决策", success=True,
                              method="向量路由",
                              strategy=strategy.type.value,
                              confidence=strategy.confidence)
                return strategy

        # 3. LLM 兜底路由（最低优先级，灵活但慢）
        if self.enable_llm_fallback:
            self.logger.debug("使用 LLM 兜底路由")
            strategy = self._llm_route(query)
            self.logger.end("路由决策", success=True,
                          method="LLM兜底",
                          strategy=strategy.type.value,
                          confidence=strategy.confidence)
            return strategy

        # 默认使用 LLM 直接生成
        self.logger.warning("未找到明确路由，使用默认策略")
        strategy = create_llm_strategy(
            confidence=0.5,
            reason="未匹配到明确规则，使用 LLM 直接回答"
        )
        self.logger.end("路由决策", success=True,
                      method="默认",
                      strategy=strategy.type.value)
        return strategy

    def _rule_route(self, query: str) -> Optional[ExecutionStrategy]:
        """
        规则路由
        基于预定义规则快速判断

        Args:
            query: 用户查询

        Returns:
            ExecutionStrategy or None
        """
        self.logger.start("_rule_route-规则路由", query=query[:50])
        self.logger.step("步骤1", "转换查询为小写")
        query_lower = query.lower()

        self.logger.step("步骤2", "检查计算类规则")
        # 检查计算类
        for pattern in self.calc_patterns:
            if re.search(pattern, query):
                self.logger.info("匹配到计算规则", pattern=pattern)
                self.logger.end("_rule_route-规则路由", success=True, strategy="MCP")
                return create_mcp_strategy(
                    confidence=1.0,
                    reason="匹配到计算规则",
                    tool_hint="add"  # 提示可能用到的工具
                )

        self.logger.step("步骤3", "检查时间类规则")
        # 检查时间类
        for pattern in self.time_patterns:
            if re.search(pattern, query):
                self.logger.info("匹配到时间规则", pattern=pattern)
                self.logger.end("_rule_route-规则路由", success=True, strategy="MCP")
                return create_mcp_strategy(
                    confidence=1.0,
                    reason="匹配到时间查询规则",
                    tool_hint="get_time"
                )

        self.logger.step("步骤4", "检查文件操作类规则")
        # 检查文件操作类
        for pattern in self.file_patterns:
            if re.search(pattern, query):
                self.logger.info("匹配到文件操作规则", pattern=pattern)
                self.logger.end("_rule_route-规则路由", success=True, strategy="MCP")
                return create_mcp_strategy(
                    confidence=1.0,
                    reason="匹配到文件操作规则",
                    tool_hint="file_operation"
                )

        self.logger.step("步骤5", "检查知识问答类规则")
        # 检查知识问答类
        for pattern in self.qa_patterns:
            if re.search(pattern, query):
                self.logger.info("匹配到知识问答规则", pattern=pattern)
                self.logger.end("_rule_route-规则路由", success=True, strategy="RAG")
                return create_rag_strategy(
                    confidence=0.9,
                    reason="匹配到知识问答规则",
                    top_k=5,
                    threshold=0.7
                )

        self.logger.step("步骤6", "检查混合类任务")
        # 检查混合类（需要多步执行）
        if self._is_hybrid_task(query):
            self.logger.info("识别为混合任务")
            result = self._create_hybrid_strategy_for_query(query)
            self.logger.end("_rule_route-规则路由", success=True, strategy="HYBRID")
            return result

        self.logger.info("未匹配到任何规则")
        self.logger.end("_rule_route-规则路由", success=False)
        return None

    def _is_hybrid_task(self, query: str) -> bool:
        """判断是否为混合任务"""
        self.logger.start("_is_hybrid_task-判断混合任务", query=query[:50])

        self.logger.step("步骤1", "检查问答模式")
        # 同时包含问答和计算
        has_qa = any(re.search(p, query) for p in self.qa_patterns)
        self.logger.debug("问答检查结果", has_qa=has_qa)

        self.logger.step("步骤2", "检查计算模式")
        has_calc = any(re.search(p, query) for p in self.calc_patterns)
        self.logger.debug("计算检查结果", has_calc=has_calc)

        self.logger.step("步骤3", "检查上下文关键词")
        # 包含 "根据" "基于" 等关键词
        has_context_keyword = any(kw in query for kw in ['根据', '基于', '参考', '结合'])
        self.logger.debug("上下文关键词检查结果", has_context_keyword=has_context_keyword)

        self.logger.step("步骤4", "综合判断")
        result = (has_qa and has_calc) or has_context_keyword

        self.logger.end("_is_hybrid_task-判断混合任务", success=True, is_hybrid=result)
        return result

    def _create_hybrid_strategy_for_query(self, query: str) -> ExecutionStrategy:
        """为查询创建混合策略"""
        self.logger.start("_create_hybrid_strategy_for_query-创建混合策略", query=query[:50])

        self.logger.step("步骤1", "创建基础混合策略")
        strategy = create_hybrid_strategy(
            confidence=0.95,
            reason="任务需要多步执行"
        )

        self.logger.step("步骤2", "分析是否需要知识检索")
        # 分析需要哪些步骤
        if any(re.search(p, query) for p in self.qa_patterns):
            self.logger.debug("添加 RAG 步骤")
            strategy.add_step(StrategyType.RAG, "检索相关知识")

        self.logger.step("步骤3", "分析是否需要计算")
        if any(re.search(p, query) for p in self.calc_patterns):
            self.logger.debug("添加 MCP 步骤")
            strategy.add_step(StrategyType.MCP, "执行计算")

        self.logger.step("步骤4", "添加结果整合步骤")
        strategy.add_step(StrategyType.LLM, "整合结果生成回答")

        self.logger.end("_create_hybrid_strategy_for_query-创建混合策略", success=True, steps_count=len(strategy.steps))
        return strategy

    def _vector_route(self, query: str) -> Optional[ExecutionStrategy]:
        """
        向量路由
        基于语义相似度匹配

        Args:
            query: 用户查询

        Returns:
            ExecutionStrategy or None
        """
        self.logger.start("_vector_route-向量路由", query=query[:50])
        self.logger.step("步骤1", "准备向量路由（未实现）")
        # TODO: 实现向量路由
        # 1. 将 query 转换为向量
        # 2. 与预定义的策略模板向量进行匹配
        # 3. 返回相似度最高的策略

        self.logger.warning("向量路由尚未实现")
        # 暂时返回 None
        self.logger.end("_vector_route-向量路由", success=False)
        return None

    def _llm_route(self, query: str) -> ExecutionStrategy:
        """
        LLM 路由
        使用 LLM 判断应该使用哪种策略

        Args:
            query: 用户查询

        Returns:
            ExecutionStrategy
        """
        self.logger.start("_llm_route-LLM路由", query=query[:50])
        self.logger.step("步骤1", "准备 LLM 路由（未完全实现）")
        # TODO: 调用 LLM 进行判断
        # 这里可以使用轻量级模型（如 Haiku）快速判断

        self.logger.step("步骤2", "返回默认 LLM 策略")
        # 暂时返回默认策略
        strategy = create_llm_strategy(
            confidence=0.7,
            reason="LLM 兜底路由"
        )

        self.logger.end("_llm_route-LLM路由", success=True)
        return strategy

    def explain_route(self, query: str) -> str:
        """
        解释路由决策
        用于调试和理解

        Args:
            query: 用户查询

        Returns:
            解释文本
        """
        self.logger.start("explain_route-解释路由决策", query=query[:50])

        self.logger.step("步骤1", "执行路由决策")
        strategy = self.route(query)

        self.logger.step("步骤2", "构建基础解释文本")
        explanation = f"""
路由决策分析：
━━━━━━━━━━━━━━━━━━━━━━
查询：{query}

策略类型：{strategy.type.value}
置信度：{strategy.confidence:.2f}
选择原因：{strategy.reason}
"""

        self.logger.step("步骤3", "添加混合策略步骤（如有）")
        if strategy.type == StrategyType.HYBRID:
            explanation += "\n执行步骤：\n"
            for i, step in enumerate(strategy.steps, 1):
                explanation += f"  {i}. {step['type']}: {step['description']}\n"

        self.logger.step("步骤4", "添加策略参数（如有）")
        if strategy.params:
            explanation += f"\n参数：{strategy.params}\n"

        self.logger.end("explain_route-解释路由决策", success=True)
        return explanation


# 便捷函数
def route(query: str, enable_vector: bool = False, enable_llm_fallback: bool = True) -> str:
    """
    便捷路由函数
    用于向后兼容旧代码

    Args:
        query: 用户查询
        enable_vector: 是否启用向量路由
        enable_llm_fallback: 是否启用 LLM 兜底

    Returns:
        策略类型字符串
    """
    logger = get_logger("RouteFunction")
    logger.start("route-便捷路由函数", query=query[:50])

    logger.step("步骤1", "创建 Router 实例", enable_vector=enable_vector, enable_llm_fallback=enable_llm_fallback)
    router = Router(enable_vector=enable_vector, enable_llm_fallback=enable_llm_fallback)

    logger.step("步骤2", "执行路由决策")
    strategy = router.route(query)

    logger.step("步骤3", "返回策略类型", strategy_type=strategy.type.value)
    logger.end("route-便捷路由函数", success=True)
    return strategy.type.value


# 测试代码
if __name__ == "__main__":
    router = Router()

    test_queries = [
        "123 + 456 等于多少？",
        "现在几点了？",
        "什么是 MCP 协议？",
        "根据文档计算总成本",
        "帮我写代码",
    ]

    print("路由测试\n" + "=" * 50)
    for query in test_queries:
        print(router.explain_route(query))
        print()
