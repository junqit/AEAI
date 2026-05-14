# ContextManager 请求处理流程

## 架构设计

### 核心原则
1. **统一响应组装点**：只在 `_send_success_response()` 中组装 AENetRsp
2. **分层处理**：ContextManager 处理路由，AEContext 处理业务
3. **结果驱动**：所有处理方法返回 dict，由统一方法组装响应

## 请求流程

```
UDP 请求
    │
    ▼
SocketConnectionManager
    │
    │ handle_request(request, connection_id)
    ▼
AEContextManager
    │
    ├─ path == "/ae/context/create" ─► _handle_create_context()
    │                                        │
    │                                        ▼
    │                                   {"context_id": "...", "status": "created"}
    │
    ├─ path == "/ae/context/cancel" ──► _handle_cancel_context()
    ��                                        │
    │                                        ▼
    │                                   {"context_id": "...", "status": "cancelled"}
    │
    └─ 其他消息 ─────────────────────► _handle_context_message()
                                            │
                                            ▼
                                      AEContext.handle_request()
                                            │
                                            ▼
                                      AEContext.process_message()
                                            │
                                            ▼
                                      并行���用 LLMs
                                            │
                                            ▼
                                      {
                                        "answer": {
                                          "claude": {"content": "...", "timestamp": "...", "error": ""},
                                          "gemini": {"content": "...", "timestamp": "...", "error": ""}
                                        }
                                      }
    │
    │ 所有方法返回 dict
    ▼
_send_success_response(connection_id, request_id, result)
    │
    │ 唯一的 AENetRsp 组装点
    ▼
AENetRsp.create_success(
    requestId=request_id,
    content="Success",
    result=result
)
    │
    ▼
SocketConnectionManager.send_response()
    │
    ▼
客户端收到响应
```

## 方法职责

### AEContextManager

**handle_request(request, connection_id)**
- 唯一的入口方法
- 路由到不同的处理方法
- 捕获异常并发送错误响应

**_handle_create_context(request) -> dict**
- 创建新的 Context
- 返回：`{"context_id": "...", "status": "created", "timestamp": "..."}`

**_handle_cancel_context(request) -> dict**
- 取消指定的 Context
- 返回：`{"context_id": "...", "status": "cancelled", "timestamp": "..."}`

**_handle_context_message(request) -> dict**
- 将消息转发给 AEContext 处理
- 获取或创建 Context
- 调用 AEContext.handle_request()
- 返回 AI 处理结果

**_send_success_response(connection_id, request_id, result)**
- **唯一的 AENetRsp 组装点**
- 统一组装成功响应
- 调用 _send_response() 发送

**_send_error_response(connection_id, request_id, error_code, error_message)**
- 统一组装错误响应
- 调用 _send_response() 发送

**_send_response(connection_id, response)**
- 底层发送方法
- 调用网络层的 send_response()

### AEContext

**handle_request(request) -> dict**
- 从 request 提取问题和 LLM 类型
- 调用 process_message() 处理
- 转换结果为指定格式

**process_message(user_input, llm_types) -> List[AELLMResponse]**
- 并行调用多个 LLM
- 返回 LLM 响应列表

## 数据格式

### 输入请求 (AENetReq)
```json
{
  "path": "/ae/context/chat",
  "context": {"id": "ctx_xxx"},
  "question": {"type": "text", "content": "问题内容"},
  "llm_types": ["claude", "gemini"],
  "requestId": "xxx"
}
```

### 处理结果 (各方法返回的 dict)

**创建 Context:**
```json
{
  "context_id": "ctx_new_id",
  "status": "created",
  "timestamp": "2026-04-28T19:00:00"
}
```

**取消 Context:**
```json
{
  "context_id": "ctx_xxx",
  "status": "cancelled",
  "timestamp": "2026-04-28T19:00:00"
}
```

**AI 回复:**
```json
{
  "answer": {
    "claude": {
      "content": "Claude的回答...",
      "timestamp": "2026-04-28T19:00:00.123",
      "error": ""
    },
    "gemini": {
      "content": "Gemini的回答...",
      "timestamp": "2026-04-28T19:00:00.456",
      "error": ""
    }
  }
}
```

### 最终响应 (AENetRsp)
```json
{
  "status": "success",
  "requestId": "xxx",
  "content": "Success",
  "result": {
    "answer": {
      "claude": {"content": "...", "timestamp": "...", "error": ""},
      "gemini": {"content": "...", "timestamp": "...", "error": ""}
    }
  }
}
```

## 优势

### 1. 单一职责
- ContextManager：路由和响应组装
- AEContext：AI 业务处理

### 2. 统一管理
- 只有一处组装 AENetRsp
- 易于修改响应格式
- 易于添加公共逻辑（日志、监控等）

### 3. 结果驱动
- 所有处理方法返回纯数据（dict）
- 响应组装与业务逻辑分离
- 易于测试

### 4. 易扩展
- 添加新的 path 处理：新增 _handle_xxx() 方法
- 修改响应格式：只需修改 _send_success_response()
- 添加中间件：在统一组装点添加逻辑

## 错误处理

所有异常在 `handle_request()` 中捕获：
```python
try:
    result = self._handle_xxx(request)
    self._send_success_response(connection_id, request.requestId, result)
except Exception as e:
    self._send_error_response(connection_id, request.requestId, "ERR_INTERNAL", str(e))
```

## 测试策略

### 单元测试
- 测试各个 _handle_xxx() 方法返回正确的 dict
- 测试 _send_success_response() 组装正确的 AENetRsp
- Mock AEContext 测试 ContextManager

### 集成测试
- 发送真实请求验证端到端流程
- 验证响应格式符合规范
