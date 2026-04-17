# Context 创建 - 快速参考

## 请求格式

```bash
POST /ae/context/create
Content-Type: application/json

{
  "aedir": "/path/to/directory"
}
```

## 响应格式

```json
{
  "contextid": "ctx_a1b2c3d4e5f6g7h8"
}
```

## 完整示例

### cURL
```bash
curl -X POST http://localhost:8000/ae/context/create \
  -H "Content-Type: application/json" \
  -d '{"aedir":"/Users/test/project"}'
```

### Python
```python
import requests

response = requests.post(
    "http://localhost:8000/ae/context/create",
    json={"aedir": "/Users/test/project"}
)

session_id = response.json()["contextid"]
print(f"Session ID: {session_id}")
```

### Swift (iOS/macOS)
```swift
let url = URL(string: "http://localhost:8000/ae/context/create")!
var request = URLRequest(url: url)
request.httpMethod = "POST"
request.setValue("application/json", forHTTPHeaderField: "Content-Type")
request.httpBody = try? JSONSerialization.data(withJSONObject: ["aedir": path])

URLSession.shared.dataTask(with: request) { data, _, _ in
    if let data = data,
       let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
       let contextId = json["contextid"] as? String {
        print("Context ID: \(contextId)")
    }
}.resume()
```

## 数据流

```
Client                          Server
  │                               │
  ├─ {"aedir": "/path"}  ────────►
  │                               │
  │                            生成 ctx_xxx
  │                            创建 Context
  │                               │
  ◄─ {"contextid": "ctx_xxx"} ───┤
  │                               │
```

## Session ID 格式

- 前缀: `ctx_`
- 长度: 16 位十六进制
- 示例: `ctx_a1b2c3d4e5f6g7h8`

## Context 包含信息

```python
{
    "session_id": "ctx_xxx",
    "aedir": "/path/to/dir",
    "created_at": "2026-04-17T10:00:00",
    "updated_at": "2026-04-17T10:00:00",
    "message_count": 0,
    "cache_enabled": true
}
```

## 错误码

| 状态码 | 原因 |
|--------|------|
| 200 | 成功 |
| 400 | aedir 为空 |
| 500 | 服务器错误 |

## 测试命令

```bash
# 启动服务
uvicorn app:app --reload --port 8000

# 运行测试
python test_context_create.py

# 手动测试
curl -X POST http://localhost:8000/ae/context/create \
  -H "Content-Type: application/json" \
  -d '{"aedir":"/tmp/test"}'

# 查看所有 Context
curl http://localhost:8000/ae/contexts/stats
```

## 核心代码位置

| 文件 | 说明 |
|------|------|
| `routes/ae_context_create.py` | 创建接口 |
| `Context/AEContext.py` | Context 模型（接收 aedir） |
| `Context/AEContextManager.py` | Context 管理器 |
| `test_context_create.py` | 测试脚本 |
