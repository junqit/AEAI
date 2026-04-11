"""
FastAPI LLM Service
AI Agent with Router, Skills, MCP, RAG
使用 AELlmManager 统一管理所有 LLM 调用
"""

import sys
from pathlib import Path

# 添加当前目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from contextlib import asynccontextmanager

from config import config
from AELlmManager import get_ae_llm_manager, cleanup_ae_llm_manager
from routes import register_routes

# 生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化 AELlmManager
    print("=" * 50)
    print("Starting Agent API Service...")
    manager = get_ae_llm_manager()
    print(f"LLM Type: {manager.llm_type.value}")
    print(f"Service ready!")
    print("=" * 50)
    yield
    # 关闭时清理资源
    print("Shutting down...")
    cleanup_ae_llm_manager()


# 创建 FastAPI 应用
app = FastAPI(
    title=config.SERVICE_NAME,
    description=config.DESCRIPTION,
    version=config.VERSION,
    lifespan=lifespan
)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册所有路由
register_routes(app)

if __name__ == "__main__":
    # 启动服务
    # 使用方式: python app.py
    print(f"Starting {config.SERVICE_NAME} v{config.VERSION}")
    print(f"Server: http://{config.HOST}:{config.PORT}")
    print(f"API Docs: http://localhost:{config.PORT}/docs")
    print(f"Health Check: http://localhost:{config.PORT}/health")
    print()

    # 不使用 reload 模式，或使用 app 对象而不是字符串
    if config.RELOAD:
        print("⚠️  Warning: reload=True may cause import issues in multiprocessing mode")
        print("   Consider using: uvicorn app:app --reload --host 0.0.0.0 --port 9999")
        print()

    uvicorn.run(
        app,  # 直接使用 app 对象
        host=config.HOST,
        port=config.PORT,
        reload=False,  # 关闭 reload 避免 multiprocessing 问题
        log_level=config.LOG_LEVEL
    )
