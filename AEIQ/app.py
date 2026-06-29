import sys
from pathlib import Path
# 添加父目录(Service/)到路径，使共享包 common 可被导入
# 须早于会间接导入 AELLMPayload 的 import（AEContextManager → AELLMPayload → common）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from AEIQConfig import config
from Context.AEContextManager import AEContextManager
from Network.Socket.Connection.AESocketServer import get_socket_server
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 导入路由模块
import routes.post_root as post_root_module
import routes.websocket_chat as websocket_chat_module
import routes.ae_context_create as ae_context_create_module
import routes.ae_context_history as ae_context_history_module
import routes.ae_context_delete as ae_context_delete_module
import routes.ae_contexts_stats as ae_contexts_stats_module

logger = logging.getLogger(__name__)

# ============= 分层架构组装 =============
# 1. 获取 Socket 服务器（网络层）
socket_server = get_socket_server(host="0.0.0.0", port=8888)

# 2. 创建 Context 管理器（业务层），注入 socket_server 作为 socket_interface
ae_context_manager = AEContextManager(socket_interface=socket_server)

# 3. AEContextManager 实现 AESocketListener 接口，直接注册到 socket_server
socket_server.add_listener(ae_context_manager)

logger.info("Layered architecture assembled: Network -> Business")
# ========================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    logger.info("Application starting up...")
    if not socket_server.is_running:
        socket_server.start()
    logger.info("UDP Socket server started on 0.0.0.0:8888")

    yield

    # shutdown
    logger.info("Application shutting down...")
    socket_server.stop()
    logger.info("UDP Socket server stopped")


# FastAPI 应用
app = FastAPI(
    title=config.APP_TITLE,
    description=config.APP_DESCRIPTION,
    version=config.APP_VERSION,
    lifespan=lifespan
)

# 注册所有路由
# app.include_router(post_root_module.router)
# app.include_router(ae_context_create_module.router)
# app.include_router(ae_context_history_module.router)
# app.include_router(ae_context_delete_module.router)
# app.include_router(ae_contexts_stats_module.router)
