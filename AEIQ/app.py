import sys

# 运行环境要求：Python >= 3.7（dict 插入有序等特性依赖），低于此版本中止运行
if sys.version_info < (3, 7):
    raise SystemExit(
        "需要 Python >= 3.7，当前版本 %s，无法运行" % ".".join(map(str, sys.version_info[:3]))
    )

from pathlib import Path
# 添加父目录(Service/)到路径，使共享包 common 可被导入
# 须早于会间接导入 AELLMPayload 的 import（AENetRouteCenter → AEUserContext → AELLMPayload → common）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from AEIQConfig import config
from Context.NetRoutCenter.AENetRouteCenter import AENetRouteCenter
from Network.Socket.Connection.AESocketServer import get_socket_server
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 屏蔽 httpx / httpcore 的 DEBUG 噪音日志
for _name in ("httpx", "httpcore", "httpcore.http11", "httpcore.http2"):
    logging.getLogger(_name).setLevel(logging.WARNING)

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

# 2. 创建网络路由中心（业务层），注入 socket_server 作为 socket_interface
ae_net_route_center = AENetRouteCenter(socket_interface=socket_server)

# 3. AENetRouteCenter 实现 AESocketListener 接口，直接注册到 socket_server
socket_server.add_listener(ae_net_route_center)

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
