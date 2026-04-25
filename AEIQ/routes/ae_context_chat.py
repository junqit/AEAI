from fastapi import APIRouter, HTTPException
from Context.AEChatRequest import AEChatRequest

router = APIRouter()

@router.post("/ae/context/chat")
async def ae_chat(request: AEChatRequest):
  
    from app import ae_context_manager

    try:
        # 获取或创建 Context
        context = await ae_context_manager.get_or_create_context(
            session_id=request.context.id
        )

        # llm_types 已经是字符串列表（因为 Pydantic Config 的 use_enum_values = True）
        llm_type_values = request.llm_types

        # 异步并行处理多个 LLM 请求
        responses = await context.process_message(
            user_input=request.question.content,
            llm_types=llm_type_values
        )

        # 组装响应结果
        result = {
            "context": {
                "id": request.context.id
            },
            "question": {
                "content": request.question.content,
                "type": request.question.type
            },
            "llm_responses": {}
        }

        # 按 llm_type 组织响应
        for response in responses:
            result["llm_responses"][response.llm_type] = {
                "content": response.response,
                "error": response.error,
                "timestamp": response.timestamp
            }

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
