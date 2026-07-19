"""
AEBaseRole - 角色 Flow 基类。

所有角色 Flow（AEAssistant / AEEmployee / AERefiner / AEWorkGroup 等）继承本类，
在 AEFlow 基础上约定「角色身份」：子类在 __init__ 中设置 self.title（职称）与
self.responsibility（能力范围），由 role_brief 组装为 LLM 的角色定位。

注：本类单独成文件，不并入 Roles.AERole。因为 Roles.AERole（枚举 / 常量）被
WorkFlows.AEFlow 导入，若本类（需 import AEFlow）放入其中会与 AEFlow 形成循环导入。
"""
import logging

from WorkFlows.AEFlow import AEFlow

logger = logging.getLogger(__name__)


class AERole(AEFlow):
    """角色 Flow 基类：所有角色继承本类，约定通过 title / responsibility 声明身份与能力。"""
