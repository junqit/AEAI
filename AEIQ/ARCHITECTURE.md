# 分层架构设计文档

## 架构概览

```
┌─────────────────────────────────────────────┐
│              Application Layer              │
│                  (app.py)                   │
│         组装层 - 依赖注入与连接              │
└─────────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌──────────────┐          ┌──────────────┐
│ Network Layer│          │Business Layer│
│              │◄────────►│              │
│SocketManager │          │ContextMgr   │
└──────────────┘          └──────────────┘
```

## 层次划分

### 1. 网络层（Network Layer）
**位置**: `AEIQ/Network/Socket/`

**职责**:
- 管理 Socket 连接
- 接收和解析网络数据包
- 发送响应到客户端
- 连接生命周期管理

**核心组件**:
- `SocketServer`: UDP 服务器
- `SocketConnectionManager`: 连接管理器
- `AESocketWrapper`: Socket 包装器
- `AEPacketParser`: 数据包解析器

**暴露接口**:
- `IResponseSender`: 响应发送接口（给业务层调用）

### 2. 业务层（Business Layer）
**位置**: `AEIQ/Context/`

**职责**:
- 处理业务逻辑
- 管理 AI Context
- 调用 LLM 进行处理
- 生成业务响应

**核心组件**:
- `AEContextManager`: Context 管理器
- `AEContext`: 单个会话上下文

**实现接口**:
- `IRequestHandler`: 请求处理接口（网络层调用）

### 3. 应用层（Application Layer）
**位置**: `AEIQ/app.py`

**职责**:
- 组装各层
- 依赖注入
- 生命周期管理

## 接口定义

### IRequestHandler（请求处理器接口）
```python
class IRequestHandler(Protocol):
    def handle_request(self, request: AENetReq, connection_id: str) -> None:
        """处理请求"""
        ...
```

**实现者**: `AEContextManager`
**调用者**: `SocketConnectionManager`

### IResponseSender（响应发送器接口）
```python
class IResponseSender(Protocol):
    def send_response(self, connection_id: str, response: AENetRsp) -> bool:
        """发送响应"""
        ...
```

**实现者**: `SocketConnectionManager`
**调用者**: `AEContextManager`

## 数据流

### 请求流程
```
Client
  │
  │ UDP Packet
  ▼
SocketServer
  │
  │ Raw bytes
  ▼
AEPacketParser
  │
  │ AENetReq
  ▼
SocketConnectionManager
  │
  │ handle_request(request, connection_id)
  ▼
AEContextManager
  │
  │ Business Logic (AI Processing)
  ▼
AEContext
```

### 响应流程
```
AEContext
  │
  │ Result
  ▼
AEContextManager
  │
  │ send_response(connection_id, response)
  ▼
SocketConnectionManager
  │
  │ AENetRsp
  ▼
AESocketWrapper
  │
  │ Bytes
  ▼
Client
```

## 依赖注入

在 `app.py` 中进行依赖注入：

```python
# 1. 创建网络层
socket_server = get_socket_server(host="0.0.0.0", port=8888)

# 2. 创建业务层，注入响应发送器
ae_context_manager = AEContextManager(
    response_sender=socket_server.connection_manager
)

# 3. 将业务层处理器注册到网络层
socket_server.connection_manager.set_request_handler(ae_context_manager)
```

## 优势

### 1. 分层清晰
- 网络层：只关心通信
- 业务层：只关心业务逻辑
- 应用层：只负责组装

### 2. 低耦合
- 通过接口（Protocol）解耦
- 各层可独立测试
- 易于替换实现

### 3. 高内聚
- 每层职责单一
- 代码组织清晰
- 易于维护

### 4. 可扩展
- 可以轻松添加新的请求处理器
- 可以支持多种网络协议
- 可以添加中间件层

## 扩展点

### 添加新的请求类型
在 `AEContextManager.handle_request()` 中添加新的 path 路由：

```python
if request.path == "/ae/context/new_feature":
    self._handle_new_feature(request, connection_id)
```

### 添加中间件
可以在网络层和业务层之间添加中间件：

```python
class RequestMiddleware(IRequestHandler):
    def __init__(self, next_handler: IRequestHandler):
        self.next_handler = next_handler
    
    def handle_request(self, request, connection_id):
        # 前置处理
        self.next_handler.handle_request(request, connection_id)
        # 后置处理
```

### 支持多种协议
可以创建不同的 Server 实现（TCP、WebSocket），只要实现 `IResponseSender` 接口即可。

## 测试策略

### 单元测试
- 网络层：模拟 IRequestHandler
- 业务层：模拟 IResponseSender

### 集成测试
- 在 app.py 中组装真实对象
- 发送测试请求验证端到端流程
