"""
分层架构修复说明

问题：AttributeError: 'SocketConnectionManager' object has no attribute 'socket_manager'

原因：socket_server.py 导入方式错误
```python
from Network.Socket import socket_manager  # 导入的是模块
self.connection_manager = socket_manager.socket_manager  # 错误：试图访问模块的属性
```

修复方案：
```python
from .socket_manager import socket_manager  # 直接导入全局实例
self.connection_manager = socket_manager  # 正确：直接使用实例
```

修改的文件：
1. AEIQ/Network/Socket/socket_server.py
   - 第 10 行：from .socket_manager import socket_manager
   - 第 43 行：self.connection_manager = socket_manager

验证：
所有 Python 语法检查通过 ✅

架构说明：
┌─────────────────────────────────────────────────┐
│                  app.py                          │
│            (Application Layer)                   │
│                                                  │
│  1. socket_server = get_socket_server()         │
│  2. context_mgr = AEContextManager(             │
│        response_sender=socket_server.conn_mgr)  │
│  3. socket_server.conn_mgr.set_request_handler( │
│        context_mgr)                              │
└─────────────────────────────────────────────────┘
         │                                  │
         │                                  │
         ▼                                  ▼
┌──────────────────┐              ┌──────────────────┐
│  Network Layer   │              │  Business Layer  │
│                  │              │                  │
│ SocketServer     │              │ ContextManager   │
│   │              │              │                  │
│   └─connection_  │◄────────────►│ handle_request() │
│     manager      │ IResponseSender│                │
│                  │   │           │ _send_response() │
│ set_request_     │   │           │                  │
│ handler()        │   └──────────►│                  │
│                  │ IRequestHandler│                │
└──────────────────┘              └──────────────────┘

数据流：
1. UDP数据 → SocketServer.receive_loop()
2. 数据 → AEPacketParser.parse()
3. AENetReq → SocketConnectionManager
4. SocketConnectionListener.on_request_received()
5. → AEContextManager.handle_request()
6. AI处理 → AEContextManager._handle_xxx()
7. AENetRsp → AEContextManager._send_response()
8. → SocketConnectionManager.send_response()
9. → AESocketWrapper.send_response()
10. 字节流 → 客户端

接口定义：
- IRequestHandler: handle_request(request, connection_id)
- IResponseSender: send_response(connection_id, response)

优势：
✅ 分层清晰：网络层、业务层、应用层
✅ 低耦合：通过接口（Protocol）通信
✅ 高内聚：每层职责单一
✅ 可测试：可以独立测试每一层
✅ 可扩展：易于添加新功能

注意事项：
1. socket_manager 是全局单例，在 socket_manager.py 末尾定义
2. SocketServer 通过 self.connection_manager 暴露给外部
3. 依赖注入在 app.py 中完成
4. 两层通过接口通信，不直接依赖具体实现
"""
