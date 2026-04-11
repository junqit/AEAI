from pydantic import BaseModel
from typing import List, Optional
from enum import Enum


class AELLMType(Enum):
    """支持的 LLM 类型"""
    CLAUDE = "claude"
    CHATGPT = "chatgpt"
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"


class AEChatRequest(BaseModel):
    """支持多个 LLM type 的聊天请求"""
    user_input: str
    session_id: str
    llm_types: List[AELLMType]  # 支持多个 LLM 类型
    work_dir: Optional[str] = None

    class Config:
        use_enum_values = True  # 自动将 Enum 转换为值
