
from Agents.skills.AESkill import AESkill

class AESkillCenter:

    def __init__(self):
        self.skills = {}

    def register(self, skill: AESkill):
        self.skills[skill.name] = skill

    def skill(self, name: str):
        return self.skills[name]

aeSkillCenter = AESkillCenter()