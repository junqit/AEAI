"""
AEFlowInterfaceImpl - AEFlowInterface 协议方法的实现（静态工具类，不实例化）。

将 AEFlow 的接口实现（startFlow / addFlow / receive_llm_response）从 AEFlow.py 抽出。
本类不创建实例、不作基类；调用方（AEFlow）在薄包装方法中传入自身实例 flow，
由本类完成具体逻辑。receive_flow_result 系列已迁至 AEFlowDelegateImpl。
"""
import logging

from .AEFlowOutput import AE_LLM_OUT
from .AEFlowInfo import AE_IDENT, AEFlowStatus

logger = logging.getLogger(__name__)


class AEFlowInterfaceImpl:
    """AEFlowInterface 协议方法实现（静态工具类，不实例化）。调用方传入 AEFlow 实例 flow。"""

    @staticmethod
    def startFlow(flow, flowInput) -> bool:
        """启动 flow：仅在 default 状态下接收 flowInput，并切换到 processing。

        - 非 default 状态下调用将被忽略，返回 False
        - 接收后置 input、切换到 processing，返回 True（output 已在构造时设置，不再注入）
        - 子类调用 super().startFlow(...) 仅在返回 True 时才进行自己的业务处理
        """
        if flow.status != AEFlowStatus.default:
            logger.warning(
                "[AEFlow:%s][%s] startFlow 仅在 default 状态可接收，当前 %s，忽略",
                flow.ident, flow.title, flow.status,
            )
            return False
        flow.input = flowInput
        flow.status = AEFlowStatus.processing
        return True

    @staticmethod
    def addFlow(flow, sub_flow) -> None:
        """添加子 flow。

        添加前把 sub_flow.delegate 设置为当前 flow（弱引用）；以 sub_flow.ident 为 key 存入有序 map。
        """
        sub_flow.set_delegate(flow)
        flow._flows[sub_flow.ident] = sub_flow

    @staticmethod
    def receive_llm_response(flow, data: dict) -> None:
        """
        接收输入数据（map），按其中的 ident 路由：

          - ident == flow.ident → 本层处理，交 flow_receive_llm
          - ident 命中 _flows 内子 flow → 转发内层 out_schema 给该子 flow（receive_llm_response）
          - ident 既非自身、也未命中子 flow → 打印错误日志

        data 约定为 receive_flow_llm_request 向上转发时的封装形态：{"ident": <目标 ident>, "llm_out": <...>}，
        每层路由消费一层 ident，逐层下传内层 out_schema；最内层叶子无 ident，由该层 flow 自己处理。
        """
        if not isinstance(data, dict):
            logger.error("[AEFlow:%s] 收到的数据非 map，无法解析: %r", flow.ident, data)
            return

        # 取 ident
        ident = data.get(AE_IDENT)

        # ident 命中自身：本层处理（传整个 data）
        if ident == flow.ident:
            flow.flow_receive_llm(data)
            return

        # ident 命中子 flow：转发内层 out_schema 给该子 flow（使用时再获取）
        sub = flow._flows.get(ident) if ident is not None else None
        if sub is not None:
            sub.receive_llm_response(data.get(AE_LLM_OUT))
            return

        # ident 既非自身、也未命中子 flow：打印错误日志
        logger.error(
            "[AEFlow:%s][%s] ident=%r 无法命中（既非自身也未匹配子 flow），忽略: %r",
            flow.ident, flow.title, ident, data,
        )
