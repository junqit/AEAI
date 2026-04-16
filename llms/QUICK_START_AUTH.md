# 🔐 全局 API Key 认证 - 快速使用指南

## 当前配置

✅ **认证方式**：全局中间件（app.py 第 60-102 行）
✅ **API Key**：`ae-agent-2024-fixed-key-9527`
✅ **Header 名称**：`AE-API-Key`

---

## 📝 如何使用

### 1. 启动服务

```bash
cd /Users/tianjunqi/Project/Self/Agents/Service/llms
python app.py
```

启动后会显示：
```
==================================================
Starting Agent API Service...
LLM Type: local
API Key: ae-agent-2024-fixed-key-9527
Service ready!
==================================================
```

### 2. 测试认证

运行测试脚本：
```bash
python test_auth.py
```

会自动测试：
- ✅ 健康检查（无需认证）
- ✅ API 文档（无需认证）
- ❌ 缺少 API Key（应返回 401）
- ❌ 错误的 API Key（应返回 401）
- ✅ 正确的 API Key（应返回 200）

---

## 🌐 客户端调用

### cURL

```bash
# ✅ 正确的请求
curl -X POST "http://localhost:9999/aellms/question" \
  -H "Content-Type: application/json" \
  -H "AE-API-Key: ae-agent-2024-fixed-key-9527" \
  -d '{
    "messages": [{"role": "user", "content": "你好"}],
    "llm_type": "claude"
  }'

# ❌ 缺少 API Key
curl -X POST "http://localhost:9999/aellms/question" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "你好"}]}'
# 返回: {"detail":"Missing AE-API-Key header","error":"unauthorized"}
```

### Python

```python
import requests

headers = {
    "Content-Type": "application/json",
    "AE-API-Key": "ae-agent-2024-fixed-key-9527"
}

response = requests.post(
    "http://localhost:9999/aellms/question",
    headers=headers,
    json={
        "messages": [{"role": "user", "content": "你好"}],
        "llm_type": "claude"
    }
)

print(response.json())
```

### JavaScript

```javascript
fetch("http://localhost:9999/aellms/question", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "AE-API-Key": "ae-agent-2024-fixed-key-9527"
  },
  body: JSON.stringify({
    messages: [{role: "user", content: "你好"}],
    llm_type: "claude"
  })
})
.then(res => res.json())
.then(data => console.log(data));
```

---

## ⚙️ 配置修改

### 修改 API Key

**方式 1：环境变量（推荐）**
```bash
export API_KEY="your-new-key-here"
python app.py
```

**方式 2：修改 config.py**
```python
# config.py 第 46 行
API_KEY: str = os.getenv("API_KEY", "your-new-key-here")
```

### 修改 Header 名称

修改 `config.py` 第 47 行：
```python
API_KEY_HEADER: str = "Your-Custom-Header"
```

### 添加/移除排除路径

修改 `app.py` 第 67-73 行：
```python
excluded_paths = [
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/",
    "/your-custom-path"  # 添加新的排除路径
]
```

---

## 🔍 排除路径（不需要认证）

当前排除的路径：
- `/` - 根路径
- `/health` - 健康检查
- `/docs` - Swagger UI 文档
- `/redoc` - ReDoc 文档
- `/openapi.json` - OpenAPI Schema

其他所有路径都需要 API Key 认证！

---

## ❓ 常见问题

**Q: 如何临时禁用认证（开发测试）？**

注释掉 `app.py` 的中间件：
```python
# @app.middleware("http")
# async def api_key_middleware(request: Request, call_next):
#     ...
```

**Q: 返回 401 Unauthorized 怎么办？**

检查：
1. Header 名称是否正确：`AE-API-Key`
2. API Key 是否正确：`ae-agent-2024-fixed-key-9527`
3. Header 是否在请求中发送

**Q: 如何支持多个 API Key？**

修改 `app.py` 第 91 行：
```python
VALID_KEYS = ["key1", "key2", "key3"]
if api_key not in VALID_KEYS:
    return JSONResponse(...)
```

---

## 📊 认证流程

```
客户端请求
    ↓
全局中间件拦截
    ↓
检查路径是否在排除列表？
    ├─ 是 → 直接放行
    └─ 否 → 验证 API Key
            ├─ 缺少 → 401 Unauthorized
            ├─ 错误 → 401 Unauthorized
            └─ 正确 → 继续处理请求
                    ↓
                路由处理
                    ↓
                返回响应
```

---

## 📁 相关文件

- `app.py` (60-102 行) - 全局认证中间件
- `config.py` (46-47 行) - API Key 配置
- `auth.py` - 认证依赖函数（备用）
- `test_auth.py` - 测试脚本

---

## 🚀 快速测试

```bash
# 1. 启动服务
python app.py

# 2. 新开终端，运行测试
python test_auth.py

# 3. 手动测试
curl -H "AE-API-Key: ae-agent-2024-fixed-key-9527" http://localhost:9999/aellms/question -X POST -d '...'
```
