from enum import Enum
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field

class LLMType(Enum):
    CLAUDE = "claude"
    CHATGPT = "chatgpt"
    DEEPSEEK = "deepseek"
    GEMINI = "GEMINI"

@dataclass
class AEQuestion:
    question: str
    tools: Optional[List[Dict[str, Any]]] = None
    system: Optional[str] = None
    context: Optional[Dict[str, Any]] = field(default_factory=dict)

    def to_messages(self) -> List[Dict[str, str]]:
        """将问题转换为消息格式"""
        return [{"role": "user", "content": self.question}]

    def add_tool(self, tool: Dict[str, Any]):
        """添加工具"""
        if self.tools is None:
            self.tools = []
        self.tools.append(tool)

    def add_context(self, key: str, value: Any):
        """添加上下文信息"""
        self.context[key] = value
