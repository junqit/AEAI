# QuestionCache - 问题与回复缓存系统

## 概述

QuestionCache 是一个用于记录用户问题和LLM回复的缓存框架，支持构建对话上下文，适用于多轮对话的AI应用场景。

## 主要特性

- ✅ **持久化存储**：支持将对话历史保存到磁盘（JSON格式）
- ✅ **多LLM支持**：可记录不同LLM的回复，灵活选择使用哪个LLM的答案
- ✅ **上下文构建**：自动构建符合LLM API格式的上下文消息
- ✅ **智能裁剪**：支持按轮数或token数量限制上下文大小
- ✅ **线程安全**：使用锁机制保证并发安全
- ✅ **灵活配置**：可选择是否启用持久化，自定义存储路径

## 目录结构

```
QuestionCache/
├── __init__.py           # 模块导出
├── cache_entry.py        # 缓存条目数据结构
├── cache_store.py        # 缓存存储实现
├── context_builder.py    # 上下文构建器
├── examples.py           # 使用示例
├── README.md             # 本文档
└── cache_data/           # 默认缓存数据目录（自动创建）
```

## 快速开始

### 基础使用

```python
from QuestionCache import QuestionCacheStore

# 1. 创建缓存存储
cache = QuestionCacheStore(enable_persistence=True)

# 2. 记录用户问题
session_id = "user_001"
cache.add_question(
    session_id=session_id,
    question="什么是机器学习？"
)

# 3. 记录LLM回复
cache.add_response(
    session_id=session_id,
    response="机器学习是人工智能的一个分支...",
    llm_type="gpt-4"
)

# 4. 获取历史记录
history = cache.get_session_history(session_id)
for entry in history:
    print(f"[{entry.role.value}] {entry.content}")
```

### 构建LLM上下文

```python
from QuestionCache import QuestionCacheStore, ContextBuilder

cache = QuestionCacheStore()
builder = ContextBuilder(cache)

# 构建标准格式的上下文（用于LLM API调用）
context = builder.build_context(
    session_id="user_001",
    max_turns=5,              # 保留最近5轮对话
    include_system_prompt=True
)

# context 格式:
# [
#     {"role": "system", "content": "你是一个AI助手..."},
#     {"role": "user", "content": "问题1"},
#     {"role": "assistant", "content": "回答1"},
#     ...
# ]
```

## 核心组件

### 1. CacheEntry - 缓存条目

表示单条对话消息（问题或回复）。

```python
from QuestionCache import CacheEntry, MessageRole

entry = CacheEntry(
    session_id="session_001",
    role=MessageRole.USER,
    content="你好",
    metadata={"source": "web"}
)
```

### 2. QuestionCacheStore - 缓存存储

管理所有会话的缓存数据。

**主要方法：**

- `add_question()` - 添加用户问题
- `add_response()` - 添加LLM回复
- `get_session_history()` - 获取会话历史
- `get_conversation_turns()` - 获取结构化的对话轮次
- `clear_session()` - 清空会话
- `get_stats()` - 获取统计信息

### 3. ContextBuilder - 上下文构建器

从缓存构建LLM调用所需的上下文。

**主要方法：**

- `build_context()` - 构建标准上下文
- `build_context_with_llm_selection()` - 选择特定LLM的回复构建上下文
- `build_summary_context()` - 构建带摘要的上下文（节省token）
- `get_context_stats()` - 获取上下文统计信息

## 使用场景

### 场景1: 多轮对话管理

```python
cache = QuestionCacheStore()

# 第1轮
cache.add_question("session_1", "介绍Python")
cache.add_response("session_1", "Python是一种编程语言...", "gpt-4")

# 第2轮
cache.add_question("session_1", "它有什么特点？")
cache.add_response("session_1", "Python的特点包括...", "gpt-4")

# 获取完整对话历史
turns = cache.get_conversation_turns("session_1")
print(f"共 {len(turns)} 轮对话")
```

### 场景2: 多LLM比较

```python
# 同一个问题，多个LLM回答
cache.add_question("session_2", "解释量子纠缠")
cache.add_response("session_2", "GPT-4的回答...", "gpt-4")
cache.add_response("session_2", "Claude的回答...", "claude-3")
cache.add_response("session_2", "Gemini的回答...", "gemini")

# 后续对话时，可以选择使用哪个LLM的回答作为上下文
builder = ContextBuilder(cache)
context = builder.build_context_with_llm_selection(
    "session_2",
    preferred_llm="gpt-4"
)
```

### 场景3: Token限制

```python
# 限制上下文大小，避免超过LLM的token限制
context = builder.build_context(
    session_id="session_3",
    max_tokens=2000,  # 限制在2000 tokens以内
    max_turns=10      # 最多10轮对话
)
```

### 场景4: 持久化存储

```python
# 程序启动时
cache = QuestionCacheStore(
    cache_dir="/path/to/cache",
    enable_persistence=True
)

# 数据自动保存到磁盘
cache.add_question("session_4", "你好")

# 程序重启后，数据仍然存在
history = cache.get_session_history("session_4")
```

## 与AEContext集成

可以将QuestionCache集成到现有的AEContext中：

```python
from AEContext import AEContext
from QuestionCache import QuestionCacheStore, ContextBuilder

class AEContextWithCache(AEContext):
    def __init__(self, session_id: str):
        super().__init__(session_id)
        self.cache = QuestionCacheStore(enable_persistence=True)
        self.context_builder = ContextBuilder(self.cache)
    
    async def process_message(self, user_input: str, llm_types: List[str]):
        # 记录用户问题
        self.cache.add_question(self.session_id, user_input)
        
        # 调用父类方法处理
        responses = await super().process_message(user_input, llm_types)
        
        # 记录LLM回复
        for response in responses:
            if not response.error:
                self.cache.add_response(
                    self.session_id,
                    str(response.response),
                    response.llm_type
                )
        
        return responses
    
    def get_context_for_next_call(self, max_turns=5):
        """获取下次调用的上下文"""
        return self.context_builder.build_context(
            self.session_id,
            max_turns=max_turns
        )
```

## 配置选项

### QuestionCacheStore 配置

```python
cache = QuestionCacheStore(
    cache_dir="./my_cache",      # 缓存目录
    enable_persistence=True       # 启用持久化
)
```

### ContextBuilder 配置

```python
context = builder.build_context(
    session_id="session_id",
    max_turns=5,                  # 最大轮数
    max_tokens=2000,              # 最大token数
    include_system_prompt=True,   # 包含系统提示
    system_prompt="自定义提示..."  # 自定义系统提示
)
```

## 性能考虑

1. **内存管理**：活跃会话保存在内存中，使用`clear_session()`及时清理
2. **磁盘I/O**：每次添加条目都会写磁盘，高频场景可考虑批量写入
3. **Token估算**：当前使用字符数/1.5的简单估算，可根据具体LLM调整

## 运行示例

```bash
cd /Users/tianjunqi/Project/Self/Agents/Service/AEIQ/Context/QuestionCache
python examples.py
```

## API文档

详细API文档请参考源代码中的docstring。

## 许可证

MIT License
