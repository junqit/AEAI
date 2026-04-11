from fastapi import APIRouter

router = APIRouter()


@router.get("/ae/contexts/stats")
async def ae_get_all_stats():
    """
    获取所有会话的统计信息

    Returns:
        所有会话的统计信息
    """
    from app import ae_context_manager

    stats = await ae_context_manager.get_all_contexts_stats()
    active_count = await ae_context_manager.get_active_sessions_count()

    return {
        "active_sessions": active_count,
        "sessions": stats
    }
