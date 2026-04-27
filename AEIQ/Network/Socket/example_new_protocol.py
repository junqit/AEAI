"""
使用新包头结构的 Socket 通信示例
"""

import socket
import time
import threading
from AEIQ.Network.Socket import AESocketWrapper, AESocketListener
from AEIQ.Network.Core import AENetReq, AENetReqAction, AENetReqData, AENetRsp, AENetRspData


class ServerListener(AESocketListener):
    """服务端监听器 - 接收请求并回复响应"""

    def __init__(self, wrapper: AESocketWrapper):
        self.wrapper = wrapper

    def on_request_received(self, request: AENetReq):
        """接收到请求"""
        print(f"\n[服务端] 收到请求:")
        print(f"  - Action: {request.action}")
        print(f"  - Content: {request.data.content if request.data else None}")
        print(f"  - Request ID: {request.request_id}")

        # 处理请求并发送响应
        response = AENetRsp.create_success(
            data=AENetRspData(
                content=f"服务端已处理你的 {request.action} 请求",
                result={"processed": True, "timestamp": time.time()}
            ),
            request_id=request.request_id
        )

        self.wrapper.send_response(response)
        print(f"[服务端] 已发送响应")

    def on_data_received(self, response: AENetRsp):
        """接收到响应（服务端一般不接收响应）"""
        print(f"[服务端] 收到意外的响应数据")

    def on_connection_closed(self):
        print("[服务端] 连接已关闭")

    def on_error(self, error: Exception):
        print(f"[服务端] 错误: {error}")


class ClientListener(AESocketListener):
    """客户端监听器 - 接收响应"""

    def on_request_received(self, request: AENetReq):
        """接收到请求（客户端一般不接收请求）"""
        print(f"[客户端] 收到意外的请求数据")

    def on_data_received(self, response: AENetRsp):
        """接收到响应"""
        print(f"\n[客户端] 收到响应:")
        print(f"  - Status: {response.status}")
        print(f"  - Success: {response.is_success}")
        if response.data:
            print(f"  - Content: {response.data.content}")
            print(f"  - Result: {response.data.result}")
        print(f"  - Request ID: {response.request_id}")

    def on_connection_closed(self):
        print("[客户端] 连接已关闭")

    def on_error(self, error: Exception):
        print(f"[客户端] 错误: {error}")


def run_server():
    """运行服务端"""
    print("=" * 60)
    print("服务端启动")
    print("=" * 60)

    # 创建服务端 socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('localhost', 9999))
    server_socket.listen(1)

    print("等待客户端连接...")

    # 接受连接
    client_sock, client_addr = server_socket.accept()
    print(f"客户端已连接: {client_addr}")

    # 创建 Socket 包装器
    wrapper = AESocketWrapper(client_sock, client_addr)

    # 添加监听器
    listener = ServerListener(wrapper)
    wrapper.add_listener(listener)

    # 开始接收数据
    wrapper.start_receiving()

    # 发送一个心跳
    time.sleep(1)
    wrapper.send_heartbeat()
    print("[服务端] 已发送心跳包")

    # 保持运行
    try:
        while wrapper.is_connected:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n服务端关闭")

    wrapper.close()
    server_socket.close()


def run_client():
    """运行客户端"""
    print("=" * 60)
    print("客户端启动")
    print("=" * 60)

    # 等待服务端启动
    time.sleep(1)

    # 连接到服务端
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client_socket.connect(('localhost', 9999))
    except ConnectionRefusedError:
        print("无法连接到服务端，请先启动服务端")
        return

    print("已连接到服务端")

    # 创建 Socket 包装器
    wrapper = AESocketWrapper(client_socket, ('localhost', 9999))

    # 添加监听器
    listener = ClientListener()
    wrapper.add_listener(listener)

    # 开始接收数据
    wrapper.start_receiving()

    # 等待一下
    time.sleep(0.5)

    # 发送 Ping
    print("\n[客户端] 发送 PING...")
    wrapper.send_ping()

    time.sleep(1)

    # 发送聊天请求
    print("\n[客户端] 发送聊天请求...")
    request1 = AENetReq(
        action=AENetReqAction.CHAT,
        data=AENetReqData(
            content="你好，请帮我查询天气",
            parameters={"location": "北京"}
        ),
        request_id="req_001"
    )
    wrapper.send(request1)

    time.sleep(2)

    # 发送查询请求
    print("\n[客户端] 发送查询请求...")
    request2 = AENetReq(
        action=AENetReqAction.QUERY,
        data=AENetReqData(
            content="SELECT * FROM users",
            parameters={"limit": 10}
        ),
        request_id="req_002"
    )
    wrapper.send(request2)

    time.sleep(2)

    # 发送命令请求
    print("\n[客户端] 发送命令请求...")
    request3 = AENetReq(
        action=AENetReqAction.COMMAND,
        data=AENetReqData(
            content="ls -la",
            parameters={"directory": "/tmp"}
        ),
        request_id="req_003"
    )
    wrapper.send(request3)

    time.sleep(2)

    # 关闭连接
    print("\n[客户端] 关闭连接")
    wrapper.close()


def run_demo():
    """运行演示"""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "server":
        run_server()
    elif len(sys.argv) > 1 and sys.argv[1] == "client":
        run_client()
    else:
        print("使用方法:")
        print("  服务端: python example_new_protocol.py server")
        print("  客户端: python example_new_protocol.py client")
        print()
        print("请在两个终端中分别运行服务端和客户端")


if __name__ == "__main__":
    run_demo()
