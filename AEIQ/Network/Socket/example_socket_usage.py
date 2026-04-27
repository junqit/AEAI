"""
Socket 包装类使用示例

演示如何使用 AESocketWrapper 进行 socket 通信
"""

import socket
import time
from AEIQ.Network.Socket import AESocketWrapper, AESocketListener
from AEIQ.Network.Core import AENetReq, AENetRsp


class MySocketListener(AESocketListener):
    """自定义监听器示例"""

    def on_data_received(self, response: AENetRsp) -> None:
        """处理接收到的数据"""
        print(f"[监听器] 收到响应:")
        print(f"  - 成功: {response.success}")
        print(f"  - 数据: {response.data}")
        print(f"  - 错误: {response.error}")
        print(f"  - 请求ID: {response.request_id}")

    def on_connection_closed(self) -> None:
        """处理连接关闭"""
        print("[监听器] 连接已关闭")

    def on_error(self, error: Exception) -> None:
        """处理错误"""
        print(f"[监听器] 发生错误: {error}")


def example_server():
    """
    示例服务端
    监听客户端连接，并响应客户端请求
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('localhost', 9999))
    server_socket.listen(1)

    print("服务端启动，等待连接...")

    client_sock, client_addr = server_socket.accept()
    print(f"客户端已连接: {client_addr}")

    # 创建 socket 包装器
    wrapper = AESocketWrapper(client_sock, client_addr)

    # 添加监听器
    class ServerListener(AESocketListener):
        def __init__(self, wrapper):
            self.wrapper = wrapper

        def on_data_received(self, request_data: AENetRsp) -> None:
            # 注意：服务端实际接收的应该是 AENetReq，但由于接收线程
            # 解析为 AENetRsp，这里我们需要处理这个情况
            print(f"服务端收到请求: {request_data.data}")

            # 发送响应
            response = AENetRsp(
                success=True,
                data={"message": "服务端已处理你的请求", "echo": request_data.data},
                request_id=request_data.request_id
            )
            self.wrapper.send(response)  # 注意：这里类型不匹配，需要修改

    listener = ServerListener(wrapper)
    wrapper.add_listener(listener)
    wrapper.start_receiving()

    # 保持服务端运行
    try:
        while wrapper.is_connected:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n服务端关闭")

    wrapper.close()
    server_socket.close()


def example_client():
    """
    示例客户端
    连接到服务端，发送请求并接收响应
    """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(('localhost', 9999))

    print("已连接到服务端")

    # 创建 socket 包装器
    wrapper = AESocketWrapper(client_socket, ('localhost', 9999))

    # 添加监听器
    listener = MySocketListener()
    wrapper.add_listener(listener)

    # 开始接收数据
    wrapper.start_receiving()

    # 发送请求
    request = AENetReq(
        action="test_action",
        data={"message": "Hello Server", "timestamp": time.time()},
        request_id="req_001"
    )

    print(f"\n发送请求: {request.model_dump()}")
    wrapper.send(request)

    # 等待响应
    time.sleep(2)

    # 发送第二个请求
    request2 = AENetReq(
        action="another_action",
        data={"value": 42},
        request_id="req_002"
    )

    print(f"\n发送请求: {request2.model_dump()}")
    wrapper.send(request2)

    # 等待响应
    time.sleep(2)

    # 关闭连接
    wrapper.close()
    print("\n客户端关闭")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "server":
        example_server()
    else:
        print("用法:")
        print("  服务端: python example_socket_usage.py server")
        print("  客户端: python example_socket_usage.py")
        print("\n启动客户端...")
        example_client()
