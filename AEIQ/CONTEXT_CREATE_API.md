# Context 创建接口文档

## 概述

云端接收 `{"aedir": "目录路径"}` 创建 Context，生成唯一的 `session_id` 并返回给客户端。

## API 接口

### 创建 Context

**URL**: `POST /ae/context/create`

**请求头**:
```
Content-Type: application/json
```

**请求体**:
```json
{
  "aedir": "/Users/username/project"
}
```

**响应（成功 200）**:
```json
{
  "contextid": "ctx_a1b2c3d4e5f6g7h8"
}
```

**响应（失败 400）**:
```json
{
  "detail": "aedir cannot be empty"
}
```

**响应（失败 500）**:
```json
{
  "detail": "Failed to create context: <error message>"
}
```

## 数据流

```
客户端                                 服务端
  │                                     │
  ├─ POST /ae/context/create ──────────►
  │  {"aedir": "/path/to/dir"}          │
  │                                     │
  │                                   生成 session_id
  │                                   ctx_xxxxxxxxxxxx
  │                                     │
  │                                   创建 AEContext
  │                                   - session_id
  │                                   - aedir
  │                                     │
  ◄─ {"contextid": "ctx_xxx..."} ──────┤
  │                                     │
  │                                     │
使用 contextid 作为后续通信的标识       Context 保存在内存
  │                                   - contexts[session_id]
  └─                                   - 包含 aedir 信息
```

## 核心实现

### 1. 服务端数据模型

**文件**: `routes/ae_context_create.py`

```python
class CreateContextRequest(BaseModel):
    """创建 Context 请求模型"""
    aedir: str  # Context 对应的目录路径

class CreateContextResponse(BaseModel):
    """创建 Context 响应模型"""
    contextid: str  # 生成的唯一 session_id
```

### 2. Context 初始化

**文件**: `Context/AEContext.py`

```python
class AEContext:
    def __init__(self, session_id: str, aedir: Optional[str] = None, enable_cache: bool = True):
        """
        初始化 Context

        Args:
            session_id: 会话唯一标识符（由服务端生成）
            aedir: Context 对应的目录路径
            enable_cache: 是否启用缓存
        """
        self.session_id = session_id
        self.aedir = aedir  # 存储目录路径
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        # ... 其他初始化
```

### 3. Context 管理器

**文件**: `Context/AEContextManager.py`

```python
async def get_or_create_context(self, session_id: str, aedir: Optional[str] = None) -> AEContext:
    """
    获取或创建 Context 实例

    Args:
        session_id: 会话 ID
        aedir: Context 对应的目录路径（可选）

    Returns:
        AEContext 实例
    """
    async with self._lock:
        if session_id not in self.contexts:
            # 创建新 Context，传入 aedir
            self.contexts[session_id] = AEContext(session_id=session_id, aedir=aedir)
        else:
            # 更新访问时间
            self.contexts[session_id].updated_at = datetime.now()
            # 如果提供了新的 aedir，更新它
            if aedir is not None:
                self.contexts[session_id].aedir = aedir

        return self.contexts[session_id]
```

### 4. 创建接口

**文件**: `routes/ae_context_create.py`

```python
@router.post("/ae/context/create", response_model=CreateContextResponse)
async def create_context(request: CreateContextRequest):
    """创建新的 Context"""
    from app import ae_context_manager

    # 1. 验证 aedir
    if not request.aedir or request.aedir.strip() == "":
        raise HTTPException(status_code=400, detail="aedir cannot be empty")

    # 2. 生成唯一的 session_id
    session_id = f"ctx_{uuid.uuid4().hex[:16]}"

    # 3. 创建 Context（传入 aedir）
    context = await ae_context_manager.get_or_create_context(
        session_id=session_id,
        aedir=request.aedir
    )

    # 4. 返回 session_id
    return CreateContextResponse(contextid=session_id)
```

## Session ID 格式

- **前缀**: `ctx_`
- **长度**: 16 位十六进制字符
- **示例**: `ctx_a1b2c3d4e5f6g7h8`
- **生成方式**: `f"ctx_{uuid.uuid4().hex[:16]}"`

## Context 数据结构

创建后的 Context 包含以下字段：

```python
{
    "session_id": "ctx_a1b2c3d4e5f6g7h8",    # 唯一标识符
    "aedir": "/Users/username/project",       # 目录路径
    "created_at": "2026-04-17T10:00:00",     # 创建时间
    "updated_at": "2026-04-17T10:00:00",     # 更新时间
    "message_count": 0,                       # 消息数量
    "cache_enabled": true                     # 是否启用缓存
}
```

## 测试

### 1. 启动服务

```bash
cd /Users/tianjunqi/Project/Self/Agents/Service/AEIQ
uvicorn app:app --reload --port 8000
```

### 2. 运行测试脚本

```bash
python test_context_create.py
```

### 3. 手动测试（使用 curl）

**创建 Context**:
```bash
curl -X POST "http://localhost:8000/ae/context/create" \
  -H "Content-Type: application/json" \
  -d '{"aedir": "/Users/test/myproject"}'
```

**预期响应**:
```json
{
  "contextid": "ctx_a1b2c3d4e5f6g7h8"
}
```

**查看所有 Context**:
```bash
curl http://localhost:8000/ae/contexts/stats
```

**预期响应**:
```json
{
  "ctx_a1b2c3d4e5f6g7h8": {
    "session_id": "ctx_a1b2c3d4e5f6g7h8",
    "aedir": "/Users/test/myproject",
    "message_count": 0,
    "created_at": "2026-04-17T10:00:00",
    "updated_at": "2026-04-17T10:00:00",
    "cache_enabled": true
  }
}
```

## 客户端集成

客户端在收到 `contextid` 后，应该：

1. **保存 session_id**：作为后续所有请求的标识
2. **创建本地 Context**：使用相同的 ID
3. **后续通信**：所有请求都带上这个 session_id

示例（Swift）:
```swift
// 1. 创建请求
let request = ["aedir": "/Users/username/project"]

// 2. 发送请求
URLSession.shared.dataTask(with: createRequest) { data, response, error in
    if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
       let sessionId = json["contextid"] as? String {
        
        // 3. 使用 session_id 创建本地 Context
        let config = AEContextConfig(content: path)
        let context = AEAIContextManager.createContext(config, withId: sessionId)
        
        // 4. 后续所有请求都使用这个 session_id
        print("✅ Context 创建成功: \(sessionId)")
    }
}.resume()
```

## 注意事项

1. **session_id 唯一性**：每次创建都生成新的唯一 ID
2. **aedir 必填**：不能为空或空字符串
3. **aedir 存储**：服务端保存 aedir，可用于后续查询
4. **Context 生命周期**：创建后保存在内存中，服务重启会丢失
5. **并发安全**：使用 asyncio.Lock 保证线程安全
6. **ID 同步**：客户端和服务端使用相同的 session_id

## 错误处理

| 错误码 | 原因 | 解决方法 |
|--------|------|----------|
| 400 | aedir 为空 | 提供有效的目录路径 |
| 500 | 服务器内部错误 | 检查服务端日志 |

## 扩展功能

未来可以增强的功能：

1. **持久化存储**：将 Context 保存到数据库
2. **目录验证**：验证 aedir 是否为有效路径
3. **权限检查**：验证用户是否有访问该目录的权限
4. **Context 元数据**：支持更多自定义字段
5. **批量创建**：支持一次创建多个 Context
6. **Context 搜索**：根据 aedir 搜索已有的 Context

## 相关文件

- `routes/ae_context_create.py` - 创建接口
- `Context/AEContext.py` - Context 模型
- `Context/AEContextManager.py` - Context 管理器
- `app.py` - 路由注册
- `test_context_create.py` - 测试脚本
