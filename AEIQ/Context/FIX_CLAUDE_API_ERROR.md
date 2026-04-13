# 修复：Claude API Extra inputs 错误

## 🐛 问题描述

### 错误信息
```
messages.0.timestamp: Extra inputs are not permitted
```

### 错误原因
`AEContext.py` 在存储消息时添加了 `timestamp` 字段：
```python
self.messages.append({
    "role": "user",
    "content": user_input,
    "timestamp": datetime.now().isoformat()  # ❌ Claude API 不接受这个字段
})
```

然后直接将 `self.messages` 发送给 Claude API：
```python
payload = {
    "messages": self.messages,  # ❌ 包含了 timestamp 字段
    ...
}
```

但 Claude API 只接受包含 `role` 和 `content` 的标准格式消息。

---

## ✅ 解决方案

### 修改前
```python
def _process_single_llm(self, user_input: str, llm_type: str):
    payload = {
        "messages": self.messages,  # ❌ 直接使用，包含 timestamp
        "llm_type": llm_type,
        "level": "high"
    }
```

### 修改后
```python
def _process_single_llm(self, user_input: str, llm_type: str):
    # 清理 messages，只保留 role 和 content 字段
    clean_messages = []
    for msg in self.messages:
        clean_msg = {
            "role": msg.get("role"),
            "content": msg.get("content")
        }
        clean_messages.append(clean_msg)

    payload = {
        "messages": clean_messages,  # ✅ 使用清理后的 messages
        "llm_type": llm_type,
        "level": "high"
    }
```

---

## 📊 数据流说明

### 内部存储格式（self.messages）
```python
[
    {
        "role": "user",
        "content": "什么是 Python？",
        "timestamp": "2026-04-13T15:55:00"  # 用于内部追踪
    },
    {
        "role": "assistant",
        "content": "Python 是...",
        "timestamp": "2026-04-13T15:55:02"
    }
]
```

### 发送给 Claude API 的格式（clean_messages）
```python
[
    {
        "role": "user",
        "content": "什么是 Python？"  # 只保留 role 和 content
    },
    {
        "role": "assistant",
        "content": "Python 是..."
    }
]
```

---

## 🔍 Claude API 支持的字段

根据 [Claude API 文档](https://docs.anthropic.com/claude/reference/messages_post)：

### Messages 格式
```json
{
  "model": "claude-3-opus-20240229",
  "max_tokens": 1024,
  "messages": [
    {
      "role": "user",      // ✅ 必需
      "content": "..."     // ✅ 必需
    }
  ],
  "system": "...",         // ✅ 可选
  "tools": [...]           // ✅ 可选
}
```

### ❌ 不支持的字段
- `timestamp`
- `id`
- `metadata`
- 任何其他自定义字段

### ✅ 支持的顶层字段
- `model` - 模型名称（必需）
- `messages` - 消息列表（必需）
- `max_tokens` - 最大 token 数（必需）
- `system` - 系统提示词（可选）
- `tools` - 工具列表（可选）
- `temperature` - 温度参数（可选）
- `top_p` - top-p 参数（可选）
- `top_k` - top-k 参数（可选）
- `metadata` - 请求元数据（可选）
- `stop_sequences` - 停止序列（可选）
- `stream` - 是否流式输出（可选）

---

## 🧪 测试

### 测试清理功能
```python
# 模拟存储的消息（包含 timestamp）
messages_with_timestamp = [
    {
        "role": "user",
        "content": "Hello",
        "timestamp": "2026-04-13T15:55:00"
    }
]

# 清理后的消息
clean_messages = []
for msg in messages_with_timestamp:
    clean_msg = {
        "role": msg.get("role"),
        "content": msg.get("content")
    }
    clean_messages.append(clean_msg)

# 结果
print(clean_messages)
# [{"role": "user", "content": "Hello"}]
```

---

## 📝 相关文件

- `/AEIQ/Context/AEContext.py` - 修复了消息清理逻辑

---

## ✅ 验证

修复后，应该能够正常调用 Claude API，不再出现 "Extra inputs are not permitted" 错误。

---

## 🔗 相关资源

- [Claude API Messages 文档](https://docs.anthropic.com/claude/reference/messages_post)
- [Claude API 错误代码](https://docs.anthropic.com/claude/reference/errors)
