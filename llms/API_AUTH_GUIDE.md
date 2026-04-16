# API 认证使用指南

## 配置

API Key 配置在 `config.py` 中：

```python
API_KEY: str = os.getenv("API_KEY", "ae-agent-2024-fixed-key-9527")
API_KEY_HEADER: str = "X-API-Key"
```

### 修改 API Key

**方式 1：环境变量（推荐）**
```bash
export API_KEY="your-custom-api-key-here"
python app.py
```

**方式 2：直接修改 config.py**
```python
API_KEY: str = "your-custom-api-key-here"
```

---

## 三种认证方式

### ✅ 方法 1：全局中间件（推荐）

**适用场景**：所有接口都需要认证（除了排除列表）

**优点**：
- 一次配置，全局生效
- 统一管理，易于维护
- 可灵活配置排除路径

**实现**：在 `app.py` 中已配置

```python
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    excluded_paths = ["/health", "/docs", "/redoc", "/openapi.json", "/"]
    
    if request.url.path in excluded_paths:
        return await call_next(request)
    
    api_key = request.headers.get(config.API_KEY_HEADER)
    if not api_key or api_key != config.API_KEY:
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid API Key"}
        )
    
    return await call_next(request)
```

**排除路径配置**：
- `/health` - 健康检查
- `/docs` - API 文档
- `/redoc` - ReDoc 文档
- `/openapi.json` - OpenAPI Schema
- `/` - 根路径

---

### 方法 2：路由组级别

**适用场景**：某些路由组需要认证，其他不需要

**优点**：
- 精确控制哪些路由组需要认证
- 不同路由组可以有不同的认证策略

**实现**：在 `routes/__init__.py` 中配置

```python
from auth import verify_api_key

def register_routes(app: FastAPI):
    # 不需要认证
    app.include_router(health_router)
    
    # 需要认证
    app.include_router(
        question_router,
        dependencies=[Depends(verify_api_key)]
    )
```

---

### 方法 3：单个接口级别

**适用场景**：只有特定接口需要认证

**优点**：
- 最精细的控制
- 适合混合认证需求

**实现**：在具体的路由函数中添加

```python
from auth import verify_api_key

@router.post("/endpoint")
async def my_endpoint(
    request: MyRequest,
    api_key: str = Depends(verify_api_key)
):
    # 业务逻辑
    pass
```

---

## 客户端调用示例

### 1. cURL 示例

```bash
# ✅ 正确的请求（包含 API Key）
curl -X POST "http://localhost:9999/aellms/question" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ae-agent-2024-fixed-key-9527" \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}],
    "llm_type": "claude"
  }'

# ❌ 错误的请求（缺少 API Key）
curl -X POST "http://localhost:9999/aellms/question" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}],
    "llm_type": "claude"
  }'
# 返回: 401 Unauthorized
```

### 2. Python requests 示例

```python
import requests

# API 配置
BASE_URL = "http://localhost:9999"
API_KEY = "ae-agent-2024-fixed-key-9527"

headers = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}

# 发送请求
response = requests.post(
    f"{BASE_URL}/aellms/question",
    headers=headers,
    json={
        "messages": [{"role": "user", "content": "Hello"}],
        "llm_type": "claude"
    }
)

print(response.status_code)
print(response.json())
```

### 3. JavaScript/Fetch 示例

```javascript
const API_KEY = "ae-agent-2024-fixed-key-9527";

fetch("http://localhost:9999/aellms/question", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
  },
  body: JSON.stringify({
    messages: [{role: "user", content: "Hello"}],
    llm_type: "claude"
  })
})
.then(response => response.json())
.then(data => console.log(data))
.catch(error => console.error("Error:", error));
```

### 4. WebSocket 示例

WebSocket 连接也需要在连接时提供 API Key：

```python
import websockets
import json
import asyncio

async def connect_with_auth():
    uri = "ws://localhost:9999/ws/session123"
    
    # WebSocket 连接时在 headers 中传递 API Key
    async with websockets.connect(
        uri,
        extra_headers={
            "X-API-Key": "ae-agent-2024-fixed-key-9527"
        }
    ) as websocket:
        # 接收欢迎消息
        welcome = await websocket.recv()
        print(f"Connected: {welcome}")
        
        # 发送消息
        await websocket.send(json.dumps({
            "type": "chat",
            "message": "Hello"
        }))
        
        # 接收响应
        response = await websocket.recv()
        print(f"Response: {response}")

asyncio.run(connect_with_auth())
```

---

## 错误响应

### 缺少 API Key
```json
{
  "detail": "Missing X-API-Key header",
  "error": "unauthorized"
}
```
HTTP Status: `401 Unauthorized`

### 无效的 API Key
```json
{
  "detail": "Invalid API Key",
  "error": "unauthorized"
}
```
HTTP Status: `401 Unauthorized`

---

## 测试

### 测试健康检查（不需要认证）
```bash
curl http://localhost:9999/health
# 返回: {"status": "ok", ...}
```

### 测试受保护的接口（需要认证）
```bash
# 有效的 API Key
curl -H "X-API-Key: ae-agent-2024-fixed-key-9527" \
  http://localhost:9999/aellms/question \
  -X POST -d '...'

# 无效的 API Key
curl -H "X-API-Key: wrong-key" \
  http://localhost:9999/aellms/question \
  -X POST -d '...'
# 返回: 401 Unauthorized
```

---

## 推荐配置

**生产环境**：
1. ✅ 使用**方法 1（全局中间件）**
2. ✅ 通过**环境变量**设置 API Key
3. ✅ 使用**强随机字符串**作为 API Key
4. ✅ 定期轮换 API Key

**开发环境**：
1. 可以使用固定的 API Key 方便测试
2. 或者临时注释掉中间件跳过认证

```python
# 开发环境临时禁用认证
# @app.middleware("http")
# async def api_key_middleware(request: Request, call_next):
#     ...
```

---

## 安全建议

1. **不要在代码中硬编码 API Key** - 使用环境变量
2. **不要在日志中打印 API Key**
3. **使用 HTTPS** - 生产环境必须使用 HTTPS
4. **定期轮换** - 定期更换 API Key
5. **监控异常访问** - 记录认证失败的请求
6. **限流** - 对认证失败的请求进行限流

---

## FAQ

**Q: 如何添加多个 API Key？**
A: 修改 `auth.py`，将 `config.API_KEY` 改为列表：
```python
VALID_API_KEYS = ["key1", "key2", "key3"]
if api_key not in VALID_API_KEYS:
    raise HTTPException(...)
```

**Q: 如何为不同的接口配置不同的 API Key？**
A: 创建多个认证依赖函数，分别对应不同的 API Key

**Q: 如何禁用认证？**
A: 注释掉 `app.py` 中的 `@app.middleware("http")` 装饰器

**Q: WebSocket 如何认证？**
A: 在连接时通过 `extra_headers` 传递 `X-API-Key`
