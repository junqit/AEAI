from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/ae/context/history")
async def ae_get_history(session_id: str):
    """
    获取会话历史

    Args:
        session_id: 会话 ID

    Returns:
        会话历史消息列表
    """
    from app import ae_context_manager

    context = await ae_context_manager.get_context(session_id)

    if not context:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "history": context.get_history()
    }
