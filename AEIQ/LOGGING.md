# 日志系统使用指南

## 📋 概述

项目已集成完整的日志系统，涵盖所有关键步骤和错误场景，便于调试和监控。

---

## 🎯 日志级别

| 级别 | 符号 | 用途 | 示例 |
|------|------|------|------|
| **DEBUG** | 🔍 | 详细调试信息 | 请求参数、响应内容预览 |
| **INFO** | ℹ️ | 关键步骤和状态 | 初始化、开始处理、调用成功 |
| **WARNING** | ⚠️ | 警告信息 | QuestionCache 未启用 |
| **ERROR** | ❌ | 错误信息 | HTTP 请求失败、LLM 调用异常 |
| **CRITICAL** | 🚨 | 严重错误 | 系统级错误 |

---

## 📊 日志格式

```
2026-04-13 10:30:45 - AEContext - INFO - [AEContext.py:45] - 🚀 初始化 AEContext - session_id=user123, enable_cache=True
```

格式说明：
- `时间戳` - 精确到秒
- `模块名` - 日志来源
- `级别` - 日志级别
- `文件:行号` - 代码位置
- `消息` - 日志内容（带表情符号便于识别）

---

## 🔍 关键日志点

### 1. AEContext 初始化
```
🚀 初始化 AEContext - session_id=user123, enable_cache=True, llm_service_url=http://localhost:9999
✅ 线程池已创建 - max_workers=5
✅ QuestionCache 已启用 - session_id=user123
❌ QuestionCache 初始化失败 - session_id=user123, error=...
```

### 2. 接收用户消息
```
📥 收到用户消息 - session_id=user123, user_input_length=50, llm_types=['claude', 'gemini']
📝 用户输入内容: 什么是Python？...
✅ 用户消息已记录 - session_id=user123, total_messages=3
```

### 3. 并行调用 LLM
```
🔄 开始并行调用 2 个 LLM - session_id=user123
🔄 开始调用 LLM - session_id=user123, llm_type=claude
📦 准备请求参数 - session_id=user123, llm_type=claude, messages_count=5
📤 发送 HTTP 请求 - session_id=user123, llm_type=claude, url=http://localhost:9999/aellms/question
```

### 4. HTTP 响应
```
📥 收到 HTTP 响应 - session_id=user123, llm_type=claude, status_code=200, elapsed=1.23s
✅ LLM 调用成功 - session_id=user123, llm_type=claude, elapsed=1.23s, response_length=1500
```

### 5. 错误场景
```
❌ HTTP 请求超时 - session_id=user123, llm_type=claude, elapsed=30.00s
❌ 连接错误 - session_id=user123, llm_type=claude, elapsed=0.50s, error=Connection refused
❌ HTTP 错误 - session_id=user123, llm_type=claude, status_code=500, elapsed=2.00s
❌ 未知错误 - session_id=user123, llm_type=claude, elapsed=1.00s, error=...
```

### 6. 处理结果统计
```
📊 处理结果统计 - session_id=user123, success=2, error=0, total=2
```

### 7. Question 路由
```
📥 [Request-1713001845.123] 收到 question 请求 - llm_type=claude, level=high, messages_count=3
🔄 [Request-1713001845.123] 开始处理 - LLM=claude, level=high
🚀 [Request-1713001845.123] 调用 LLM - llm_type=claude
✅ [Request-1713001845.123] LLM 调用成功 - llm_type=claude, elapsed=1.50s, response_length=2000
❌ [Request-1713001845.123] LLM 调用失败 - llm_type=claude, elapsed=2.00s, error=...
```

---

## 🛠️ 使用日志

### 方式1: 查看控制台输出

运行服务后，日志会实时输出到控制台：

```bash
python main.py
```

### 方式2: 查看日志文件

日志文件保存在 `AEIQ/logs/` 目录下：

```bash
# 查看最新日志
tail -f AEIQ/logs/AEContext_20260413.log

# 搜索错误日志
grep "❌" AEIQ/logs/AEContext_20260413.log

# 搜索特定 session
grep "session_id=user123" AEIQ/logs/AEContext_20260413.log
```

### 方式3: 使用日志配置模块

```python
from AEIQ.logging_config import get_logger

# 获取日志记录器
logger = get_logger("my_module")

# 记录日志
logger.info("这是一条信息")
logger.error("这是一个错误")
```

---

## 📈 日志分析示例

### 1. 统计成功率

```bash
# 统计成功和失败的请求数
grep "✅ LLM 调用成功" logs/AEContext_*.log | wc -l
grep "❌" logs/AEContext_*.log | wc -l
```

### 2. 查看响应时间

```bash
# 查看所有响应时间
grep "elapsed=" logs/AEContext_*.log | grep -oP "elapsed=\K[0-9.]+"
```

### 3. 错误分析

```bash
# 按错误类型统计
grep "❌" logs/AEContext_*.log | cut -d'-' -f5 | sort | uniq -c | sort -rn
```

### 4. 会话追踪

```bash
# 追踪某个会话的完整流程
grep "session_id=user123" logs/AEContext_*.log
```

---

## 🎨 日志符号说明

| 符号 | 含义 |
|------|------|
| 🚀 | 初始化/启动 |
| 📥 | 接收/输入 |
| 📤 | 发送/输出 |
| 🔄 | 处理中/进行中 |
| ✅ | 成功 |
| ❌ | 失败/错误 |
| ⚠️ | 警告 |
| 📊 | 统计/统计信息 |
| 📚 | 历史/记录 |
| 🗑️ | 删除/清理 |
| 🧹 | 清理资源 |
| 🔍 | 查询/搜索 |
| 📝 | 内容/详情 |
| 📦 | 准备/打包 |
| 📋 | 请求详情 |

---

## ⚙️ 配置日志级别

### 方式1: 代码中配置

```python
import logging

# 设置为 DEBUG 级别（显示所有日志）
logging.getLogger().setLevel(logging.DEBUG)

# 只显示 WARNING 及以上级别
logging.getLogger().setLevel(logging.WARNING)
```

### 方式2: 使用环境变量

```bash
# 在启动服务前设置
export LOG_LEVEL=DEBUG
python main.py
```

### 方式3: 修改 logging_config.py

```python
# 在 logging_config.py 中修改
DEFAULT_LOG_LEVEL = logging.DEBUG  # 改为 DEBUG
```

---

## 🔧 调试技巧

### 1. 开启 DEBUG 日志

```python
import logging
logging.getLogger("AEContext").setLevel(logging.DEBUG)
```

这会显示：
- 请求参数详情
- 响应内容预览
- QuestionCache 操作详情

### 2. 过滤特定日志

```python
# 只看错误日志
grep "❌" logs/*.log

# 只看成功日志
grep "✅" logs/*.log

# 只看特定 LLM
grep "llm_type=claude" logs/*.log
```

### 3. 实时监控

```bash
# 实时查看日志并高亮错误
tail -f logs/AEContext_*.log | grep --color=always -E "❌|$"
```

---

## 📊 日志文件管理

### 自动轮转

日志文件会自动轮转：
- 单个文件最大 10MB
- 保留最近 5 个文件
- 按日期命名：`AEContext_20260413.log`

### 清理旧日志

```bash
# 删除 7 天前的日志
find logs/ -name "*.log" -mtime +7 -delete
```

---

## 🚨 重要错误场景

### 1. LLM 服务不可用
```
❌ 连接错误 - session_id=user123, llm_type=claude, url=http://localhost:9999
```
**解决**: 检查 LLM 服务是否启动，端口是否正确

### 2. 请求超时
```
❌ 请求超时 - session_id=user123, llm_type=claude, timeout=30s
```
**解决**: 增加超时时间或检查网络

### 3. HTTP 5xx 错误
```
❌ HTTP 错误 - session_id=user123, llm_type=claude, status_code=500
```
**解决**: 查看 LLM 服务的日志，检查是否有错误

### 4. 参数错误
```
❌ 不支持的 LLM 类型: unknown_llm
```
**解决**: 检查传入的 llm_type 参数

---

## 📝 最佳实践

1. **开发环境**: 使用 `DEBUG` 级别，查看详细信息
2. **生产环境**: 使用 `INFO` 级别，减少日志量
3. **错误追踪**: 使用 `session_id` 和 `request_id` 追踪完整流程
4. **定期清理**: 定期清理旧日志文件，避免占用过多磁盘空间
5. **监控告警**: 监控错误日志，设置告警阈值

---

## 🔗 相关文件

- `AEIQ/Context/AEContext.py` - Context 日志实现
- `llms/routes/question.py` - Question 路由日志实现
- `AEIQ/logging_config.py` - 日志配置模块
- `AEIQ/logs/` - 日志文件目录
