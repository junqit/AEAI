"""
AEFlowInterfaceImpl - AEFlowInterface 协议方法的实现（静态工具类，不实例化）+
AEFlowOptimizeQuestion - AEFlow 的父类（问题优化相关 LLM 请求方法）。

AEFlowInterfaceImpl：将 AEFlow 的接口实现（startFlow / addFlow / receive_llm_response）
从 AEFlow.py 抽出。本类不创建实例、不作基类；调用方（AEFlow）在薄包装方法中传入自身实例 flow，
由本类完成具体逻辑。receive_flow_result 系列已迁至 AEFlowDelegateImpl。

AEFlowOptimizeQuestion：AEFlow 的父类，提供 requestOptimizeInputOptimize /
receiveOptimizeInputOptimize；AEFlow 多继承本类。AEFlowFunctional 在方法内懒导入避免循环。
"""
import logging
from typing import Optional, TYPE_CHECKING

from .AEFlowOutput import AE_LLM_OUT
from .AEFlowInfo import AEFlowInfo, AE_IDENT, AE_ANSWER, AE_CONFIRM, AEFlowStatus
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Roles.AERole import AEConentRole, AE_ROLE, AE_CONTENT

if TYPE_CHECKING:
    pass

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


class AEFlowOptimizeQuestion(AEFlowInfo):
    """AEFlow 父类：问题优化相关 LLM 请求方法（requestOptimizeInputOptimize / receiveOptimizeInputOptimize）。"""

    def requestOptimizeInputOptimize(self) -> None:
        """综合自身 title/能力(role_brief)、optimizePromptResult 与 input.content 发送 LLM 请求，得到结果。

        - messages: system(role_brief) / system(input.content) / user(optimizePromptResult)，每条信息单独一条消息
        - out_schema: 本 flow 的输出结构（output 已在构造时设置），由 LLM 填充最终结果
        - 走 receiveOptimizeInputOptimize：回包仅打印结果（不完成 flow）
        """
        from WorkFlows.AEFlow import AEFlowFunctional  # 懒导入避免循环
        messages = []
        # system：身份与能力(role_brief)，单独一条
        role_brief = self.role_brief
        if len(role_brief) > 0:
            messages.append({
                AE_ROLE: AEConentRole.SYSTEM.value,
                AE_CONTENT: role_brief,
            })
        # system：用户问题(input.content)，单独一条
        if self.input is not None and self.input.content:
            messages.append({
                AE_ROLE: AEConentRole.SYSTEM.value,
                AE_CONTENT: f"用户问题：\n{self.input.content}",
            })
        # user：问题优化提示(optimizePromptResult)，作为优化指引
        if len(self.optimizePromptResult) > 0:
            messages.append({
                AE_ROLE: AEConentRole.USER.value,
                AE_CONTENT: self.optimizePromptResult,
            })
        # out_schema 由 flowOutput 构建（注册功能 + 标准结构），不复用当前 flow 的 output
        flow_out = self.flowOutput(AEFlowFunctional.receiveOptimizeInputOptimize)
        # llm_out：最终结果(AE_ANSWER) 与 需确认信息(AE_CONFIRM) 二选一，不可同时填写
        flow_out.set_llm_out({
            AE_ANSWER: llm_generate("依据经验给出的问题"),
            # AE_CONFIRM: llm_generate("需要提问者确认的信息；根据自身工作范围填写，不要超出职责范围，要有界限；与 reply 二选一，给出确认信息时 reply 留空，无确认需求时本字段留空"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveOptimizeInputOptimize(self, data: dict) -> bool:
        """接收 LLM 返回的最终结果，仅打印（不完成 flow、不写 outResult）。

        解析结论中是否含「需要提问者确认的信息」(AE_CONFIRM 字段)：非空则记录为待确认。

        Args:
            data: 回包内层 llm_out，形如 {AE_ANSWER: <最终结果>, AE_CONFIRM: <需确认信息>}；
                  若直接为字符串则视为结果

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        result = data.get(AE_ANSWER) if isinstance(data, dict) else None
        if result is None and isinstance(data, str):
            result = data
        # 解析是否含有需要用户确认的信息
        confirm = data.get(AE_CONFIRM) if isinstance(data, dict) else None
        confirm = (confirm or "").strip() if isinstance(confirm, str) else ""
        if confirm:
            logger.info(
                "[AEFlow:%s][%s] 收到最终结果:\n%s\n[需要用户确认] %s",
                self.ident, self.title, result or "", confirm,
            )
        else:
            logger.info(
                "[AEFlow:%s][%s] 收到最终结果:\n%s",
                self.ident, self.title, result or "",
            )
        return True
