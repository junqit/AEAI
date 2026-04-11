"""
Question Route - 接收 question 请求，支持多 LLM 并发调用
"""
from fastapi import APIRouter, HTTPException
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from question.AEQuestion import LLMType, AEQuestion
from AEAiLevel import AEAiLevel
from AEllm import AEllm

router = APIRouter(prefix="/question", tags=["question"])

# 创建线程池用于并发调用 LLM
executor = ThreadPoolExecutor(max_workers=4)


class AEQuestionRequest(BaseModel):
    """Question 请求模型"""
    question: str
    llm_types: Optional[List[str]] = None  # 支持多个 LLM 类型
    level: Optional[str] = "default"
    system: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "question": "请解释什么是 Python 装饰器",
                "llm_types": ["claude", "gemini"],
                "level": "high",
                "system": "你是一个 Python 专家"
            }
        }


class AEQuestionResponse(BaseModel):
    """Question 响应模型 - 支持多 LLM 响应"""
    status: str
    question: str
    answers: Dict[str, Any]  # 按 LLM 类型组织的答案
    timestamp: str

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "question": "请解释什么是 Python 装饰器",
                "answers": {
                    "claude": {
                        "response": "装饰器是...",
                        "status": "success",
                        "error": None,
                        "elapsed_seconds": 1.2
                    },
                    "gemini": {
                        "response": "装饰器是...",
                        "status": "success",
                        "error": None,
                        "elapsed_seconds": 0.8
                    }
                },
                "timestamp": "2026-04-11T12:00:00"
            }
        }


@router.post("", response_model=AEQuestionResponse)
async def process_question(request: AEQuestionRequest):
    """
    处理 question 请求，支持单个或多个 LLM 并发调用

    Args:
        request: 包含 question 和可选参数的请求
                llm_types 可以是单个或多个 LLM 类型

    Returns:
        AEQuestionResponse: 处理结果，包含所有 LLM 的响应
    """
    try:
        print(f"[{datetime.now().isoformat()}] Received question: {request.question}")

        # 解析 AI 级别
        level = AEAiLevel.default
        if request.level:
            level_map = {
                "default": AEAiLevel.default,
                "middle": AEAiLevel.middle,
                "high": AEAiLevel.high
            }
            level = level_map.get(request.level.lower(), AEAiLevel.default)

        # 解析 LLM 类型列表
        llm_types = []
        if request.llm_types:
            llm_type_map = {
                "claude": LLMType.CLAUDE,
                "chatgpt": LLMType.CHATGPT,
                "deepseek": LLMType.DEEPSEEK,
                "gemini": LLMType.GEMINI
            }
            for llm_type_str in request.llm_types:
                llm_type = llm_type_map.get(llm_type_str.lower())
                if llm_type:
                    llm_types.append(llm_type)
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"不支持的 LLM 类型: {llm_type_str}"
                    )

        # 如果没有指定 LLM 类型，使用默认 Claude
        if not llm_types:
            llm_types = [LLMType.CLAUDE]

        print(f"Processing with LLMs: {[lt.value for lt in llm_types]}, level: {level.name}")

        # 并发调用多个 LLM
        loop = asyncio.get_event_loop()
        tasks = []

        for llm_type in llm_types:
            task = loop.run_in_executor(
                executor,
                _call_single_llm,
                request.question,
                llm_type,
                level,
                request.system
            )
            tasks.append((llm_type, task))

        # 等待所有 LLM 响应
        answers = {}
        for llm_type, task in tasks:
            try:
                result = await task
                answers[llm_type.value] = result
            except Exception as e:
                answers[llm_type.value] = {
                    "response": None,
                    "status": "error",
                    "error": str(e),
                    "elapsed_seconds": 0
                }

        return AEQuestionResponse(
            status="success",
            question=request.question,
            answers=answers,
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


def _call_single_llm(
    question: str,
    llm_type: LLMType,
    level: AEAiLevel,
    system: Optional[str] = None
) -> Dict[str, Any]:
    """
    调用单个 LLM

    Args:
        question: 用户问题
        llm_type: LLM 类型
        level: AI 级别
        system: 系统提示词

    Returns:
        包含响应、状态和耗时的字典
    """
    start_time = time.time()
    try:
        # 创建问题对象
        ae_question = AEQuestion(
            question=question,
            system=system
        )

        # 调用 LLM
        response = AEllm.call_llm(
            question=ae_question,
            llm_type=llm_type,
            level=level
        )

        elapsed = time.time() - start_time

        return {
            "response": str(response),
            "status": "success",
            "error": None,
            "elapsed_seconds": round(elapsed, 2)
        }

    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "response": None,
            "status": "error",
            "error": str(e),
            "elapsed_seconds": round(elapsed, 2)
        }

