"""
Root Route
"""
from fastapi import APIRouter
from datetime import datetime

router = APIRouter(tags=["root"])


@router.get("/")
async def root():
    """根路径，返回服务信息"""
    return {
        "service": "LLM API",
        "version": "2.0.0",
        "description": "LLM Service with AELlmManager",
        "status": "running",
        "timestamp": datetime.now().isoformat()
    }
