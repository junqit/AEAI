from fastapi import FastAPI
from AEIQConfig import config
from Context.AEContextManager import AEContextManager

# 导入路由模块
import routes.post_root as post_root_module
import routes.websocket_chat as websocket_chat_module
import routes.ae_context_chat as ae_context_chat_module
import routes.ae_context_history as ae_context_history_module
import routes.ae_context_delete as ae_context_delete_module
import routes.ae_contexts_stats as ae_contexts_stats_module

# FastAPI 应用 - 配置从 AEIQConfig 读取
app = FastAPI(
    title=config.APP_TITLE,
    description=config.APP_DESCRIPTION,
    version=config.APP_VERSION
)

# Context 管理器 - 配置从 AEIQConfig 读取
ae_context_manager = AEContextManager()

# 注册所有路由
app.include_router(post_root_module.router)
app.include_router(websocket_chat_module.router)
app.include_router(ae_context_chat_module.router)
app.include_router(ae_context_history_module.router)
app.include_router(ae_context_delete_module.router)
app.include_router(ae_contexts_stats_module.router)
