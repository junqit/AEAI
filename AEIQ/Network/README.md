# UDP Socket 服务器

基于 UDP 协议的 Socket 服务器，支持接收和响应 JSON 格式数据。

## 功能特性

- ✅ UDP Socket 通信
- ✅ JSON 数据格式支持
- ✅ 多线程并发处理
- ✅ 可扩展的消息处理器
- ✅ 与 FastAPI 应用集成
- ✅ 完整的日志记录

## 目录结构

```
Network/
├── __init__.py              # 模块初始化
├── udp_server.py            # UDP 服务器核心类
├── message_handler.py       # 消息处理器
├── start_udp_server.py      # 启动脚本
├── example_server.py        # 服务端示例
└── README.md                # 本文档
```

## 快速开始

### 1. 启动服务器

```bash
cd /Users/tianjunqi/Project/Self/Agents/Service/agent_one/Network
python start_udp_server.py
```

服务器将在 `0.0.0.0:9999` 上监听 UDP 请求。

### 2. 基本使用

```python
from Network import UDPServer, MessageHandler

# 创建消息处理器
handler = MessageHandler()

# 创建服务器
server = UDPServer(host="0.0.0.0", port=9999)
server.set_message_handler(handler.handle)

# 启动服务器
server.start()
```

## 消息格式

### 请求格式

所有请求必须是 JSON 格式，包含 `type` 字段：

```json
{
  "type": "消息类型",
  "其他字段": "..."
}
```

### 支持的消息类型

#### 1. Ping 测试

**请求：**
```json
{
  "type": "ping",
  "timestamp": "2026-04-09T10:00:00"
}
```

**响应：**
```json
{
  "status": "success",
  "type": "pong",
  "message": "Server is alive",
  "timestamp": "2026-04-09T10:00:01"
}
```

#### 2. 聊天消息

**请求：**
```json
{
  "type": "chat",
  "message": "你好",
  "context_id": "user_123"
}
```

**响应：**
```json
{
  "status": "success",
  "type": "chat_response",
  "message": "Received: 你好",
  "context_id": "user_123",
  "timestamp": "2026-04-09T10:00:02"
}
```

#### 3. 上下文操作

**请求：**
```json
{
  "type": "context",
  "action": "get",
  "context_id": "user_123",
  "data": {}
}
```

**响应：**
```json
{
  "status": "success",
  "type": "context_response",
  "action": "get",
  "context_id": "user_123",
  "timestamp": "2026-04-09T10:00:03"
}
```

#### 4. 自定义消息

**请求：**
```json
{
  "type": "custom",
  "data": {
    "自定义字段": "自定义值"
  }
}
```

## 与 FastAPI 集成

服务器可以与现有的 FastAPI 应用集成：

```python
from app import context_manager
from Network import UDPServer, MessageHandler

# 创建带 Context Manager 的处理器
handler = MessageHandler(context_manager=context_manager)

# 创建并启动服务器
server = UDPServer()
server.set_message_handler(handler.handle)
server.start()
```

## 自定义消息处理器

您可以扩展 `MessageHandler` 类来添加自定义逻辑：

```python
from Network import MessageHandler

class CustomHandler(MessageHandler):
    def _handle_custom(self, data):
        # 自定义处理逻辑
        result = self.process_custom_logic(data)
        return {
            "status": "success",
            "result": result
        }
```

## 配置选项

### UDPServer 参数

- `host`: 绑定的主机地址，默认 `"0.0.0.0"`
- `port`: 绑定的端口，默认 `9999`
- `buffer_size`: 接收缓冲区大小（字节），默认 `4096`

### 修改端口和地址

```python
server = UDPServer(
    host="127.0.0.1",  # 只监听本地
    port=8888,          # 使用 8888 端口
    buffer_size=8192    # 8KB 缓冲区
)
```

## 错误处理

服务器会自动捕获和处理错误，返回错误响应：

```json
{
  "status": "error",
  "message": "错误描述",
  "timestamp": "2026-04-09T10:00:04"
}
```

## 日志

服务器使用 Python 的 `logging` 模块，日志级别为 `INFO`。

查看日志输出示例：
```
2026-04-09 10:00:00 - __main__ - INFO - UDP 服务器启动成功: 0.0.0.0:9999
2026-04-09 10:00:01 - __main__ - INFO - 收到来自 ('127.0.0.1', 54321) 的消息: {'type': 'ping'}
2026-04-09 10:00:01 - __main__ - INFO - 已发送响应到 ('127.0.0.1', 54321)
```

## 安全建议

1. **生产环境**：不要绑定到 `0.0.0.0`，指定具体的内网 IP
2. **防火墙**：配置防火墙规则限制访问来源
3. **数据验证**：在 `MessageHandler` 中添加数据验证逻辑
4. **大小限制**：根据实际需求调整 `buffer_size`

## 故障排查

### 端口被占用

```bash
# 查看端口占用
lsof -i :9999

# 或使用 netstat
netstat -an | grep 9999
```

### 防火墙问题

```bash
# macOS 检查防火墙
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
```

## 性能优化

1. **并发处理**：每个消息在独立线程中处理，避免阻塞
2. **缓冲区大小**：根据消息大小调整 `buffer_size`
3. **超时设置**：客户端应设置合理的超时时间

## 相关文档

- [客户端文档](../../../Client/CocoaPods/AENetworkEngine/Socket/UDP/README.md)
- [FastAPI 集成指南](../README.md)
