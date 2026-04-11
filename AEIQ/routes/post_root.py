from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class RootRequest(BaseModel):
    pass

@router.get("/")
async def root(request: RootRequest):
    """根路径"""
    return {
        "name": "Agent API",
        "version": "2.0.0",
        "status": "running"
    }
