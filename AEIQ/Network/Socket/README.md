# Socket 包装类使用说明

## 概述

`Socket` 目录提供了对原始 socket 连接的高级封装，实现了：

1. **数据包装**：使用 `AENetReq` 和 `AENetRsp` 进行数据封装
2. **异步接收**：在独立线程中接收数据
3. **监听器模式**：通过注册监听器处理接收到的数据
4. **线程安全**：使用锁保护共享资源

## 核心组件

### 1. AENetReq (请求包装)

位置：`AEIQ/Network/Core/AENetReq.py`

```python
from AEIQ.Network.Core import AENetReq

# 创建请求
request = AENetReq(
    action="query",              # 请求动作
    data={"key": "value"},       # 请求数据
    request_id="req_123"         # 请求ID（可选）
)

# 序列化为字节流
bytes_data = request.to_bytes()

# 从字节流反序列化
request = AENetReq.from_bytes(bytes_data)
```

### 2. AENetRsp (响应包装)

位置：`AEIQ/Network/Core/AENetRsp.py`

```python
from AEIQ.Network.Core import AENetRsp

# 创建响应
response = AENetRsp(
    success=True,                # 是否成功
    data={"result": "ok"},       # 响应数据
    error=None,                  # 错误信息（可选）
    request_id="req_123"         # 对应的请求ID（可选）
)

# 序列化为字节流
bytes_data = response.to_bytes()

# 从字节流反序列化
response = AENetRsp.from_bytes(bytes_data)
```

### 3. AESocketListener (监听器接口)

位置：`AEIQ/Network/Socket/AESocketListener.py`

```python
from AEIQ.Network.Socket import AESocketListener
from AEIQ.Network.Core import AENetRsp

class MyListener(AESocketListener):
    def on_data_received(self, response: AENetRsp):
        """处理接收到的数据"""
        print(f"收到数据: {response.data}")
    
    def on_connection_closed(self):
        """处理连接关闭"""
        print("连接已关闭")
    
    def on_error(self, error: Exception):
        """处理错误"""
        print(f"发生错误: {error}")
```

### 4. AESocketWrapper (Socket 包装器)

位置：`AEIQ/Network/Socket/AESocketWrapper.py`

```python
import socket
from AEIQ.Network.Socket import AESocketWrapper, AESocketListener
from AEIQ.Network.Core import AENetReq

# 创建或接受 socket 连接
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('localhost', 8080))

# 创建包装器
wrapper = AESocketWrapper(sock, ('localhost', 8080))

# 添加监听器
listener = MyListener()
wrapper.add_listener(listener)

# 开始接收数据（在独立线程中）
wrapper.start_receiving()

# 发送数据
request = AENetReq(action="test", data={"key": "value"})
wrapper.send(request)

# 关闭连接
wrapper.close()
```

## 使用场景

### 场景1：服务端接受连接

```python
import socket
from AEIQ.Network.Socket import AESocketWrapper, AESocketListener
from AEIQ.Network.Core import AENetRsp

# 创建服务端 socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(('0.0.0.0', 8080))
server_socket.listen(5)

# 接受客户端连接
client_sock, client_addr = server_socket.accept()

# 创建包装器
wrapper = AESocketWrapper(client_sock, client_addr)

# 定义监听器
class ServerListener(AESocketListener):
    def on_data_received(self, response: AENetRsp):
        # 处理客户端请求
        print(f"收到客户端数据: {response.data}")
        
        # 发送响应（注意：这里需要根据实际情况调整）
        # wrapper.send(...)

# 添加监听器并开始接收
wrapper.add_listener(ServerListener())
wrapper.start_receiving()
```

### 场景2：客户端连接

```python
import socket
from AEIQ.Network.Socket import AESocketWrapper, AESocketListener
from AEIQ.Network.Core import AENetReq

# 连接到服务端
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('server_ip', 8080))

# 创建包装器
wrapper = AESocketWrapper(sock)

# 定义监听器
class ClientListener(AESocketListener):
    def on_data_received(self, response: AENetRsp):
        print(f"收到服务端响应: {response.data}")

# 添加监听器并开始接收
wrapper.add_listener(ClientListener())
wrapper.start_receiving()

# 发送请求
request = AENetReq(action="query", data={"query": "select * from users"})
wrapper.send(request)
```

### 场景3：多个监听器

```python
# 可以添加多个监听器来处理不同的逻辑
class LoggingListener(AESocketListener):
    def on_data_received(self, response: AENetRsp):
        logging.info(f"Received: {response.model_dump()}")

class BusinessListener(AESocketListener):
    def on_data_received(self, response: AENetRsp):
        # 业务逻辑处理
        process_business_logic(response)

wrapper.add_listener(LoggingListener())
wrapper.add_listener(BusinessListener())
wrapper.start_receiving()
```

## 数据传输协议

数据传输使用以下格式：

```
[4字节：数据长度(大端序)][N字节：JSON数据]
```

例如：
- 数据长度：100 字节
- 传输格式：`\x00\x00\x00\x64` + JSON字符串

这种格式确保了：
1. 接收方知道要读取多少字节
2. 避免粘包问题
3. 支持大数据传输

## 注意事项

1. **线程安全**：接收操作在独立线程中进行，监听器回调也在该线程中执行
2. **资源管理**：使用完毕后记得调用 `wrapper.close()` 关闭连接
3. **异常处理**：监听器中的异常会被捕获并记录，不会影响接收线程
4. **上下文管理器**：支持 `with` 语句自动管理资源

```python
with AESocketWrapper(sock) as wrapper:
    wrapper.add_listener(listener)
    wrapper.start_receiving()
    wrapper.send(request)
# 自动关闭连接
```

## 示例代码

完整的使用示例请参考：`example_socket_usage.py`

运行示例：
```bash
# 启动服务端
python AEIQ/Network/Socket/example_socket_usage.py server

# 启动客户端（另一个终端）
python AEIQ/Network/Socket/example_socket_usage.py
```
