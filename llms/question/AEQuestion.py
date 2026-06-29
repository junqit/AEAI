from dataclasses import dataclass
from typing import List, Dict, Any
from common.aellm_enums import AELLMType, AEAiLevel  # noqa: F401  (re-export)


@dataclass
class AEQuestion:
    messages: List[Dict[str, Any]]
    llm_type: AELLMType
    level: AEAiLevel = AEAiLevel.default
