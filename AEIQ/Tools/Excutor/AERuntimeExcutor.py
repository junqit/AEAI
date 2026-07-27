"""
AERuntimeExcutor - 运行时方法执行器。

维护 funcident -> 脚本字符串 的映射，区分两种注册方式：
  - default：持久默认映射（add_default），不会被 exec 自动清除
  - temporary：临时映射（add_temporary），查找时优先于 default，exec 执行后自动清除

add_default / add_temporary(funcident, script, target)：注册脚本并绑定 target（方法的 self）。
exec(funcident, inner)：按 funcident 取注册项，以绑定的 target 作 'self'、inner 作 'inner' 注入 namespace 后 exec 执行。
"""
import json
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# namespace 键名（同时是脚本内引用的变量名）
AE_SELF = "self"    # 注册时绑定的 target（方法的 self）
AE_INNER = "inner"  # exec 传入的数据
AE_RESULT = "__ae_result__"  # 方法执行结果（脚本内赋值，exec 读取后判断/打印）


class AEFunctional:
    """功能性方法名基类（普通类，定义方法名常量），供子类继承扩展。

    子类（AEFlowFunctional / AEAssistantFunction）可直接访问下列常量，
    也可追加各自的方法名常量。值为字符串方法名，由 executor 经 method_call 拼成脚本调用。
    """
    flow_receive_default = "flow_receive_default"        # 回包置 default
    flow_receive_processing = "flow_receive_processing"  # 回包置 processing
    flow_receive_complete = "flow_receive_complete"      # 回包置 complete 并赋值最终结果


@dataclass
class _Entry:
    """注册项：脚本 + 绑定的 target（方法的 self）。"""
    script: str
    target: object


class AERuntimeExcutor:
    """运行时方法执行器：funcident -> 脚本 映射，区分 default / temporary 注册。"""

    def __init__(self):
        # 默认注册（持久）
        self._default: Dict[str, _Entry] = {}
        # 临时注册（优先于 default，exec 后自动清除）
        self._temporary: Dict[str, _Entry] = {}

    # ==================== 注册 ====================

    def add_default(self, funcident: str, script: str, target) -> None:
        """默认方式注册：持久映射，不会被 exec 自动清除。

        Args:
            funcident: 方法标识（字符串键）
            script: 功能性方法名（字符串），内部经 method_call 拼成脚本
            target: 方法的 self，执行时作为 AE_SELF 注入 namespace
        """
        self._default[funcident] = _Entry(self.method_call(script), target)

    def add_temporary(self, funcident: str, method: str, target) -> None:
        """临时方式注册：优先于 default，exec 执行后自动清除。

        Args:
            funcident: 方法标识（字符串键）
            method: 功能性方法名（字符串），内部经 method_call 拼成脚本
            target: 方法的 self，执行时作为 AE_SELF 注入 namespace
        """
        self._temporary[funcident] = _Entry(self.method_call(method), target)

    def remove_default(self, funcident: str) -> None:
        """移除默认注册。"""
        self._default.pop(funcident, None)

    def remove_temporary(self, funcident: str) -> None:
        """移除临时注册（未执行也会清除）。"""
        self._temporary.pop(funcident, None)

    def clear_temporary(self) -> None:
        """清空全部临时注册。"""
        self._temporary.clear()

    # ==================== 查询 ====================

    def get(self, funcident: str) -> Tuple[Optional[_Entry], bool]:
        """取注册项：temporary 优先，其次 default。

        Returns:
            (entry, is_temporary)：未注册时 (None, False)
        """
        if funcident in self._temporary:
            return self._temporary[funcident], True
        if funcident in self._default:
            return self._default[funcident], False
        return None, False

    def contains(self, funcident: str) -> bool:
        """是否已注册（default 或 temporary）。"""
        return funcident in self._temporary or funcident in self._default

    # ==================== 执行 ====================

    @staticmethod
    def method_call(method: str) -> str:
        """拼接默认方法调用脚本：__ae_result__ = self.<method>(inner)。

        将方法返回值赋给 AE_RESULT，供 exec 读取后判断/打印。
        用 AE_SELF / AE_INNER / AE_RESULT 常量拼接，避免脚本与 namespace 键名漂移。
        """
        return f"{AE_RESULT} = {AE_SELF}.{method}({AE_INNER})"

    def exec(self, funcident: str, inner):
        """按 funcident 查找注册项并 exec 执行，获取方法返回结果并判断/打印。

        注册时绑定的 target 作为 AE_SELF 注入，inner 作为 AE_INNER 直接注入 namespace；
        方法返回值经 AE_RESULT 取回，按 bool 判断执行状态并打印日志；temporary 注册执行后自动清除。

        Args:
            funcident: 方法标识
            inner: 传入数据，注入 namespace 的 AE_INNER

        Returns:
            方法的执行结果（通常为 bool：True=当前数据处理完成，False/其他=未完成或异常）

        Raises:
            KeyError: funcident 未注册
        """
        entry, is_temporary = self.get(funcident)
        if entry is None:
            raise KeyError(f"未注册的 funcident: {funcident!r}")
        namespace = {AE_SELF: entry.target, AE_INNER: inner}
        exec(entry.script, namespace)
        # 获取方法执行结果并判断/打印
        result = namespace.get(AE_RESULT)
        if result is not True:
            logger.warning("[AERuntimeExcutor] funcident=%s 执行未完成: result=%r", funcident, result)
        # temporary 执行后清除，避免残留
        if is_temporary:
            self._temporary.pop(funcident, None)
        return result
