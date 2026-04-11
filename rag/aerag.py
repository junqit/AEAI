"""
RAG (Retrieval Augmented Generation) 模块
提供向量检索和知识库管理功能
"""

import os
import sys
from typing import List, Optional, Dict, Any

# 添加父目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from utils.logger import get_logger


class SimpleRAG:
    """
    简单的 RAG 实现
    使用内存中的文档存储和简单的关键词匹配

    后续可以升级为使用 FAISS + Sentence Transformers
    """

    def __init__(self):
        """初始化 RAG"""
        self.logger = get_logger("SimpleRAG")
        self.logger.info("🔧 初始化 SimpleRAG")

        self.logger.step("步骤1", "初始化文档存储")
        self.documents = []  # 存储文档
        self.embeddings_available = False

        # 尝试加载嵌入模型
        self.logger.step("步骤2", "尝试加载嵌入模型")
        try:
            from sentence_transformers import SentenceTransformer, util
            model_path = os.path.expanduser(
                "~/.cache/huggingface/hub/models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/snapshots/e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
            )
            if os.path.exists(model_path):
                self.logger.debug("找到模型路径", model_path=model_path)
                self.model = SentenceTransformer(model_path)
                self.util = util
                self.embeddings_available = True
                self.logger.info("✅ 嵌入模型加载成功")
            else:
                self.logger.warning("模型路径不存在", model_path=model_path)
                self.embeddings_available = False
        except ImportError:
            self.logger.warning("sentence-transformers 未安装，使用关键词匹配")
            self.embeddings_available = False
        except Exception as e:
            self.logger.error("加载嵌入模型失败", error=str(e))
            self.embeddings_available = False

        self.logger.info("RAG 初始化完成", embeddings_available=self.embeddings_available)

    def add_documents(self, docs: List[str]):
        """
        添加文档到知识库

        Args:
            docs: 文档列表
        """
        self.logger.start("add_documents-添加文档", docs_count=len(docs))

        self.logger.step("步骤1", "扩展文档列表")
        self.documents.extend(docs)

        self.logger.info(f"✅ 已添加文档", added=len(docs), total=len(self.documents))
        self.logger.end("add_documents-添加文档", success=True)

    def retrieve(self, query: str, top_k: int = 5, threshold: float = 0.5) -> List[str]:
        """
        检索相关文档

        Args:
            query: 查询字符串
            top_k: 返回的文档数量
            threshold: 相似度阈值

        Returns:
            相关文档列表
        """
        self.logger.start("retrieve-检索文档", query=query[:50], top_k=top_k)

        if not self.documents:
            self.logger.warning("知识库为空")
            self.logger.end("retrieve-检索文档", success=False, reason="empty_kb")
            return []

        if self.embeddings_available:
            # 使用向量相似度
            self.logger.step("步骤1", "使用向量相似度检索")
            result = self._retrieve_with_embeddings(query, top_k, threshold)
        else:
            # 使用关键词匹配
            self.logger.step("步骤1", "使用关键词匹配检索")
            result = self._retrieve_with_keywords(query, top_k)

        self.logger.end("retrieve-检索文档", success=True, results_count=len(result))
        return result

    def _retrieve_with_embeddings(self, query: str, top_k: int, threshold: float) -> List[str]:
        """使用嵌入模型检索"""
        self.logger.debug("开始向量检索")
        try:
            # 编码查询
            self.logger.step("步骤1", "编码查询")
            query_emb = self.model.encode([query])

            # 编码文档
            self.logger.step("步骤2", "编码文档", docs_count=len(self.documents))
            doc_embs = self.model.encode(self.documents)

            # 计算相似度
            self.logger.step("步骤3", "计算相似度")
            similarities = self.util.cos_sim(query_emb, doc_embs)[0]

            # 获取 top_k 结果
            self.logger.step("步骤4", "筛选结果", threshold=threshold)
            results = []
            for idx, score in enumerate(similarities):
                if score > threshold:
                    results.append((score.item(), self.documents[idx]))

            # 按相似度排序
            self.logger.step("步骤5", "排序结果")
            results.sort(reverse=True, key=lambda x: x[0])

            # 返回文档
            retrieved = [doc for score, doc in results[:top_k]]

            self.logger.info(f"✅ 向量检索完成", retrieved_count=len(retrieved))
            return retrieved

        except Exception as e:
            self.logger.error(f"❌ 向量检索失败，回退到关键词匹配", error=str(e))
            return self._retrieve_with_keywords(query, top_k)

    def _retrieve_with_keywords(self, query: str, top_k: int) -> List[str]:
        """使用关键词匹配检索"""
        self.logger.debug("开始关键词检索")

        # 分词（简单按空格分）
        self.logger.step("步骤1", "分词")
        keywords = query.lower().split()
        self.logger.debug("关键词", keywords=keywords)

        # 计算每个文档的匹配分数
        self.logger.step("步骤2", "计算匹配分数")
        results = []
        for doc in self.documents:
            doc_lower = doc.lower()
            score = sum(1 for kw in keywords if kw in doc_lower)
            if score > 0:
                results.append((score, doc))

        # 按分数排序
        self.logger.step("步骤3", "排序结果")
        results.sort(reverse=True, key=lambda x: x[0])

        # 返回 top_k
        retrieved = [doc for score, doc in results[:top_k]]

        self.logger.info(f"✅ 关键词检索完成", retrieved_count=len(retrieved))
        return retrieved

    def clear(self):
        """清空知识库"""
        self.logger.info("清空知识库")
        self.documents = []
        self.logger.info("✅ 知识库已清空")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_documents": len(self.documents),
            "embeddings_available": self.embeddings_available,
            "model_type": "SentenceTransformer" if self.embeddings_available else "Keyword Match"
        }


# 全局 RAG 实例
_default_rag = SimpleRAG()


def get_rag() -> SimpleRAG:
    """获取全局 RAG 实例"""
    return _default_rag


def retrieve(query: str, top_k: int = 5, threshold: float = 0.5) -> List[str]:
    """
    便捷函数：检索文档

    Args:
        query: 查询字符串
        top_k: 返回的文档数量
        threshold: 相似度阈值

    Returns:
        相关文档列表
    """
    rag = get_rag()
    return rag.retrieve(query, top_k, threshold)


def add_sample_documents():
    """添加示例文档"""
    rag = get_rag()

    sample_docs = [
        "MCP (Model Context Protocol) 是一个用于 AI 模型与外部工具通信的协议标准。",
        "Claude 是 Anthropic 公司开发的大语言模型，具有强大的对话和推理能力。",
        "FastAPI 是一个现代、快速的 Python Web 框架，用于构建 API。",
        "向量数据库如 FAISS 可以高效地存储和检索高维向量。",
        "RAG (Retrieval Augmented Generation) 通过检索相关信息来增强生成质量。",
        "Agent 是能够自主决策和执行任务的 AI 系统。",
        "Router 负责根据任务内容动态选择执行策略。",
        "Skill 是 Agent 的具体能力实现，如工具调用、知识检索等。",
        "Python 是一种广泛使用的编程语言，特别适合 AI 和数据科学。",
        "机器学习是人工智能的一个分支，通过数据训练模型。"
    ]

    rag.add_documents(sample_docs)
    print(f"[RAG] 已添加 {len(sample_docs)} 个示例文档")


# 向后兼容的类
class RAGController:
    """
    RAG 控制器（向后兼容）
    """

    def __init__(self):
        self.rag = get_rag()

    def should_use_rag(self, query: str) -> bool:
        """判断是否应该使用 RAG"""
        docs = self.rag.retrieve(query, top_k=1)
        return len(docs) > 0

    def retrieve_context(self, query: str) -> str:
        """检索上下文"""
        docs = self.rag.retrieve(query, top_k=5)

        if not docs:
            return ""

        # 重排序（这里简化为原顺序）
        docs = docs[:2]  # 控制上下文长度

        return "\n".join(docs)


# 测试代码
if __name__ == "__main__":
    print("测试 RAG 模块\n")

    # 添加示例文档
    add_sample_documents()

    # 测试检索
    test_queries = [
        "什么是 MCP？",
        "介绍一下 FastAPI",
        "RAG 是什么？",
        "Agent 的作用"
    ]

    print("\n" + "=" * 60)
    print("测试检索")
    print("=" * 60)

    for query in test_queries:
        print(f"\n查询: {query}")
        results = retrieve(query, top_k=3)
        print(f"找到 {len(results)} 个相关文档:")
        for i, doc in enumerate(results, 1):
            print(f"  {i}. {doc}")

    # 统计信息
    print("\n" + "=" * 60)
    stats = get_rag().get_stats()
    print("RAG 统计信息:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
