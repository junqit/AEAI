"""
AEContextCenter - 单用户内的 Context 管理中心。

负责该用户下 AEContext 的命中与创建/存储/查找，以及 LLM 回复的解析与按 ident 路由回对应 Context。
由 AEUserContext 持有：AEUserContext 负责用户隔离、事件循环、网络与 LLM 请求发送，
本类只依赖 AEContextDelegate（即 AEUserContext）——Context 的回调与所需 user 信息均经 delegate 获取。
"""
import os
import json
import asyncio
import platform
import logging
from typing import Dict, Optional

from Network.Core import AENetReq
from Network.Core.AENetReq import AENetCont, AENetReqInfo
from Network.Core.AENetRsp import AENetRsp, AENetRspCode
from ..Context.AEBaseContext import AEBaseContext
from ..Context.AEContextDelegate import AEContextDelegate
from ..Context.AEContextType import AEContextType
from ..Context.AEPermissionContext import AEPermissionContext
from ..Context.AEDirectoryContext import AEDirectoryContext
from ..Context.AEWorkSpaceContext import AEWorkSpaceContext
from WorkFlows.AEFlowOutput import AE_LLM_OUT
from WorkFlows.AEFlow import AE_IDENT
from WorkFlows.AEFlowInfo import AE_TITLE

logger = logging.getLogger(__name__)


class AEContextCenter(AEContextDelegate):
    """单用户内 Context 的命中/创建/存储/查找 + LLM 回复分发。

    实现 AEContextDelegate：作为各子 Context 的直接 delegate，
    将 NetReq / NetRsp / LLM 请求转发给上层 delegate（AEUserContext）。
    """

    _SINGLETON_TYPES = {AEContextType.directory, AEContextType.permission}

    def __init__(self, delegate: AEContextDelegate):
        # delegate（AEUserContext）：作为子 Context 的委托（网络/LLM 回调），并提供 user 信息
        self._delegate = delegate
        # context_ident -> AEBaseContext
        self._contexts: Dict[str, AEBaseContext] = {}

    # ==================== AEContextDelegate 实现（转发给上层 AEUserContext） ====================

    def send_request(self, request: AENetReq) -> None:
        """转发 NetReq 给上层 delegate。"""
        self._delegate.send_request(request)

    def send_response(self, response: AENetRsp) -> None:
        """转发 NetRsp 给上层 delegate。"""
        self._delegate.send_response(response)

    def send_llm_request(self, payload) -> None:
        """转发 LLM 请求给上层 delegate；注入 DirectoryContext 的环境参数 prompt。"""
        # 获取 DirectoryContext，注入 payload 携带的环境参数（env_params）prompt
        directory = self.find_by_type(AEContextType.directory)
        if directory is not None:
            from Roles.AERole import AEConentRole, AE_ROLE, AE_CONTENT
            for env_param in reversed(list(payload.env_params)):
                prompt = directory.build_env_param_prompt(env_param)
                if prompt:
                    payload.messages.insert(0, {AE_ROLE: AEConentRole.SYSTEM.value, AE_CONTENT: prompt})
        # 打印完整 LLM 请求
        logger.info("[AEContextCenter] === 发送 LLM 请求 ===\nmessages:\n%s\nout_schema:\n%s",
                     json.dumps(payload.messages, ensure_ascii=False, indent=2),
                     json.dumps(payload.out_schema, ensure_ascii=False, indent=2))
        self._delegate.send_llm_request(payload)

    # ==================== Context 命中与创建 ====================

    def resolve_context(self, cont: Optional[AENetCont]) -> Optional[AEBaseContext]:
        """按 cont.ident 命中已有 context；命中不到则按 cont.type 创建。"""
        if cont is None or not cont.type:
            logger.warning("[AEContextCenter] resolve_context: 无 context 信息, 忽略")
            return None

        logger.info("[AEContextCenter] resolve_context: type=%s, ident=%s, space=%s", cont.type, cont.ident, cont.space)

        # 先按 ident 命中
        if cont.ident:
            existing = self._contexts.get(cont.ident)
            if existing is not None:
                logger.info("[AEContextCenter] 命中已有 context: ident=%s, type=%s", cont.ident, existing.context_type)
                return existing

        # 命中不到则按 type 创建
        space = cont.space or ""
        if cont.type == AEContextType.workspace.value and not space:
            logger.warning("[AEContextCenter] 无法创建 WorkSpaceContext: space 为空")
            return None
        logger.info("[AEContextCenter] 未命中, 按 type 创建: type=%s, space=%s", cont.type, space)
        return self._create_context(cont.type, space=space)

    def get_all(self) -> list:
        """返回该用户下所有 context。"""
        return list(self._contexts.values())

    def find_by_ident(self, context_ident: str) -> Optional[AEBaseContext]:
        """按 ident 查找 context。"""
        return self._contexts.get(context_ident)

    def find_by_type(self, context_type: AEContextType) -> Optional[AEBaseContext]:
        """按 type 查找 context。"""
        for context in self._contexts.values():
            if context.context_type == context_type:
                return context
        return None

    def _create_context(self, context_type_str: str, space: str = "") -> Optional[AEBaseContext]:
        try:
            context_type = AEContextType(context_type_str)
        except ValueError:
            logger.warning("[AEContextCenter] _create_context: 未知 context type=%s", context_type_str)
            return None

        if context_type in self._SINGLETON_TYPES:
            existing = self.find_by_type(context_type)
            if existing:
                logger.info("[AEContextCenter] _create_context: 单例已存在, 复用 type=%s, ident=%s", context_type, existing.ident)
                return existing

        context_map = {
            AEContextType.permission: AEPermissionContext,
            AEContextType.directory: AEDirectoryContext,
            AEContextType.workspace: AEWorkSpaceContext,
        }

        # Context 回调设给本 AEContextCenter（由其转发给上层 AEUserContext）
        context = context_map[context_type](space=space)
        context.set_delegate(self)

        self._contexts[context.ident] = context
        logger.info("[AEContextCenter] _create_context: 创建成功 type=%s, ident=%s, space=%s",
                     context_type, context.ident, space)
        return context

    # ==================== Path 处理（收 cont，经 delegate 发响应） ====================

    def handle_context_list(self, req: AENetReqInfo) -> None:
        """返回该用户下所有 context 配置列表。"""
        contexts = [context.context_config() for context in self.get_all()]
        response = AENetRsp(
            code=AENetRspCode.success,
            rsp={"contexts": contexts},
            req=req,
        )
        self._delegate.send_response(response)

    def handle_create(self, cont: AENetCont, req: AENetReqInfo) -> None:
        """创建/命中 context，返回其基础信息。"""
        context = self.resolve_context(cont)
        if context is None:
            return
        response = AENetRsp(
            code=AENetRspCode.success,
            cont=AENetCont(
                type=cont.type if cont else None,
                ident=context.ident,
                space=context.space,
            ),
            req=req,
        )
        self._delegate.send_response(response)

    def handle_chat(self, cont: AENetCont, req: AENetReqInfo) -> None:
        """处理 chat：交 workspace 接收（receive_chat 内部异步流转，不等回）；
        回复由 Chat 处理完成后 Context 内部自行处理，不在此处回复。"""
        logger.info("[AEContextCenter] handle_chat: 开始, cont_type=%s, cont_ident=%s", cont.type if cont else None, cont.ident if cont else None)
        context = self.resolve_context(cont)
        if context is None:
            logger.warning("[AEContextCenter] handle_chat: resolve_context 返回 None, 无法处理")
            return

        if not isinstance(context, AEWorkSpaceContext):
            logger.warning("[AEContextCenter] handle_chat: chat 仅支持 WorkSpace, 当前 type=%s", context.context_type)
            return

        question = cont.ques if cont else None
        logger.info("[AEContextCenter] handle_chat: 交 workspace receive_chat, question=%r", question.content if question else None)
        context.receive_chat(question, req)

    def handle_chat_list(self, cont: AENetCont, req: AENetReqInfo) -> None:
        """返回 workspace 下的 chat 列表；cont 用该 workspace 配置（含 space）。"""
        context = self.resolve_context(cont)
        if context is None:
            return

        chats = []
        if isinstance(context, AEWorkSpaceContext):
            chats = [
                {AE_IDENT: c.ident, AE_TITLE: c.title, "status": c.status.value}
                for c in context._chat_map.values()
            ]
        response = AENetRsp(
            code=AENetRspCode.success,
            rsp={"data": {"chats": chats}},
            cont=AENetCont(
                type=context.context_type.value,
                ident=context.ident,
                space=context.space,
            ),
            req=req,
        )
        self._delegate.send_response(response)

    async def handle_info(self, cont: AENetCont, req: AENetReqInfo) -> None:
        """返回 directory 的系统/脚本环境信息（脚本扫描丢线程池，不阻塞 loop）。"""
        context = self.resolve_context(cont)
        if context is None:
            return

        info: dict = {}
        if isinstance(context, AEDirectoryContext):
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(None, AEContextCenter._build_info, context)
        response = AENetRsp(
            code=AENetRspCode.success,
            rsp=info,
            cont=cont,
            req=req,
        )
        self._delegate.send_response(response)

    @staticmethod
    def _build_info(context: AEDirectoryContext) -> dict:
        """组装 directory 系统信息（同步，供 run_in_executor 调用）。"""
        return {
            "system": platform.system(),
            "node": platform.node(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cwd": os.getcwd(),
            "scripts": context._discover_scripts(),
        }

    # ==================== LLM 回复接收与分发 ====================

    def dispatch_llm_response(self, reply: str) -> None:
        """解析 LLM 回复 JSON，按其中的 ident 把数据传给本用户内对应 Context。"""
        if not reply:
            logger.warning("LLM 回复为空，跳过 dispatch")
            return
        stripped = self._strip_code_fence(reply)
        try:
            data = json.loads(stripped)
        except (ValueError, TypeError) as e:
            logger.error("[AEContextCenter] JSON 解析失败: %s\nreply(前2000字符)=%s", e, reply[:2000])
            return
        if not isinstance(data, dict):
            logger.error(f"LLM 回复非 JSON 对象: {reply!r}")
            return
        ident = data.get(AE_IDENT)
        if not ident:
            logger.error(f"LLM 回复缺少 ident: {data!r}")
            return
        context = self.find_by_ident(ident)
        if context is None:
            logger.error(f"未找到 ident={ident!r} 的 Context，丢弃 LLM 回复")
            return
        # 剥掉第一层（context.ident），把内层 llm_out 传给 context，由各层逐层解析本层数据
        context.receive_llm_response(data.get(AE_LLM_OUT))

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        """去掉 LLM 回复可能包裹的 ```json ... ``` 代码块围栏"""
        t = text.strip()
        if t.startswith("```"):
            lines = t.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            t = "\n".join(lines)
        return t
