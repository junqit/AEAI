"""
UDP 服务器启动脚本
与 FastAPI 应用集成
"""
import sys
import os

# 添加父目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from udp_server import UDPServer
from message_handler import MessageHandler


def main():
    """启动 UDP 服务器"""
    # 可选：导入 Context Manager
    try:
        from app import context_manager
        print("已加载 Context Manager")
    except ImportError:
        context_manager = None
        print("未加载 Context Manager，使用独立模式")

    # 创建消息处理器
    handler = MessageHandler(context_manager=context_manager)

    # 创建并启动 UDP 服务器
    server = UDPServer(
        host="0.0.0.0",
        port=9999,
        buffer_size=4096
    )

    # 设置消息处理器
    server.set_message_handler(handler.handle)

    try:
        server.start()
        print(f"UDP 服务器运行在 {server.host}:{server.port}")
        print("按 Ctrl+C 停止服务器")

        # 保持服务器运行
        import time
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n正在停止服务器...")
        server.stop()
        print("服务器已停止")


if __name__ == "__main__":
    main()
