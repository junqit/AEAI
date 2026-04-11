"""
Routes Registration
"""
from fastapi import FastAPI

from .root import router as root_router
from .health import router as health_router
from .question import router as question_router


def register_routes(app: FastAPI):
    """注册所有路由"""
    app.include_router(root_router)
    app.include_router(health_router)
    app.include_router(question_router)
