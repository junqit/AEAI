"""
Question Route - 接收 question 请求，调用单个 LLM
使用 AELlmManager 统一管理 LLM Provider
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from question.AEQuestion import LLMType, AEQuestion, AEAiLevel
from AELlmManager import get_ae_llm_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

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
    request_id = f"{datetime.now().timestamp()}"
    logger.info(f"📥 [Request-{request_id}] 收到 question 请求 - llm_type={request.llm_type}, level={request.level}, messages_count={len(request.messages)}")
    logger.debug(f"📋 [Request-{request_id}] 请求详情 - messages={request.messages}")

    start_time = datetime.now()

    try:
        # 解析 LLM 类型
        llm_type_map = {
            "claude": LLMType.CLAUDE,
            "chatgpt": LLMType.CHATGPT,
            "deepseek": LLMType.DEEPSEEK,
            "gemini": LLMType.GEMINI
        }
        llm_type = llm_type_map.get(request.llm_type.lower())
        if not llm_type:
            error_msg = f"不支持的 LLM 类型: {request.llm_type}"
            logger.error(f"❌ [Request-{request_id}] {error_msg}")
            raise HTTPException(
                status_code=400,
                detail=error_msg
            )

        # 解析 AI 级别
        level_map = {
            "default": AEAiLevel.default,
            "middle": AEAiLevel.middle,
            "high": AEAiLevel.high
        }
        level = level_map.get(request.level.lower(), AEAiLevel.default)

        logger.info(f"🔄 [Request-{request_id}] 开始处理 - LLM={llm_type.value}, level={level.name}")

        # 创建 AEQuestion 对象（所有参数都在对象内部）
        question = AEQuestion(
            messages=request.messages,
            llm_type=llm_type,
            level=level,
            system=request.system,
            tools=request.tools,
            context=request.context or {}
        )
        logger.debug(f"✅ [Request-{request_id}] AEQuestion 对象已创建")

        # 获取 AELlmManager 实例
        manager = get_ae_llm_manager()
        logger.debug(f"✅ [Request-{request_id}] AELlmManager 实例已获取")

        # 调用 LLM - 所有参数都在 question 对象内部，不需要传递零散参数
        logger.info(f"🚀 [Request-{request_id}] 调用 LLM - llm_type={llm_type.value}")
        result = manager.generate(question)

        elapsed = (datetime.now() - start_time).total_seconds()

        if result["status"] == "success":
            response_length = len(result.get("response", "")) if result.get("response") else 0
            logger.info(f"✅ [Request-{request_id}] LLM 调用成功 - llm_type={request.llm_type}, elapsed={elapsed:.2f}s, response_length={response_length}")
            logger.debug(f"📝 [Request-{request_id}] 响应内容预览: {result.get('response', '')[:200]}...")
        else:
            logger.error(f"❌ [Request-{request_id}] LLM 调用失败 - llm_type={request.llm_type}, elapsed={elapsed:.2f}s, error={result.get('error')}")

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
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.error(f"❌ [Request-{request_id}] HTTP 异常 - elapsed={elapsed:.2f}s")
        raise
    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        error_msg = f"Failed to process question: {str(e)}"
        logger.error(f"❌ [Request-{request_id}] 未知错误 - elapsed={elapsed:.2f}s, error={error_msg}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )
