from enum import Enum
from typing import List, Dict, Any
from dataclasses import dataclass

class LLMType(Enum):
    CLAUDE = "claude"
    CHATGPT = "chatgpt"
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"

class AEAiLevel(Enum):
    default = 1
    middle = 2
    high = 3

@dataclass
class AEQuestion:
    messages: List[Dict[str, Any]]
    llm_type: LLMType
    level: AEAiLevel = AEAiLevel.default
