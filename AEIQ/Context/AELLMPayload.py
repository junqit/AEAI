from dataclasses import dataclass
from typing import List, Dict


@dataclass
class AELLMPayload:
    messages: List[Dict[str, str]]
    llm_type: str = "claude"
    level: str = "default"

    def to_dict(self) -> dict:
        return {
            "messages": self.messages,
            "llm_type": self.llm_type,
            "level": self.level,
        }
