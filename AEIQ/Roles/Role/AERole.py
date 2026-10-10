"""AERole - 角色信息属性基类。

持有角色相关属性（role / title / responsibility / rolePrompt），经 cooperative __init__ 初始化。
"""
import logging
from typing import Optional

from Roles.Role.AERoleType import AERoleParamInfo

logger = logging.getLogger(__name__)


class AERole:
    """角色信息属性基类：持有角色相关属性，经 cooperative __init__ 初始化。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 角色层级：None 表示未归属分解层级；非 None 表示归属具体层级。
        self.role: Optional[AERoleParamInfo] = None
        # ----- 角色信息（角色专属）-----
        self.title: str = ""             # 职称
        self.responsibility: str = ""    # 职责要求
        self.rolePrompt: str = ""        # 角色 prompt

    def print_info(self) -> None:
        """打印基础信息：角色描述、title/responsibility、问题（content）、goal。"""
        role_desc = ""
        if self.role is not None:
            role_desc = f"{self.role.role.value}（{self.role.title}：{self.role.responsibility}）"
        inp = getattr(self, "input", None)
        question = inp.get_content() if inp is not None else ""
        goal = inp.get_goal() if inp is not None else ""
        logger.info(
            "[%s][d=%s] 基础信息:\n"
            "========================================\n"
            "  角色描述: %s\n"
            "  title: %s\n"
            "  responsibility: %s\n"
            "  问题: %s\n"
            "  goal: %s\n"
            "========================================",
            getattr(self, "title", ""), getattr(self, "deepth", 0),
            role_desc, self.title, self.responsibility, question, goal,
        )
