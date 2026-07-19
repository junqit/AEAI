"""
AEFlow - Flow 基类，同时实现 AEFlowInterface 与 AEFlowDelegate 两个协议。

AEFlowInterface 实现（flow 自身接口）：
  - ident / delegate（属性）
  - receive_llm_response()   接收输入数据
  - addFlow()                  添加子 flow

AEFlowDelegate 实现（子 flow 通过本类向外流转）：
  - flow_llm_request()                 发送 AELLMPayload 调用 LLM
  - flow_complete()            Flow 完成，整理结果
"""
import json
import logging
import weakref
from typing import Dict, Optional, TYPE_CHECKING

from .AEFlowInfo import AEFlowInfo, AEFlowStatus, AE_IDENT, AE_ANSWER, AE_funcationkey
from .AEFlowInput import AEFlowInput
from .AEFlowOutput import AEFlowOutput, AE_LLM_OUT
from Context.Context.AELLMPayload import AELLMPayload, llm_generate
from Roles.AERole import AEConentRole, AE_USER_QUESTION_PREFIX, AE_ROLE, AE_CONTENT
from Excutor import AERuntimeExcutor
from Excutor.AERuntimeExcutor import AEFunctional


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .AEFlowDelegate import AEFlowDelegate
    from .AEFlowInterface import AEFlowInterface


class AEFlowFunctional(AEFunctional):
    """Flow 通用回包功能性方法名（继承 AEFunctional 的 flow_receive_* 常量，可按需扩展）。"""
    receiveRole = "receiveRole"                            # 接收 LLM 生成的自身工作名称与能力范围，传入 map
    receiveOptimizePrompt = "receiveOptimizePrompt"        # 接收 LLM 基于 title+能力 生成的问题优化提示，传入 map
    receiveOptimizeInputOptimize = "receiveOptimizeInputOptimize"  # 接收 LLM 综合上下文返回的最终结果，传入 map


class AEFlow(AEFlowInfo):
    """Flow 基类，继承 AEFlowInfo，实现 AEFlowInterface 与 AEFlowDelegate 协议"""

    def __init__(self, flowOutput: AEFlowOutput, ident: str = "", flowInput: Optional[AEFlowInput] = None):
        # ----- AEFlowInfo 属性 -----
        # ident 可传入（默认空，为空则内部生成）；外部只读；
        # output（本 flow 输出结构）创建时必传；input 可在初始化时传入（默认 None），未传时由 startFlow 设置
        super().__init__(flowOutput=flowOutput, ident=ident, flowInput=flowInput)
        # delegate：AEFlowDelegate，Flow 内部信息向外流转的出口
        self.delegate: "Optional[AEFlowDelegate]" = None
        # ----- 内部状态 -----
        self._flows: "Dict[str, AEFlowInterface]" = {}  # 有序 map，key 为 flow.ident
        # 方法执行器：管理 functional -> 脚本映射，区分 default / temporary；
        # 默认不注册任何方法，由业务子类自行 add_default / add_temporary 添加
        self.excutor = AERuntimeExcutor()

    # ==================== AEFlowInterface 实现 ====================

    def set_delegate(self, delegate: "AEFlowDelegate") -> None:
        """注入 delegate（弱引用持有，避免与子 flow 形成循环引用）"""
        self.delegate = weakref.proxy(delegate) if delegate is not None else None

    def startFlow(self, flowInput: AEFlowInput) -> bool:
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

    def receive_llm_response(self, data: dict) -> None:
        """
        接收输入数据（map），按其中的 ident 路由：

          - ident == self.ident → 本层处理，交 flow_receive_llm
            （子类在 flow_receive_llm 中处理收到的数据）
          - ident 命中 _flows 内子 flow → 转发内层 out_schema 给该子 flow（receive_llm_response）
          - ident 既非自身、也未命中子 flow → 打印错误日志

        data 约定为 flow_llm_request 向上转发时的封装形态：{"ident": <目标 ident>, "llm_out": <...>}，
        每层路由消费一层 ident，逐层下传内层 out_schema；最内层叶子无 ident，由该层 flow 自己处理。

        Args:
            data: 输入数据 map（含 ident / out_schema）
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
        flow = self._flows.get(ident) if ident is not None else None
        if flow is not None:
            flow.receive_llm_response(data.get(AE_LLM_OUT))
            return

        # ident 既非自身、也未命中子 flow：打印错误日志
        logger.error(
            "[AEFlow:%s][%s] ident=%r 无法命中（既非自身也未匹配子 flow），忽略: %r",
            self.ident, self.title, ident, data,
        )

    def flow_receive_llm(self, out_schema: "Optional[dict]") -> None:
        """
        收到经 receive_llm_response 路由到自身、已解析出的 out_schema 数据。

        按 out_schema 内的 AE_funcationkey 字段从 self.excutor 取对应脚本并执行；
        该 key 由发送方 flowOutput 注册时随机生成，对应一个 flow_receive_* 方法。

        out_schema 内无 AE_funcationkey 字段、或其值未在 excutor 内注册时，打印错误信息并忽略。
        子类可经 excutor.add_default / add_temporary 自定义处理，或覆写各 flow_receive_* 方法；
        temporary 注册执行后由 excutor 自动清除。

        Args:
            out_schema: 从输入 map 中解析出的 out_schema 数据（含 AE_funcationkey / llm_out 字段）
        """
        if not isinstance(out_schema, dict):
            logger.error("[AEFlow:%s] out_schema 非 map，忽略: %r", self.ident, out_schema)
            return
        command = out_schema.get(AE_funcationkey)
        # 真正交给业务处理的内容在 llm_out 下（out_schema 形如 {ident, title, funcationkey, llm_out: <内容>}）
        inner = out_schema.get(AE_LLM_OUT)
        if not self.excutor.contains(command):
            logger.error(
                "[AEFlow:%s][%s] out_schema 内 funcationkey=%r 无效或缺失，忽略: %r",
                self.ident, self.title, command, out_schema,
            )
            return
        # inner 直接传入；target 在注册时已绑定为 self，temporary 执行后由 excutor 自动清除
        self.excutor.exec(command, inner)

    def flow_receive_default(self, out_schema: "Optional[dict]") -> bool:
        """
        status=default：收到结果数据，置本 flow 状态为 default。子类可覆写做业务处理。

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        self.status = AEFlowStatus.default
        return True

    def flow_receive_processing(self, out_schema: "Optional[dict]") -> bool:
        """
        status=processing：收到结果数据，置本 flow 状态为 processing。子类可覆写做业务处理。

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        self.status = AEFlowStatus.processing
        return True

    def flow_receive_complete(self, out_schema: "Optional[dict]") -> bool:
        """
        status=complete：收到结果数据，置本 flow 状态为 complete，赋值最终结果，并通过 delegate.flow_complete 通知返回。

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        self.status = AEFlowStatus.complete
        self.outResult = out_schema
        if self.delegate is not None:
            self.delegate.flow_complete(out_schema, AEFlowStatus.complete)
        return True

    @property
    def outResult_summary(self) -> str:
        """从 outResult 中提取总结内容（AE_ANSWER），并附带角色说明。

        形如「我是一名{title}，{responsibility}。我的回答：{answer}」；
        title / responsibility 均为空时省略角色前缀，仅返回「我的回答：{answer}」。
        """
        answer = self._extract_answer(self.outResult) or ""
        if len(self.title) > 0 or len(self.responsibility) > 0:
            return f"我是一名{self.title}，{self.responsibility}。我的回答：{answer}"
        return f"我的回答：{answer}"

    def requestOptimizePrompt(self) -> None:
        """组装并发送 LLM 请求：仅带自身名称(title)与能力(responsibility)，
        让 LLM 据此生成一段「问题优化提示」——该提示用于引导 LLM 对用户输入的问题做进一步优化。

        - messages: system(role_brief，含身份与能力) / user(生成问题优化提示的指令)
        - out_schema: {AE_ANSWER: 问题优化提示 占位}，由 LLM 填充
        - 走 receiveOptimizePrompt：回包后赋值 optimizePromptResult（不完成 flow）

        注：本步仅依据 title + 能力生成提示，不传入用户问题；用户问题留待后续步骤用该提示进一步优化。
        """
        messages = []
        role_brief = self.role_brief
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "请根据你的标题与能力，生成一段「问题优化提示」；该提示将用于引导 LLM 对用户输入的问题"
                "做进一步优化（更清晰、更完整、更易于理解）。提示需体现你的专业角色与能力范围，"
                "且不依赖任何具体用户问题，仅给出通用的优化方向与约束。"
            ),
        })
        flow_out = self.flowOutput(AEFlowFunctional.receiveOptimizePrompt)
        flow_out.set_llm_out({AE_ANSWER: llm_generate("问题优化提示，用于引导对用户问题做进一步优化")})
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveOptimizePrompt(self, data: dict) -> bool:
        """接收 LLM 生成的问题优化提示（不完成 flow，仅存储供后续使用）。

        Args:
            data: 回包内层 llm_out，形如 {AE_ANSWER: <生成的问题优化提示>}

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        prompt = self._extract_answer(data) if isinstance(data, dict) else None
        if prompt is None and isinstance(data, str):
            prompt = data
        self.optimizePromptResult = prompt or ""
        logger.info(
            "[AEFlow:%s][%s] 收到问题优化提示:\n%s",
            self.ident, self.title, self.optimizePromptResult,
        )
        # 收到提示词后，用其作为输入上下文发起下一步 LLM 请求，得到最终结果
        self.requestOptimizeInputOptimize()
        return True

    def requestOptimizeInputOptimize(self) -> None:
        """综合自身 title/能力(role_brief)、optimizePromptResult 与 input.content 发送 LLM 请求，得到结果。

        - messages: system(role_brief) / system(input.content) / user(optimizePromptResult)，每条信息单独一条消息
        - out_schema: 本 flow 的输出结构（output 已在构造时设置），由 LLM 填充最终结果
        - 走 receiveOptimizeInputOptimize：回包仅打印结果（不完成 flow）
        """
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
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveOptimizeInputOptimize(self, data: dict) -> bool:
        """接收 LLM 返回的最终结果，仅打印（不完成 flow、不写 outResult）。

        Args:
            data: 回包内层 llm_out，形如 {AE_ANSWER: <最终结果>}；若直接为字符串则视为结果

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        result = self._extract_answer(data) if isinstance(data, dict) else None
        if result is None and isinstance(data, str):
            result = data
        logger.info(
            "[AEFlow:%s][%s] 收到最终结果:\n%s",
            self.ident, self.title, result or "",
        )
        return True

    def requestRoleInfo(self) -> None:
        """根据问题内容(input.content)请求 LLM 生成自身工作名称(title)与能力范围(responsibility)。

        - messages: system(role_brief，含已有身份与能力，可为空) / user(问题内容 + 生成角色指令)
        - out_schema: {title, responsibility 占位}，由 LLM 填充
        - 走 receiveRole：回包后写入 self.title / self.responsibility（不完成 flow）
        """
        messages = []
        role_brief = self.role_brief
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: (
                "请根据以下问题内容，生成你的工作名称与能力范围；工作名称需体现专业领域与定位，"
                f"能力范围需明确职责边界与禁止事项。\n问题内容：{self.input.content if self.input else ''}"
            ),
        })
        flow_out = self.flowOutput(AEFlowFunctional.receiveRole)
        flow_out.set_llm_out({
            "title": llm_generate("工作名称，体现专业领域与定位"),
            "responsibility": llm_generate("能力范围，明确职责边界与禁止事项"),
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)

    def receiveRole(self, data: dict) -> bool:
        """接收 LLM 生成的自身工作名称与能力范围，写入 title / responsibility（不完成 flow）。

        Args:
            data: 回包内层 llm_out，形如 {"title": <工作名称>, "responsibility": <能力范围>}

        Returns:
            bool: 当前数据处理是否完成（True=已处理）
        """
        if not isinstance(data, dict):
            data = {}
        self.title = data.get("title", "") or ""
        self.responsibility = data.get("responsibility", "") or ""
        logger.info(
            "[AEFlow:%s] 收到角色信息:\ntitle=%r\nresponsibility=%r",
            self.ident, self.title, self.responsibility,
        )
        return True

    @staticmethod
    def _extract_answer(obj) -> Optional[str]:
        """递归查找 obj 内首个 AE_ANSWER 键的值。"""
        if isinstance(obj, dict):
            if AE_ANSWER in obj:
                return obj[AE_ANSWER]
            for v in obj.values():
                r = AEFlow._extract_answer(v)
                if r is not None:
                    return r
        return None

    def addFlow(self, flow: "AEFlowInterface") -> None:
        """
        添加子 flow。

        添加前把 flow.delegate 设置为当前 flow（弱引用）；
        以 flow.ident 为 key 存入有序 map。

        Args:
            flow: 待添加的 flow，须符合 AEFlowInterface 协议
        """
        flow.set_delegate(self)
        self._flows[flow.ident] = flow

    def nextFlow(self) -> "Optional[AEFlowInterface]":
        """
        获取下一个待执行的子 flow：按 addFlow 顺序首个状态为 default 的子 flow。

        Returns:
            AEFlowInterface: 首个 default 状态的子 flow；均非 default 时返回 None
        """
        for flow in self._flows.values():
            if flow.status == AEFlowStatus.default:
                return flow
        return None

    def send_llm_payload(self, payload: "AELLMPayload") -> None:
        """
        通过 delegate 发送 AELLMPayload（无返回值）。

        校验 delegate 后，用 ident / title 包装 payload.out_schema 向上转发
        （回程按 ident 路由回本 flow）。

        Args:
            payload: AELLMPayload 结构体

        Raises:
            RuntimeError: delegate 未设置时
        """
        if self.delegate is None:
            raise RuntimeError("AEFlow delegate 未设置，无法发送 LLM 请求")
        # 外层信封：ident / title 用于回程路由，llm_out 包装内层内容
        payload.out_schema = {
            AE_IDENT: self.ident,
            "title": self.title,
            AE_LLM_OUT: payload.out_schema,
        }
        self.delegate.flow_llm_request(payload)

    # ==================== AEFlowDelegate 实现 ====================

    def flow_llm_request(self, payload: "AELLMPayload") -> None:
        """
        发送 AELLMPayload 调用 LLM（无返回值）。

        AEFlow 自身不持有 LLM 客户端，真实发送由外层 delegate（具体 AEFlowDelegate 实现，
        如 AENetRouteCenter 适配器）完成。本方法校验 delegate 后，用当前 flow 的 ident / title
        包装 payload.out_schema，再向上转发（回程按 ident 路由回本 flow）。

        Args:
            payload: AELLMPayload 结构体

        Raises:
            RuntimeError: delegate 未设置时
        """
        if self.delegate is None:
            raise RuntimeError("AEFlow delegate 未设置，无法发送 LLM 请求")
        # 用当前 flow 的 ident / title 包装 payload.out_schema
        payload.out_schema = {
            AE_IDENT: self.ident,
            "title": self.title,
            AE_LLM_OUT: payload.out_schema,
        }
        self.delegate.flow_llm_request(payload)

    def flow_complete(self, result: dict, flowStatus: "AEFlowStatus") -> None:
        """
        Flow 完成通知：仅处理 complete，按 result.ident 路由结果数据。

        - ident == self.ident → 确认是本 flow 需处理的内容，交 receive_flow_result
        - ident 命中 _flows 内子 flow → 转发给该子 flow（receive_flow_result）

        非 complete 状态（default / processing）忽略并记录告警。

        Args:
            result: 完成 flow 的结果数据（含 ident）
            flowStatus: 完成 flow 的状态
        """
        if flowStatus != AEFlowStatus.complete:
            logger.warning(
                "[AEFlow:%s][%s] flow_complete 仅处理 complete，当前 %s，忽略",
                self.ident, self.title, flowStatus,
            )
            return
        ident = result.get(AE_IDENT) if isinstance(result, dict) else None
        logger.info(
            "[recv][AEFlow:%s][%s] flow_complete ident=%r, result:\n%s",
            self.ident, self.title, ident, json.dumps(result, ensure_ascii=False, indent=2, default=str),
        )
        # 确认是本 flow 需处理的内容：ident 命中自身 → 交 receive_flow_result
        if ident == self.ident:
            self.receive_flow_result(result)
            return
        # ident 命中子 flow：转发结果数据给该子 flow
        flow = self._flows.get(ident) if ident is not None else None
        if flow is not None:
            flow.receive_flow_result(result.get(AE_LLM_OUT))
            return
        logger.warning(
            "[AEFlow:%s][%s] ident=%r 既非自身也未命中子 flow，忽略: %r",
            self.ident, self.title, ident, result,
        )

    def receive_flow_result(self, out_schema: "Optional[dict]") -> None:
        """
        收到经 flow_complete 路由到自身、确认由本 flow 处理的结果数据。

        判断所有子 flow 是否全部 complete：
        - 未全部 complete：把 AE_ANSWER 内容组装成 flowInput，交给首个 default 状态子 flow startFlow
        - 全部 complete：汇总所有子 flow 的 outResult 交 LLM 生成最终答案

        Args:
            out_schema: 结果数据（含 AE_ANSWER 字段）
        """
        answer = out_schema.get(AE_ANSWER) if isinstance(out_schema, dict) else None
        # 判断所有子 flow 是否全部 complete
        all_complete = all(f.status == AEFlowStatus.complete for f in self._flows.values())
        if not all_complete:
            self._advance_next_flow(answer)
            return

        self._summarize_to_llm()

    def _advance_next_flow(self, answer: Optional[str]) -> None:
        """未全部 complete：把 answer 组装成 flowInput，交给首个 default 状态子 flow startFlow。"""
        flow_input = AEFlowInput(content=answer or "")
        next_flow = self.nextFlow()
        if next_flow is not None:
            next_flow.startFlow(flow_input)
        else:
            logger.warning(
                "[AEFlow:%s][%s] 未全部 complete 但无 default 状态子 flow，无法继续",
                self.ident, self.title,
            )

    def _summarize_to_llm(self) -> None:
        """全部 complete：汇总所有子 flow 的 outResult 放入 messages，交 LLM 生成最终答案。

        问题已由上游（如 AERefiner）具象化，此处不再带原始 input.content。
        """
        flow_out = self.flowOutput(AEFlowFunctional.flow_receive_complete)
        messages = []
        role_brief = self.role_brief
        if len(role_brief) > 0:
            messages.append({AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: role_brief})
        # 把所有子 flow 的 outResult 总结内容放入 messages
        for f in self._flows.values():
            if f.outResult is not None:
                messages.append({
                    AE_ROLE: AEConentRole.SYSTEM.value,
                    AE_CONTENT: f.outResult_summary,
                })
        messages.append({
            AE_ROLE: AEConentRole.USER.value,
            AE_CONTENT: f"以上内容中，{AE_USER_QUESTION_PREFIX}为用户问题；请基于所有提供的回答仔细思考，针对该用户问题输出结论",
        })
        payload = AELLMPayload(messages=messages, out_schema=flow_out.out_schema)
        self.send_llm_payload(payload)
