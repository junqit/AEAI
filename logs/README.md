# 日志文件目录

这个目录存放系统运行时生成的日志文件。

## 日志文件

### 开发测试日志
- **test_debug.log** - 测试脚本的详细日志（DEBUG级别）
  - 包含所有组件的详细执行信息
  - 适用于问题排查和调试

### 生产环境日志
- **agent.log** - Agent API 服务的运行日志（INFO级别）
  - 启动 FastAPI 服务时自动生成
  - 包含关键路径和性能指标
  - 适用于生产环境监控

## 日志配置

日志系统位于 `utils/logger.py`，支持以下配置：

### 日志级别
- **DEBUG** - 显示所有详细信息（开发调试）
- **INFO** - 显示关键信息（生产推荐）
- **WARNING** - 只显示警告和错误
- **ERROR** - 只显示错误

### 配置方式

```python
from utils.logger import setup_logging

# 控制台输出（带彩色）
setup_logging(level="DEBUG")

# 同时输出到文件（无颜色代码）
setup_logging(level="INFO", log_file="logs/agent.log")
```

## 日志特性

✅ **控制台输出** - 带颜色，易于阅读
✅ **文件输出** - 纯文本，无颜色代码
✅ **全链路追踪** - Trace ID 关联所有操作
✅ **性能监控** - 自动记录执行时间
✅ **结构化日志** - 带元数据的 JSON 风格
✅ **组件标识** - [Orchestrator]/[Router]/[MCPSkill] 等

## 日志格式

```
时间戳 | 级别 | [组件] [trace:xxx] 消息 (参数=值)
```

示例：
```
2026-03-29 18:52:21 | INFO | [Router] ✅ 成功 路由决策 (elapsed_ms=0.13ms, method=规则路由, strategy=mcp)
```

## 日志轮转（建议）

生产环境建议配置日志轮转，避免日志文件过大：

```bash
# 使用 logrotate 或定期清理
find logs/ -name "*.log" -mtime +7 -delete  # 删除7天前的日志
```

## 查看日志

```bash
# 实时查看日志
tail -f logs/agent.log

# 查看最近100行
tail -100 logs/agent.log

# 搜索错误
grep ERROR logs/agent.log

# 查看某个组件的日志
grep "\[MCPSkill\]" logs/agent.log

# 查看某个trace的完整链路
grep "trace:trace_06" logs/test_debug.log
```

## 日志分析

参考 `LOGGING_GUIDE.md` 获取完整的日志使用指南。
