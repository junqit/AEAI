"""AERole - 角色信息属性基类（继承 AEFlow，角色即 flow）。

持有角色相关属性（role / title / responsibility / rolePrompt），经 cooperative __init__ 初始化。
"""
import logging
from typing import Optional

from WorkFlows.FlowWork.AEFlow import AEFlow
from Roles.RoleBase.AERoleType import AERoleParamInfo

logger = logging.getLogger(__name__)


class AERole(AEFlow):
    """角色信息属性基类（继承 AEFlow，角色即 flow）：持有角色相关属性，经 cooperative __init__ 初始化。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 角色层级：None 表示未归属分解层级；非 None 表示归属具体层级。
        self.role: Optional[AERoleParamInfo] = None
        # ----- 角色信息（角色专属）-----
        self.title: str = ""             # 职称
        self.responsibility: str = ""    # 职责要求
        self.rolePrompt: str = ""        # 角色 prompt
        # 背景确认控制：True 表示跳过自身背景确认（被派发的背景确认子 flow 置 True，避免递归）
        self.skip_context_confirm: bool = False

    # 打印基础信息：角色描述、deepth、title/responsibility、问题与任务
    def print_info(self) -> None:
        role_desc = ""
        if self.role is not None:
            role_desc = f"{self.role.role.value}（{self.role.title}：{self.role.responsibility}）"
        inp = getattr(self, "input", None)
        question = inp.get_content() if inp is not None else ""
        goal = inp.get_goal() if inp is not None else ""
        deepth = getattr(self, "deepth", 0)
        logger.info(
            "[%s][d=%s] 基础信息:\n"
            "========================================\n"
            "  角色描述: %s\n"
            "  deepth: %s\n"
            "  title: %s\n"
            "  responsibility: %s\n"
            "  问题: %s\n"
            "  明确的任务: %s\n"
            "========================================",
            getattr(self, "title", ""), deepth,
            role_desc, deepth, self.title, self.responsibility, question, goal,
        )
