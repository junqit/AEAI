"""
AEBaseRole - 角色 Flow 基类。

所有角色 Flow 继承本类。单独成文件以避免与 WorkFlows.AEFlow 循环导入
（Roles.AERole 被 AEFlow 导入，本类需 import AEFlow）。
"""
import logging
from typing import Optional

from WorkFlows.AEFlow import AEFlow
from Roles.AERole import AERoleParamInfo

logger = logging.getLogger(__name__)


class AERole(AEFlow):
    """角色 Flow 基类。"""

    roleParamInfo: Optional[AERoleParamInfo] = None
