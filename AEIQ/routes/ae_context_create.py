from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class CreateContextRequest(BaseModel):
    """创建 Context 请求模型"""
    aedir: str  # Context 对应的目录路径

    class Config:
        json_schema_extra = {
            "example": {
                "aedir": "/Users/username/project"
            }
        }


class CreateContextResponse(BaseModel):
    """创建 Context 响应模型"""
    contextid: str  # 生成的唯一 Context ID

    class Config:
        json_schema_extra = {
            "example": {
                "contextid": "ctx_abc123def456"
            }
        }


@router.post("/ae/context/create", response_model=CreateContextResponse)
async def create_context(request: CreateContextRequest):
    """
    创建新的 Context

    Args:
        request: CreateContextRequest 包含 aedir（目录路径）

    Returns:
        CreateContextResponse 包含生成的 session_id (作为 contextid)
    """
    from app import ae_context_manager

    try:
        # 验证 aedir 是否为空
        if not request.aedir or request.aedir.strip() == "":
            raise HTTPException(
                status_code=400,
                detail="aedir cannot be empty"
            )

        # 创建 Context（内部自动生成 session_id）
        context = await ae_context_manager.create_context(aedir=request.aedir)

        # 从 Context 实例获取自动生成的 session_id
        session_id = context.session_id

        print(f"✅ Context 创建成功")
        print(f"   Session ID: {session_id}")
        print(f"   AE Dir: {request.aedir}")

        # 返回 session_id（客户端将其作为 contextid 使用）
        return CreateContextResponse(contextid=session_id)

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Context 创建失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create context: {str(e)}"
        )
