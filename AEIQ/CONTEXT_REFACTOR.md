# Context 重构 - Session ID 生成策略

## 重构目标

将 `session_id` 的生成逻辑从外部（路由层）移到 `AEContext` 内部，实现更好的封装和职责分离。

## 重构前后对比

### 重构前（旧方式）

**路由层生成 session_id**：
```python
# routes/ae_context_create.py
session_id = f"ctx_{uuid.uuid4().hex[:16]}"
context = await ae_context_manager.get_or_create_context(
    session_id=session_id,
    aedir=request.aedir
)
```

**Context 接收外部传入的 session_id**：
```python
# Context/AEContext.py
def __init__(self, session_id: str, aedir: Optional[str] = None):
    self.session_id = session_id  # 外部传入
```

**问题**：
- ❌ 职责不清：路由层不应该负责生成 ID
- ❌ 重复代码：每个需要创建 Context 的地方都要生成 ID
- ❌ 不易维护：如果 ID 格式需要修改，要改多个地方

### 重构后（新方式）

**Context 内部生成 session_id**：
```python
# Context/AEContext.py
def __init__(self, aedir: Optional[str] = None, enable_cache: bool = True):
    # 自动生成 session_id
    self.session_id = self._generate_session_id()
    self.aedir = aedir

@staticmethod
def _generate_session_id() -> str:
    """生成唯一的 session_id"""
    return f"ctx_{uuid.uuid4().hex[:16]}"
```

**路由层只需获取 session_id**：
```python
# routes/ae_context_create.py
context = await ae_context_manager.create_context(aedir=request.aedir)
session_id = context.session_id  # 从实例获取
return CreateContextResponse(contextid=session_id)
```

**优势**：
- ✅ 职责清晰：Context 负责自己的 ID 生成
- ✅ 代码简洁：外部只需要获取，不需要生成
- ✅ 易于维护：ID 格式集中管理，修改一处即可
- ✅ 封装良好：外部不需要知道 ID 生成的细节

## 架构设计

```
┌─────────────────────────────────────┐
│  Route Layer (ae_context_create.py) │
│                                     │
│  create_context(request)            │
│    ├─ 验证 aedir                    │
│    ├─ context = create_context()   │  <- 不再生成 ID
│    └─ return context.session_id    │  <- 只获取 ID
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│  Manager Layer (AEContextManager)   │
│                                     │
│  create_context(aedir)              │
│    └─ context = AEContext(aedir)   │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│  Model Layer (AEContext)            │
│                                     │
│  __init__(aedir):                   │
│    ├─ self.session_id =            │  <- 内部生成 ID
│    │  _generate_session_id()       │
│    └─ self.aedir = aedir           │
│                                     │
│  @staticmethod                      │
│  _generate_session_id() -> str:    │  <- ID 生成逻辑
│    return f"ctx_{uuid.uuid4()...}" │
└─────────────────────────────────────┘
```

## 修改文件清单

### 1. `Context/AEContext.py`

**修改内容**：
- ✅ 添加 `import uuid`
- ✅ 移除 `session_id` 参数
- ✅ 添加 `_generate_session_id()` 静态方法
- ✅ 在 `__init__` 中自动调用生成方法

### 2. `Context/AEContextManager.py`

**修改内容**：
- ✅ 添加 `create_context(aedir)` 方法（新方法）
- ✅ 保留 `get_or_create_context(session_id, aedir)` 方法（兼容旧代码）

### 3. `routes/ae_context_create.py`

**修改内容**：
- ✅ 移除 `import uuid`
- ✅ 移除 `session_id = f"ctx_..."` 生成代码
- ✅ 改用 `create_context(aedir)` 方法
- ✅ 从 `context.session_id` 获取 ID

## Session ID 生成规则

**格式**：`ctx_{16位十六进制}`

**示例**：`ctx_a1b2c3d4e5f6g7h8`

**实现**：
```python
@staticmethod
def _generate_session_id() -> str:
    """生成唯一的 session_id"""
    return f"ctx_{uuid.uuid4().hex[:16]}"
```

**特点**：
- 前缀 `ctx_` 标识 Context 类型
- 16 位十六进制保证唯一性
- UUID v4 随机生成，碰撞概率极低

## API 使用方式

### 新方式（推荐）

```python
# 创建 Context（自动生成 session_id）
context = await ae_context_manager.create_context(aedir="/path/to/dir")

# 获取自动生成的 session_id
session_id = context.session_id
print(f"Generated session_id: {session_id}")
```

### 旧方式（兼容）

```python
# 手动指定 session_id（兼容旧代码）
context = await ae_context_manager.get_or_create_context(
    session_id="custom_id",
    aedir="/path/to/dir"
)
```

## 兼容性

### 向后兼容

- ✅ 保留 `get_or_create_context(session_id, aedir)` 方法
- ✅ 旧代码可以继续使用指定的 session_id
- ✅ 不影响现有的其他路由（如 ae_context_chat）

### 迁移建议

新代码应该使用 `create_context(aedir)` 方法：

```python
# ❌ 旧方式（不推荐）
session_id = f"ctx_{uuid.uuid4().hex[:16]}"
context = await manager.get_or_create_context(session_id, aedir)

# ✅ 新方式（推荐）
context = await manager.create_context(aedir)
session_id = context.session_id
```

## 测试

### 测试 session_id 生成

```python
from Context.AEContext import AEContext

# 创建多个 Context
context1 = AEContext(aedir="/path1")
context2 = AEContext(aedir="/path2")

# 验证 session_id 唯一性
assert context1.session_id != context2.session_id
assert context1.session_id.startswith("ctx_")
assert len(context1.session_id) == 20  # ctx_ + 16位
```

### 测试 API 接口

```bash
# 测试创建 Context
curl -X POST http://localhost:8000/ae/context/create \
  -H "Content-Type: application/json" \
  -d '{"aedir":"/test/project"}'

# 预期响应
{
  "contextid": "ctx_a1b2c3d4e5f6g7h8"
}
```

## 优势总结

### 1. **职责清晰**
- Context 负责自己的数据和行为
- 外部只需要使用，不需要了解实现细节

### 2. **代码简洁**
- 外部代码更简单：`context = create_context(aedir)`
- 不需要重复写 ID 生成逻辑

### 3. **易于维护**
- ID 格式集中管理在 `_generate_session_id()`
- 修改 ID 规则只需要改一个方法

### 4. **类型安全**
- ID 生成逻辑在类内部，不会被误用
- 静态方法可以单独测试

### 5. **扩展性**
- 未来可以轻松添加其他 ID 生成策略
- 可以添加 ID 验证、格式检查等功能

## 未来扩展

### 1. 自定义 ID 前缀

```python
@staticmethod
def _generate_session_id(prefix: str = "ctx") -> str:
    """生成唯一的 session_id，支持自定义前缀"""
    return f"{prefix}_{uuid.uuid4().hex[:16]}"
```

### 2. ID 验证

```python
@staticmethod
def is_valid_session_id(session_id: str) -> bool:
    """验证 session_id 格式是否正确"""
    import re
    pattern = r"^ctx_[0-9a-f]{16}$"
    return bool(re.match(pattern, session_id))
```

### 3. ID 冲突检测

```python
def __init__(self, aedir: Optional[str] = None, enable_cache: bool = True):
    # 生成 ID，确保唯一性
    max_retries = 10
    for _ in range(max_retries):
        self.session_id = self._generate_session_id()
        if not self._id_exists(self.session_id):
            break
    else:
        raise RuntimeError("Failed to generate unique session_id")
```

## 相关文件

- `Context/AEContext.py` - Session ID 生成实现
- `Context/AEContextManager.py` - Manager 层接口
- `routes/ae_context_create.py` - 路由层使用
- `test_context_create.py` - 测试脚本
