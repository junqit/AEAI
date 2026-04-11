"""
UDP 服务器使用示例
"""
from udp_server import UDPServer
from message_handler import MessageHandler


def custom_handler(data, addr):
    """
    自定义消息处理函数示例
    """
    print(f"收到消息: {data} 来自 {addr}")

    # 简单的 echo 响应
    return {
        "status": "success",
        "echo": data,
        "message": "This is a custom handler response"
    }


def main():
    print("=== UDP 服务器示例 ===\n")

    # 示例 1: 使用默认消息处理器
    print("示例 1: 使用默认消息处理器")
    handler = MessageHandler()

    server = UDPServer(host="0.0.0.0", port=9999)
    server.set_message_handler(handler.handle)

    # 示例 2: 使用自定义处理函数
    # server.set_message_handler(custom_handler)

    try:
        server.start()
        print(f"✓ 服务器启动成功: {server.host}:{server.port}")
        print("✓ 等待接收消息...")
        print("✓ 按 Ctrl+C 停止服务器\n")

        # 保持运行
        import time
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n正在停止服务器...")
        server.stop()
        print("✓ 服务器已停止")

    # 示例 3: 使用上下文管理器
    # with UDPServer(host="0.0.0.0", port=9999) as server:
    #     server.set_message_handler(handler.handle)
    #     while True:
    #         time.sleep(1)


if __name__ == "__main__":
    main()
