from fastapi import APIRouter, HTTPException
from Context.AEChatRequest import AEChatRequest

router = APIRouter()
@router.post("/ae/context/chat")
async def ae_chat(request: AEChatRequest):
    """
    处理支持多 LLM 类型的聊天消息

    Args:
        request: AEChatRequest 包含用户输入和多个 LLM 类型

    Returns:
        包含所有 LLM 响应的结果，按 llm_type 区分
    """
    from app import ae_context_manager

    try:
        # 获取或创建 Context
        context = await ae_context_manager.get_or_create_context(
            session_id=request.session_id
        )

        # 转换 LLM 类型为字符串列表
        llm_type_values = [llm_type.value for llm_type in request.llm_types]

        # 异步并行处理多个 LLM 请求
        responses = await context.process_message(
            user_input=request.user_input,
            llm_types=llm_type_values
        )

        # 组装响应结果
        result = {
            "session_id": request.session_id,
            "user_input": request.user_input,
            "llm_responses": {}
        }

        # 按 llm_type 组织响应
        for response in responses:
            result["llm_responses"][response.llm_type] = {
                "response": response.response,
                "error": response.error,
                "timestamp": response.timestamp
            }

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
