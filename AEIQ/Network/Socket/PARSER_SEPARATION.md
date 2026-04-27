# 解析器分离架构设计

## 设计目标

遵循**单一职责原则**，将接收和解析职责分离到不同的类中：
- `AESocketWrapper` - 只负责 Socket 接收
- `AEPacketParser` - 只负责缓存和解析

## 架构对比

### 改进前（混合架构）

```
┌─────────────────────────────────────┐
│      AESocketWrapper               │
├─────────────────────────────────────┤
│ - socket接收                        │
│ - 接收缓冲区                        │
│ - 解析线程                          │
│ - 包头解析                          │
│ - JSON反序列化                      │
│ - 监听器通知                        │
└─────────────────────────────────────┘
```

**问题**：
- ❌ 职责过多，难以维护
- ❌ 解析逻辑与接收逻辑混合
- ❌ 难以复用解析器
- ❌ 测试困难

### 改进后（分离架构）

```
┌───────────────────┐    feed()    ┌──────────────────┐
│ AESocketWrapper   │─────────────>│ AEPacketParser   │
├───────────────────┤              ├──────────────────┤
│ - socket接收      │              │ - 接收缓冲区     │
│ - 快速喂数据      │              │ - 解析线程       │
│                   │<─────────────│ - 包头解析       │
│                   │   callback   │ - JSON反序列化   │
└───────────────────┘              └──────────────────┘
         │                                  │
         │                                  │
         └─────────> 监听器通知 <───────────┘
```

**优势**：
- ✅ 职责清晰，符合单一职责原则
- ✅ 解析器可以独立使用
- ✅ 易于测试和维护
- ✅ 可以灵活替换解析器

## 核心组件

### 1. AESocketWrapper（接收器）

**职责**：
- 管理 Socket 连接
- 快速接收数据
- 将数据喂给解析器
- 处理监听器通知

**核心方法**：
```python
class AESocketWrapper:
    def __init__(self, sock, addr, buffer_size):
        self._socket = sock
        self._parser = AEPacketParser(
            on_request_callback=self._on_request_parsed,
            on_response_callback=self._on_response_parsed,
            on_error_callback=self._on_parser_error
        )
    
    def start_receiving(self):
        """启动解析器和接收线程"""
        self._parser.start()
        # 启动接收线程...
    
    def _receive_loop(self):
        """接收循环"""
        while running:
            chunk = socket.recv(8192)
            self._parser.feed(chunk)  # 喂给解析器
    
    def _on_request_parsed(self, request):
        """解析器回调：处理请求"""
        self._notify_listeners_request(request)
    
    def _on_response_parsed(self, response):
        """解析器回调：处理响应"""
        self._notify_listeners(response)
```

**特点**：
- 📡 专注于 Socket I/O
- ⚡ 快速接收，不阻塞
- 🔌 通过回调连接解析器

### 2. AEPacketParser（解析器）

**职责**：
- 管理接收缓冲区
- 在独立线程中解析数据包
- JSON 反序列化
- 通过回调通知已解析的数据

**核心方法**：
```python
class AEPacketParser:
    def __init__(self,
                 on_request_callback,
                 on_response_callback,
                 on_error_callback,
                 buffer_size):
        self._buffer = AEReceiveBuffer(buffer_size)
        self._buffer_lock = threading.Lock()
        self._parse_thread = None
        self._data_available = threading.Event()
        # 回调函数
        self._on_request_callback = on_request_callback
        self._on_response_callback = on_response_callback
        self._on_error_callback = on_error_callback
    
    def start(self):
        """启动解析线程"""
        self._running = True
        self._parse_thread = threading.Thread(
            target=self._parse_loop,
            daemon=True
        )
        self._parse_thread.start()
    
    def feed(self, data: bytes):
        """接收数据（由外部接收线程调用）"""
        with self._buffer_lock:
            self._buffer.append(data)
        self._data_available.set()
    
    def _parse_loop(self):
        """解析线程循环"""
        while running:
            self._data_available.wait(timeout=1.0)
            self._data_available.clear()
            
            while True:
                with self._buffer_lock:
                    packet = self._buffer.try_parse_packet()
                
                if packet is None:
                    break
                
                self._handle_packet(packet)
    
    def _handle_packet(self, packet):
        """处理数据包"""
        if packet.header.data_type == REQUEST:
            request = AENetReq.from_bytes(packet.data)
            self._on_request_callback(request)
        elif packet.header.data_type == RESPONSE:
            response = AENetRsp.from_bytes(packet.data)
            self._on_response_callback(response)
```

**特点**：
- 🗄️ 管理缓冲区
- 🔄 独立解析线程
- 📦 完整的数据包处理
- 🔔 通过回调通知

## 交互流程

### 启动流程

```
1. 创建 AESocketWrapper
      ↓
2. 内部创建 AEPacketParser（注册回调）
      ↓
3. 调用 start_receiving()
      ↓
4. 启动解析器: parser.start()
      ↓
5. 启动接收线程: receive_thread.start()
      ↓
   准备就绪
```

### 数据流

```
网络数据
   ↓
socket.recv() ─────────┐
   ↓                   │
AESocketWrapper        │ 接收线程
   ↓                   │
parser.feed(chunk) ────┘
   ↓
┌──────────────────────┐
│ AEPacketParser       │
│   ↓                  │
│ buffer.append(chunk) │ 加锁
│   ↓                  │
│ signal.set()         │ 通知
│                      │
│ ┌──────────────────┐ │
│ │ 解析线程         │ │
│ │   ↓              │ │
│ │ wait(signal)     │ │
│ │   ↓              │ │
│ │ try_parse()      │ │ 加锁
│ │   ↓              │ │
│ │ from_bytes()     │ │ JSON反序列化
│ │   ↓              │ │
│ │ callback()       │ │ 通知
│ └──────────────────┘ │
└──────────────────────┘
   ↓
AESocketWrapper._on_request_parsed()
   ↓
_notify_listeners_request()
   ↓
AESocketListener.on_request_received()
   ↓
业务层处理
```

### 关闭流程

```
1. wrapper.close()
      ↓
2. parser.stop() ───> 停止解析线程
      ↓
3. socket.close() ──> 中断接收
      ↓
4. 等待线程结束
      ↓
   清理完成
```

## 接口设计

### AESocketWrapper 对外接口

```python
# 创建
wrapper = AESocketWrapper(socket, addr, buffer_size=10MB)

# 启动
wrapper.start_receiving()

# 发送
wrapper.send(request)
wrapper.send_response(response)
wrapper.send_heartbeat()
wrapper.send_ping()

# 监听
wrapper.add_listener(listener)
wrapper.remove_listener(listener)

# 关闭
wrapper.close()
```

### AEPacketParser 对外接口

```python
# 创建
parser = AEPacketParser(
    on_request_callback=on_request,
    on_response_callback=on_response,
    on_error_callback=on_error,
    buffer_size=10MB
)

# 启动
parser.start()

# 喂数据
parser.feed(chunk)

# 关闭
parser.stop()

# 查询状态
is_running = parser.is_running
buffer_size = parser.buffer_size
```

## 独立使用解析器

解析器可以脱离 Socket 独立使用：

```python
from AEIQ.Network.Socket import AEPacketParser

# 场景1: 从文件读取数据包
def on_request(request):
    print(f"Parsed request: {request.action}")

parser = AEPacketParser(on_request_callback=on_request)
parser.start()

with open('packets.bin', 'rb') as f:
    while True:
        chunk = f.read(8192)
        if not chunk:
            break
        parser.feed(chunk)

parser.stop()

# 场景2: 从队列读取数据
import queue

data_queue = queue.Queue()
parser = AEPacketParser(on_request_callback=on_request)
parser.start()

while True:
    chunk = data_queue.get()
    if chunk is None:  # 结束信号
        break
    parser.feed(chunk)

parser.stop()
```

## 线程模型

### 线程分布

```
┌─────────────────────┐
│ 主线程              │
│ - 创建对象          │
│ - 注册监听器        │
│ - 发送数据          │
└─────────────────────┘

┌─────────────────────┐
│ 接收线程            │
│ (在Wrapper中)       │
│ - socket.recv()     │
│ - parser.feed()     │
└─────────────────────┘

┌─────────────────────┐
│ 解析线程            │
│ (在Parser中)        │
│ - wait(signal)      │
│ - try_parse()       │
│ - from_bytes()      │
│ - callback()        │
└─────────────────────┘

┌─────────────────────┐
│ 业务线程            │
│ (监听器回调中)      │
│ - 业务逻辑处理      │
└─────────────────────┘
```

### 线程安全

| 资源 | 保护方式 | 访问者 |
|------|----------|--------|
| `_buffer` | `_buffer_lock` | 接收线程(写) + 解析线程(读) |
| `_data_available` | Event内置 | 接收线程(set) + 解析线程(wait) |
| `_listeners` | `_lock` | 主线程(修改) + 解析线程(读) |

## 性能优势

### 1. 更清晰的职责划分

```
接收线程：专注 I/O，延迟 < 1ms
解析线程：处理逻辑，可能较慢
```

### 2. 更好的可测试性

```python
# 测试接收器
mock_parser = Mock()
wrapper = AESocketWrapper(socket)
wrapper._parser = mock_parser
# 测试接收逻辑...

# 测试解析器
parser = AEPacketParser(on_request=callback)
parser.feed(test_data)
# 验证回调...
```

### 3. 更灵活的扩展

```python
# 替换为自定义解析器
class CustomParser(AEPacketParser):
    def _handle_packet(self, packet):
        # 自定义解析逻辑
        pass

wrapper._parser = CustomParser(...)
```

## 使用示例

### 基本使用（与之前完全兼容）

```python
from AEIQ.Network.Socket import AESocketWrapper, AESocketListener

class MyListener(AESocketListener):
    def on_request_received(self, request):
        print(f"Request: {request.action}")

wrapper = AESocketWrapper(socket)
wrapper.add_listener(MyListener())
wrapper.start_receiving()

# 使用完全不变！
```

### 高级使用（访问解析器）

```python
# 可以访问解析器的状态
print(f"Buffer size: {wrapper._parser.buffer_size}")
print(f"Parser running: {wrapper._parser.is_running}")

# 可以手动停止解析器
wrapper._parser.stop()
```

## 总结

### 改进点

✅ **单一职责** - 每个类只做一件事  
✅ **松耦合** - 通过接口连接，易于替换  
✅ **可测试** - 每个组件可以独立测试  
✅ **可复用** - 解析器可以独立使用  
✅ **易维护** - 代码结构清晰  

### 适用场景

✅ 需要独立测试解析逻辑  
✅ 需要复用解析器（如从文件解析）  
✅ 需要自定义解析器  
✅ 大型项目，需要清晰的架构  

### 向后兼容

✅ 对外接口完全不变  
✅ 使用方式完全相同  
✅ 现有代码无需修改  

**这是一个优秀的架构重构！** 🎯
