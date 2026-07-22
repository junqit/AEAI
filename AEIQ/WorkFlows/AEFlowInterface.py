"""
AEFlowInterface - Flow 接口协议 + AEFlowInterfaceImpl 实例实现（mixin），同文件组织。

- AEFlowInterface（Protocol）：声明所有 Flow 需遵循的接口（ident / status / delegate /
  startFlow / addFlow / receive_llm_response / receive_flow_result）。
- AEFlowInterfaceImpl（mixin）：提供 startFlow / addFlow / receive_llm_response 的实例实现，
  由 AEFlow 继承获得（receive_flow_result 系列在 AEFlowDelegateImpl）。
  与 AEFlowDelegate.py（协议+实现同文件）组织方式一致。
"""
import logging
from typing import Protocol, runtime_checkable, TYPE_CHECKING, Optional

from .AEFlowOutput import AE_LLM_OUT
from .AEFlowInfo import AE_IDENT, AEFlowStatus

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlowInput import AEFlowInput
    from .AEFlowOutput import AEFlowOutput

logger = logging.getLogger(__name__)


@runtime_checkable
class AEFlowInterface(Protocol):
    """Flow 接口协议，所有 flow 需遵循此协议进行实现"""

    ident: str
    status: 'AEFlowStatus'
    delegate: 'AEFlowDelegate'

    def startFlow(self, flowInput: 'AEFlowInput') -> bool:
        """
        启动 flow：仅在 default 状态下接收 flowInput，并将状态切换到 processing。

        - 非 default 状态下调用将被忽略，返回 False
        - 接收后置 input、切换到 processing，返回 True（output 已在构造时设置）
        - 子类调用 super().startFlow(...) 仅在返回 True 时才进行自己的业务处理

        Args:
            flowInput: flow 输入数据

        Returns:
            bool: True 表示已成功启动（状态由 default 切到 processing）；False 表示非 default 状态被忽略
        """
        ...

    def addFlow(self, flow: 'AEFlowInterface') -> None:
        """
        添加子 flow。

        Args:
            flow: 待添加的子 flow，须符合 AEFlowInterface 协议
        """
        ...

    def receive_llm_response(self, data: dict) -> None:
        """
        接收输入数据（map），内部解析处理。

        Flow 在执行前由外部注入输入数据 map，方法内部解析该 map，
        供后续 build_prompt / 生成等使用。

        Args:
            data: 输入数据 map
        """
        ...

    def receive_flow_result(self, data: dict) -> None:
        """
        接收 flow 结果数据（经 receive_flow_complete 按 ident 路由到自身）。

        子类覆写以处理收到的结果数据。

        Args:
            data: 结果数据
        """
        ...


class AEFlowInterfaceImpl:
    """AEFlowInterface 协议方法实现（mixin），由 AEFlow 继承获得这些方法。

    方法内以 self 引用所属 flow（status / input / _flows / ident / flow_receive_llm 等
    均由 AEFlow 及其基类提供）。
    """

    def startFlow(self, flowInput) -> bool:
        """启动 flow：仅在 default 状态下接收 flowInput，并切换到 processing。

        - 非 default 状态下调用将被忽略，返回 False
        - 接收后置 input、切换到 processing，返回 True（output 已在构造时设置，不再注入）
        - 子类调用 super().startFlow(...) 仅在返回 True 时才进行自己的业务处理
        """
        if self.status != AEFlowStatus.default:
            logger.warning(
                "[AEFlow:%s][%s] startFlow 仅在 default 状态可接收，当前 %s，忽略",
                self.ident, self.title, self.status,
            )
            return False
        self.input = flowInput
        self.status = AEFlowStatus.processing
        return True

    def addFlow(self, sub_flow) -> None:
        """添加子 flow。

        添加前把 sub_flow.delegate 设置为当前 flow（弱引用）；以 sub_flow.ident 为 key 存入有序 map。
        """
        sub_flow.set_delegate(self)
        self._flows[sub_flow.ident] = sub_flow

    def receive_llm_response(self, data: dict) -> None:
        """
        接收输入数据（map），按其中的 ident 路由：

          - ident == self.ident → 本层处理，交 flow_receive_llm
          - ident 命中 _flows 内子 flow → 转发内层 out_schema 给该子 flow（receive_llm_response）
          - ident 既非自身、也未命中子 flow → 打印错误日志

        data 约定为 receive_flow_llm_request 向上转发时的封装形态：{"ident": <目标 ident>, "llm_out": <...>}，
        每层路由消费一层 ident，逐层下传内层 out_schema；最内层叶子无 ident，由该层 flow 自己处理。
        """
        if not isinstance(data, dict):
            logger.error("[AEFlow:%s] 收到的数据非 map，无法解析: %r", self.ident, data)
            return

        # 取 ident
        ident = data.get(AE_IDENT)

        # ident 命中自身：本层处理（传整个 data）
        if ident == self.ident:
            self.flow_receive_llm(data)
            return

        # ident 命中子 flow：转发内层 out_schema 给该子 flow（使用时再获取）
        sub = self._flows.get(ident) if ident is not None else None
        if sub is not None:
            sub.receive_llm_response(data.get(AE_LLM_OUT))
            return

        # ident 既非自身、也未命中子 flow：打印错误日志
        logger.error(
            "[AEFlow:%s][%s] ident=%r 无法命中（既非自身也未匹配子 flow），忽略: %r",
            self.ident, self.title, ident, data,
        )
