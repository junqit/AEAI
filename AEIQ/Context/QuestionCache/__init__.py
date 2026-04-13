"""
QuestionCache - 问题与回复缓存模块

用于记录用户问题和LLM回复，支持构建对话上下文
"""

from .cache_store import QuestionCacheStore
from .cache_entry import CacheEntry, MessageRole
from .context_builder import ContextBuilder

__all__ = [
    'QuestionCacheStore',
    'CacheEntry',
    'MessageRole',
    'ContextBuilder'
]
