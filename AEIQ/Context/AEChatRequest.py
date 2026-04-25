from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from enum import Enum


class AELLMType(Enum):
    """支持的 LLM 类型"""
    CLAUDE = "claude"
    CHATGPT = "chatgpt"
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"


class AEQuestionContext(BaseModel):
    """问题上下文"""
    id: str


class AEQuestion(BaseModel):
    """问题详情"""
    content: str
    type: Optional[str] = "text"  # text, command, search 等
    parameters: Optional[Dict[str, Any]] = None


class AEChatRequest(BaseModel):
    """
    聊天请求数据结构

    示例:
    {
        "llm_types": ["claude", "gemini"],
        "context": {
            "id": "context_id_hash_value"
        },
        "question": {
            "content": "用户输入的问题内容",
            "type": "text",
            "parameters": {...}
        }
    }
    """
    llm_types: List[AELLMType]  # 支持多个 LLM 类型
    context: AEQuestionContext
    question: AEQuestion

    class Config:
        use_enum_values = True  # 自动将 Enum 转换为值
