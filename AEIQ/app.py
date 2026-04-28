from fastapi import FastAPI
from AEIQConfig import config
from Context.AEContextManager import AEContextManager
import logging

# 导入路由模块
import routes.post_root as post_root_module
import routes.websocket_chat as websocket_chat_module
import routes.ae_context_chat as ae_context_chat_module
import routes.ae_context_create as ae_context_create_module
import routes.ae_context_history as ae_context_history_module
import routes.ae_context_delete as ae_context_delete_module
import routes.ae_contexts_stats as ae_contexts_stats_module

# 导入 Socket 服务器
from routes.socket_server import start_socket_server, stop_socket_server

logger = logging.getLogger(__name__)

# FastAPI 应用 - 配置从 AEIQConfig 读取
app = FastAPI(
    title=config.APP_TITLE,
    description=config.APP_DESCRIPTION,
    version=config.APP_VERSION
)

# Context 管理器 - 配置从 AEIQConfig 读取
ae_context_manager = AEContextManager()

# 注册所有路由
# app.include_router(post_root_module.router)
# app.include_router(ae_context_create_module.router)
# app.include_router(ae_context_chat_module.router)
# app.include_router(ae_context_history_module.router)
# app.include_router(ae_context_delete_module.router)
# app.include_router(ae_contexts_stats_module.router)


@app.on_event("startup")
async def startup_event():
    """应用启动时的事件"""
    logger.info("Application starting up...")

    # 启动 UDP Socket 服务器（默认端口 8888）
    try:
        start_socket_server(host="0.0.0.0", port=8888)
        logger.info("UDP Socket server started on 0.0.0.0:8888")
    except Exception as e:
        logger.error(f"Failed to start UDP Socket server: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的事件"""
    logger.info("Application shutting down...")

    # 停止 UDP Socket 服务器
    try:
        stop_socket_server()
        logger.info("UDP Socket server stopped")
    except Exception as e:
        logger.error(f"Failed to stop UDP Socket server: {e}")
