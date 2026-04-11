from enum import Enum


class AESkillType(str, Enum):

    AE_SKILL_TYPE_ATOMIC = "AE_SKILL_TYPE_ATOMIC"
    AE_SKILL_TYPE_COMPOSITE = "AE_SKILL_TYPE_COMPOSITE"


class AESkillType(str, Enum):

    AE_SKILL_NAME_FILE = "AE_SKILL_NAME_FILE"

class AESkill:

    type: AESkillType
    name: AESkillType
    description: str

    input_schema: dict = {}

    def run(self, input_data):
        raise NotImplementedError
    
    def llmInputSchema():
        return ""