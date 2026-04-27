## 新包头结构实现文档

## 概述

实现了完善的网络数据包协议，包含：
1. **包头结构**：魔数、版本、数据类型、长度、校验和
2. **接收缓冲区**：处理粘包和半包问题
3. **自动解析**：根据包头自动解析数据为 AENetReq 或 AENetRsp
4. **业务层通知**：通过 AESocketListener 传递给业务层

## 包结构设计

### 完整包格式

```
┌─────────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
│ Magic Code  │ Version  │ DataType │  Length  │ Checksum │   Data   │
│   (4 bytes) │ (2 bytes)│ (2 bytes)│ (4 bytes)│ (4 bytes)│ (N bytes)│
└─────────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
```

### 包头字段说明

| 字段 | 大小 | 说明 | 示例 |
|------|------|------|------|
| Magic Code | 4字节 | 魔数，固定为 0x41454951 ('AEIQ') | 识别协议 |
| Version | 2字节 | 协议版本，当前为 0x0001 | 支持版本升级 |
| DataType | 2字节 | 数据类型枚举值 | 区分请求/响应 |
| Length | 4字节 | 数据长度（不含包头） | 最大 4GB |
| Checksum | 4字节 | CRC32 校验和 | 数据完整性校验 |

**总包头长度：16 字节**

### 数据类型 (AEDataType)

```python
class AEDataType(Enum):
    REQUEST = 0x0001    # 请求数据 (AENetReq)
    RESPONSE = 0x0002   # 响应数据 (AENetRsp)
    HEARTBEAT = 0x0003  # 心跳包
    PING = 0x0004       # Ping
    PONG = 0x0005       # Pong
    CUSTOM = 0x00FF     # 自定义数据
```

## 核心组件

### 1. AEPacketHeader - 包头

```python
from AEIQ.Network.Socket import AEPacketHeader, MAGIC_CODE, PROTOCOL_VERSION

# 创建包头
header = AEPacketHeader(
    magic_code=MAGIC_CODE,      # 自动填充
    version=PROTOCOL_VERSION,   # 自动填充
    data_type=0x0001,
    length=100,
    checksum=0x12345678
)

# 序列化为字节流
header_bytes = header.to_bytes()  # 16 字节

# 从字节流解析
header = AEPacketHeader.from_bytes(header_bytes)

# 验证数据完整性
is_valid = header.validate(data_bytes)
```

### 2. AEPacket - 完整数据包

```python
from AEIQ.Network.Socket import AEPacket, AEDataType

# 创建数据包
data = b'Hello, World!'
packet = AEPacket.create(AEDataType.REQUEST, data)

# 序列化为字节流（包头 + 数据）
packet_bytes = packet.to_bytes()

# 从字节流解析
header = AEPacketHeader.from_bytes(packet_bytes)
data_bytes = packet_bytes[16:16+header.length]
packet = AEPacket.from_bytes(header, data_bytes)
```

### 3. AEReceiveBuffer - 接收缓冲区

```python
from AEIQ.Network.Socket.AEReceiveBuffer import AEReceiveBuffer

# 创建缓冲区
buffer = AEReceiveBuffer(max_buffer_size=10*1024*1024)

# 追加接收到的数据
buffer.append(recv_data)

# 尝试解析完整数据包
packet = buffer.try_parse_packet()
if packet:
    # 处理数据包
    process(packet)
else:
    # 数据不完整，继续接收
    pass
```

**缓冲区特性：**
- ✅ 自动处理粘包（多个包合并接收）
- ✅ 自动处理半包（数据分批接收）
- ✅ 错误恢复（查找下一个有效魔数）
- ✅ 溢出保护（防止内存溢出）

### 4. 改进的 AESocketWrapper

#### 接收流程

```python
def _receive_loop(self):
    """
    接收流程：
    1. 从 socket 接收数据（8KB 块）
    2. 追加到缓冲区
    3. 循环尝试解析完整数据包
    4. 根据数据类型解析为 AENetReq 或 AENetRsp
    5. 通过监听器通知业务层
    """
```

**处理粘包示例：**
```
接收缓冲区: [包1][包2][包3的一半]

循环解析:
  - 解析包1 ✓ → 通知监听器
  - 解析包2 ✓ → 通知监听器
  - 尝试解析包3 ✗ → 等待更多数据
```

**处理半包示例：**
```
第一次接收: [包头前10字节]
  → 无法解析，保留在缓冲区

第二次接收: [包头后6字节][数据前50字节]
  → 包头完整，但数据不完整，继续等待

第三次接收: [数据剩余部分]
  → 数据完整 ✓ → 解析并通知监听器
```

#### 发送方法

```python
# 发送请求（默认类型为 REQUEST）
wrapper.send(request)

# 发送响应
wrapper.send_response(response)

# 发送心跳
wrapper.send_heartbeat()

# 发送 Ping
wrapper.send_ping()
```

### 5. 更新的 AESocketListener

```python
class MyListener(AESocketListener):
    """业务监听器"""

    def on_request_received(self, request: AENetReq):
        """接收到请求（服务端实现）"""
        print(f"收到请求: {request.action}")
        # 处理业务逻辑

    def on_data_received(self, response: AENetRsp):
        """接收到响应（客户端实现）"""
        print(f"收到响应: {response.status}")
        # 处理业务逻辑

    def on_connection_closed(self):
        """连接关闭"""
        pass

    def on_error(self, error: Exception):
        """发生错误"""
        pass
```

## 使用示例

### 服务端

```python
import socket
from AEIQ.Network.Socket import AESocketWrapper, AESocketListener
from AEIQ.Network.Core import AENetReq, AENetRsp, AENetRspData

class ServerListener(AESocketListener):
    def __init__(self, wrapper):
        self.wrapper = wrapper

    def on_request_received(self, request: AENetReq):
        """接收到客户端请求"""
        print(f"收到请求: {request.action}")

        # 处理请求并发送响应
        response = AENetRsp.create_success(
            data=AENetRspData(content="处理成功"),
            request_id=request.request_id
        )
        self.wrapper.send_response(response)

# 创建服务端
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(('localhost', 8888))
server_socket.listen(1)

# 接受连接
client_sock, addr = server_socket.accept()

# 创建包装器
wrapper = AESocketWrapper(client_sock, addr)
wrapper.add_listener(ServerListener(wrapper))
wrapper.start_receiving()

# 保持运行...
```

### 客户端

```python
import socket
from AEIQ.Network.Socket import AESocketWrapper, AESocketListener
from AEIQ.Network.Core import AENetReq, AENetReqAction, AENetReqData

class ClientListener(AESocketListener):
    def on_data_received(self, response: AENetRsp):
        """接收到服务端响应"""
        print(f"收到响应: {response.status}")
        if response.is_success:
            print(f"数据: {response.data}")

# 连接到服务端
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect(('localhost', 8888))

# 创建包装器
wrapper = AESocketWrapper(client_socket)
wrapper.add_listener(ClientListener())
wrapper.start_receiving()

# 发送请求
request = AENetReq(
    action=AENetReqAction.CHAT,
    data=AENetReqData(content="Hello"),
    request_id="req_001"
)
wrapper.send(request)
```

## 协议特性

### 1. 魔数识别
- 防止接收到错误的数据流
- 快速识别有效数据包
- 支持错误恢复（查找下一个魔数）

### 2. 版本控制
- 支持协议升级
- 向后兼容性检查
- 未来可扩展

### 3. 数据类型
- 明确区分请求和响应
- 支持心跳和 Ping/Pong
- 可扩展自定义类型

### 4. 长度字段
- 明确数据边界
- 避免粘包问题
- 支持大数据传输（最大 4GB）

### 5. 校验和
- CRC32 算法
- 检测数据损坏
- 保证数据完整性

## 对比旧版本

| 特性 | 旧版本 | 新版本 |
|------|--------|--------|
| 包头大小 | 4字节（仅长度） | 16字节（完整信息） |
| 协议识别 | 无 | ✅ 魔数 |
| 版本控制 | 无 | ✅ 版本字段 |
| 数据类型 | 无区分 | ✅ 类型枚举 |
| 数据校验 | 无 | ✅ CRC32 |
| 粘包处理 | 手动 | ✅ 自动 |
| 半包处理 | 手动 | ✅ 自动 |
| 错误恢复 | 无 | ✅ 魔数搜索 |
| 心跳支持 | 无 | ✅ 内置 |

## 测试

### 运行测试

```bash
# 测试数据包功能
python -m unittest AEIQ.Network.Socket.test_packet -v

# 运行示例
python -m AEIQ.Network.Socket.example_new_protocol server  # 服务端
python -m AEIQ.Network.Socket.example_new_protocol client  # 客户端
```

### 测试覆盖

- ✅ 包头序列化/反序列化
- ✅ 魔数验证
- ✅ 数据包创建和解析
- ✅ CRC32 校验
- ✅ 缓冲区管理
- ✅ 粘包处理
- ✅ 半包处理
- ✅ 溢出保护
- ✅ 错误恢复

## 性能考虑

### 内存使用
- 默认缓冲区：10MB
- 可配置大小
- 自动清理已处理数据

### CPU 开销
- CRC32 计算：快速（硬件加速）
- 包头解析：O(1) 时间复杂度
- 缓冲区查找：最坏 O(n)，平均 O(1)

### 网络效率
- 包头开销：16字节 / 每包
- 无额外往返延迟
- 支持批量发送

## 安全考虑

### 1. 缓冲区溢出保护
```python
buffer = AEReceiveBuffer(max_buffer_size=10*1024*1024)
# 超过限制会抛出 OverflowError
```

### 2. 无效数据处理
- 魔数验证失败 → 跳过无效数据
- 校验和失败 → 丢弃数据包
- 长度异常 → 拒绝处理

### 3. DOS 防护
- 限制单包大小
- 限制缓冲区大小
- 超时机制（可选）

## 最佳实践

### 1. 错误处理

```python
try:
    wrapper.send(request)
except Exception as e:
    logger.error(f"发送失败: {e}")
    # 处理错误
```

### 2. 心跳保活

```python
# 定期发送心跳
import threading

def heartbeat_thread():
    while wrapper.is_connected:
        wrapper.send_heartbeat()
        time.sleep(30)

threading.Thread(target=heartbeat_thread, daemon=True).start()
```

### 3. 请求超时

```python
import asyncio

async def send_with_timeout(wrapper, request, timeout=10):
    # 发送请求
    wrapper.send(request)

    # 等待响应（需要配合响应匹配机制）
    response = await asyncio.wait_for(
        wait_for_response(request.request_id),
        timeout=timeout
    )
    return response
```

## 总结

新的包头结构实现提供了：
- ✅ 完善的协议设计
- ✅ 自动的数据解析
- ✅ 健壮的错误处理
- ✅ 灵活的扩展性
- ✅ 高性能的实现

所有数据通过包头自动识别和解析，业务层只需实现监听器接口，无需关心底层细节。
