from enum import Enum
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field

class LLMType(Enum):
    CLAUDE = "claude"
    CHATGPT = "chatgpt"
    DEEPSEEK = "deepseek"
    GEMINI = "GEMINI"

class AEAiLevel(Enum):
    default = 1
    middle = 2
    high = 3

@dataclass
class AEQuestion:
    
    messages: List[Dict[str, Any]]  # 已组装好的消息列表
    llm_type: LLMType  # LLM 类型
    level: AEAiLevel = AEAiLevel.default  # AI 级别
    max_tokens: int = 4096  # 最大 token 数
    system: Optional[str] = None  # 系统提示词
    tools: Optional[List[Dict[str, Any]]] = None  # 工具列表
    context: Optional[Dict[str, Any]] = field(default_factory=dict)  # 上下文信息

    def to_dict(self) -> Dict[str, Any]:
        """将 AEQuestion 转换为字典格式"""
        result = {"messages": self.messages}
        return result

    def add_tool(self, tool: Dict[str, Any]):
        """添加工具"""
        if self.tools is None:
            self.tools = []
        self.tools.append(tool)

    def add_context(self, key: str, value: Any):
        """添加上下文信息"""
        self.context[key] = value
