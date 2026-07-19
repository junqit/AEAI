"""
AEScript - 脚本 Flow，继承 AEFlow。

不在本类自定义 __init__，直接复用父类 AEFlow 的初始化（需传入 flowOutput 等）。
脚本信息（title / script / type）通过 update_* 方法设置/更新。

每个脚本声明：
  - title：作用（脚本用途说明）
  - script：脚本内容
  - type：脚本类型，取值 python / shell / ruby（AEScriptType）

脚本本身作为 Flow 持有上述信息；执行由外部 Runner 完成，脚本自身不负责执行。
"""
import logging
from enum import Enum

from WorkFlows.AEFlow import AEFlow
from WorkFlows.AEFlowInput import AEFlowInput
from WorkFlows.AEFlowInfo import AE_IDENT, AE_ANSWER

logger = logging.getLogger(__name__)


class AEScriptType(str, Enum):
    """脚本类型常量枚举"""

    python = "python"
    shell = "shell"
    ruby = "ruby"


class AEScript(AEFlow):
    """脚本 Flow：title=作用，script=脚本内容，type=脚本类型(AEScriptType: python/shell/ruby)。

    复用父类 AEFlow.__init__；脚本信息经 update(title, script, type) 设置。
    """

    # 允许的脚本类型（取自 AEScriptType 枚举值）
    VALID_TYPES = tuple(t.value for t in AEScriptType)

    # 脚本信息默认值（title 由父类 AEFlowInfo 初始化为 ""）
    script: str = ""
    type: str = ""

    # 字段意义（供动态创建 / 文档化使用）
    INIT_SCHEMA = {
        "title": "作用（脚本用途说明）",
        "script": "脚本内容",
        "type": "脚本类型，取值 python / shell / ruby 之一",
    }

    def update(self, title: str, script: str, type) -> None:
        """更新脚本信息：title(作用)、script(脚本内容)、type(脚本类型)。

        Args:
            title: 作用（脚本用途说明）。
            script: 脚本内容。
            type: 脚本类型，AEScriptType 枚举或其字符串值（python / shell / ruby）。

        Raises:
            ValueError: type 非法时。
        """
        self.title = title or ""
        self.script = script or ""
        type_value = type.value if isinstance(type, AEScriptType) else type
        if type_value not in self.VALID_TYPES:
            raise ValueError(f"AEScript.type 非法: {type!r}，应为 {self.VALID_TYPES} 之一")
        self.type = type_value

    def startFlow(self, flowInput: AEFlowInput) -> None:
        """启动：执行 self.script（按 type 选 runner），stdout 作为结果回传父 flow。

        传入的 flowInput 仅用于基类置 input / 切 processing；实际执行内容为 self.script。
        完成回程 ident 取 delegate（父 flow）ident，路由回父 flow。

        Args:
            flowInput: flow 输入数据（内容不参与脚本执行，执行内容为 self.script）
        """
        if not super().startFlow(flowInput):
            return
        from .AEScriptRunner import get_runner  # 懒导入避免与 AEScriptRunner 循环
        try:
            runner = get_runner(self.type)
            stdout = runner.run(self.script)
        except Exception as e:
            logger.error("[AEScript:%s] 脚本执行失败(type=%s): %s", self.ident, self.type, e)
            stdout = ""
        # 结果回传父 flow：ident 路由回 delegate，AE_ANSWER 为脚本 stdout
        delegate_ident = self.delegate.ident if self.delegate is not None else self.ident
        self.flow_receive_complete({AE_IDENT: delegate_ident, AE_ANSWER: stdout})
