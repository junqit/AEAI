from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class AELLMPayload:
    messages: List[Dict[str, str]]
    llm_type: str = "chatgpt"
    level: str = "default"
    system: Optional[str] = None

    def to_dict(self) -> dict:
        data = {
            "messages": self.messages,
            "llm_type": self.llm_type,
            "level": self.level,
        }
        if self.system:
            data["system"] = self.system
        return data
