"""
Question Route - 接收 question 请求，调用单个 LLM
使用 AELlmManager 统一管理 LLM Provider
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from question.AEQuestion import LLMType, AEQuestion, AEAiLevel
from AELlmManager import get_ae_llm_manager

class AEQuestionRequest(BaseModel):
    """Question 请求模型 - 接收已组装好的数据"""
    messages: List[Dict[str, Any]]  # 已组装好的消息列表（包含 user、assistant 等）
    llm_type: Optional[str] = "claude"  # LLM 类型
    level: Optional[str] = "default"  # AI 级别
    system: Optional[str] = None  # 系统提示词
    tools: Optional[List[Dict[str, Any]]] = None  # 工具列表
    context: Optional[Dict[str, Any]] = None  # 上下文信息

    class Config:
        json_schema_extra = {
            "example": {
                "messages": [
                    {"role": "user", "content": "请解释什么是 Python 装饰器"}
                ],
                "llm_type": "claude",
                "level": "high",
                "max_tokens": 4096,
                "system": "你是一个 Python 专家",
                "tools": [],
                "context": {}
            }
        }


class AEQuestionResponse(BaseModel):
    """Question 响应模型 - 单个 LLM 响应"""
    status: str
    messages: List[Dict[str, Any]]  # 请求的消息列表
    response: Optional[str] = None
    error: Optional[str] = None
    llm_type: str
    elapsed_seconds: float
    timestamp: str

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "messages": [
                    {"role": "user", "content": "请解释什么是 Python 装饰器"}
                ],
                "response": "装饰器是 Python 中的一种设计模式...",
                "error": None,
                "llm_type": "claude",
                "elapsed_seconds": 1.2,
                "timestamp": "2026-04-11T12:00:00"
            }
        }

router = APIRouter(prefix="/aellms/question", tags=["question"])
@router.post("", response_model=AEQuestionResponse)
async def process_question(request: AEQuestionRequest):
    """
    处理 question 请求，调用单个 LLM
    使用 AELlmManager 统一管理

    Args:
        request: 包含已组装好的 messages 和可选参数的请求

    Returns:
        AEQuestionResponse: 处理结果
    """
    try:
        print(f"[{datetime.now().isoformat()}] Received messages: {request.messages}")

        # 解析 LLM 类型
        llm_type_map = {
            "claude": LLMType.CLAUDE,
            "chatgpt": LLMType.CHATGPT,
            "deepseek": LLMType.DEEPSEEK,
            "gemini": LLMType.GEMINI
        }
        llm_type = llm_type_map.get(request.llm_type.lower())
        if not llm_type:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的 LLM 类型: {request.llm_type}"
            )

        # 解析 AI 级别
        level_map = {
            "default": AEAiLevel.default,
            "middle": AEAiLevel.middle,
            "high": AEAiLevel.high
        }
        level = level_map.get(request.level.lower(), AEAiLevel.default)

        print(f"Processing with LLM: {llm_type.value}, level: {level.name}")

        # 创建 AEQuestion 对象（所有参数都在对象内部）
        question = AEQuestion(
            messages=request.messages,
            llm_type=llm_type,
            level=level,
            system=request.system,
            tools=request.tools,
            context=request.context or {}
        )

        # 获取 AELlmManager 实例
        manager = get_ae_llm_manager()

        # 调用 LLM - 所有参数都在 question 对象内部，不需要传递零散参数
        result = manager.generate(question)

        # 返回响应
        return AEQuestionResponse(
            status=result["status"],
            messages=request.messages,
            response=result.get("response"),
            error=result.get("error"),
            llm_type=request.llm_type,
            elapsed_seconds=round(result["elapsed_seconds"], 2),
            timestamp=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error processing question: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process question: {str(e)}"
        )
