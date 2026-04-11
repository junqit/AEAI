from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/ae/context/delete")
async def ae_delete_context(session_id: str):
    """
    删除会话

    Args:
        session_id: 会话 ID

    Returns:
        操作结果
    """
    from app import ae_context_manager

    success = await ae_context_manager.delete_context(session_id)

    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "message": "Context deleted successfully"
    }


@router.post("/ae/context/clear")
async def ae_clear_history(session_id: str):
    """
    清空会话历史

    Args:
        session_id: 会话 ID

    Returns:
        操作结果
    """
    from app import ae_context_manager

    context = await ae_context_manager.get_context(session_id)

    if not context:
        raise HTTPException(status_code=404, detail="Session not found")

    context.clear_history()

    return {
        "session_id": session_id,
        "message": "History cleared successfully"
    }
