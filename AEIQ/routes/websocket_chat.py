from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json

router = APIRouter()

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket 连接端点 - 支持双向通信"""
    from websocket_manager import ws_manager
    from app import context_manager
    from llms.AEAiLevel import AEAiLevel

    # 接受连接
    await ws_manager.connect(websocket, session_id)

    try:
        # 发送欢迎消息
        await ws_manager.send_message(session_id, {
            "type": "connected",
            "session_id": session_id,
            "message": "WebSocket connected successfully"
        })

        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            message = json.loads(data)

            message_type = message.get("type")

            # 处理不同类型的消息
            if message_type == "chat":
                # 处理聊天消息
                user_input = message.get("message", "")

                # 发送处理中状态
                await ws_manager.send_message(session_id, {
                    "type": "processing",
                    "message": "Processing your request..."
                })

                # 获取或创建 Context
                context = context_manager.get_or_create_context(
                    session_id=session_id
                )

                # 处理消息
                result = await context.process_message(user_input)

                # 发送响应
                await ws_manager.send_message(session_id, {
                    "type": "chat_response",
                    "message": result,
                    "session_id": session_id
                })

            elif message_type == "confirmation_response":
                # 处理确认响应
                confirm_id = message.get("confirm_id")
                response = message.get("response")

                ws_manager.handle_confirmation_response(confirm_id, {
                    "answer": response,
                    "timestamp": message.get("timestamp")
                })

            elif message_type == "ping":
                # 心跳检测
                await ws_manager.send_message(session_id, {
                    "type": "pong"
                })

            else:
                # 未知消息类型
                await ws_manager.send_message(session_id, {
                    "type": "error",
                    "message": f"Unknown message type: {message_type}"
                })

    except WebSocketDisconnect:
        ws_manager.disconnect(session_id)
        print(f"[WebSocket] Client {session_id} disconnected")

    except Exception as e:
        print(f"[WebSocket] Error for session {session_id}: {e}")
        ws_manager.disconnect(session_id)
