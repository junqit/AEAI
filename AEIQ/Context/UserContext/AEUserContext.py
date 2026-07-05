"""
AEUserContext - 单用户的 Context 管理中心。

接收该用户传来的 AENetReq，负责相关 context 的创建与存储、context list 处理，
并分发到对应 Context 处理。AENetRouteCenter 通过 user.user_key 命中对应的本类实例，
把请求转交本类处理。每个 AEUserContext 持有自己的持久事件循环。
本类已按用户隔离，内部 context 表只需 ident -> AEBaseContext。
"""
import asyncio
import json
import logging
import threading
from typing import Dict, Optional

from Network.Core import AENetReq, AENetRsp
from Network.Core.AENetReq import AEUserInfo
from Network.Core.AENetRsp import AENetRspCode
from ..Context.AEBaseContext import AEBaseContext
from ..Context.AEContextDelegate import AENetworkDelegate
from ..Context.AEContextPath import AE_PATH_CONTEXT_LIST
from ..Context.AEContextType import AEContextType
from ..Context.AEPermissionContext import AEPermissionContext
from ..Context.AEDirectoryContext import AEDirectoryContext
from ..Context.AEWorkSpaceContext import AEWorkSpaceContext

logger = logging.getLogger(__name__)


class AEUserContext:
    """单用户的 Context 管理中心：创建/存储/分发该用户的 contexts，持有独立事件循环。"""

    _SINGLETON_TYPES = {AEContextType.directory, AEContextType.permission}

    def __init__(self, user: AEUserInfo, delegate: AENetworkDelegate):
        self.user = user
        self.delegate = delegate
        # context_ident -> AEBaseContext（本类已按用户隔离，无需再按 user_key 分层）
        self._user_contexts: Dict[str, AEBaseContext] = {}
        # 持久事件循环，避免 httpx 连接池在 loop.close() 时报错
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._loop_thread.start()
        logger.info(f"AEUserContext initialized - user_key={user.user_key if user else None}")

    # ==================== 接口（请求入口） ====================

    def handle_request(self, request: AENetReq) -> None:
        """处理该用户请求：关键判断后处理 context list；否则获取/创建 context 并在其上执行。"""
        # 关键判断：context 信息
        if not request.cont or not request.cont.type:
            logger.warning("Request has no context info, ignored")
            return

        # context list 路径（放在关键判断之后）
        path = request.req.path if request.req else None
        if path == AE_PATH_CONTEXT_LIST:
            self._handle_context_list(request)
            return

        # 先通过 cont.ident 获取已有 context 实例
        context = None
        if request.cont.ident:
            context = self._get_context(request.cont.ident)

        # 获取不到，通过 cont.type 创建新 context
        if context is None:
            space = request.cont.space or ""
            if request.cont.type == AEContextType.workspace.value and not space:
                logger.warning("Cannot create WorkSpaceContext: space is required")
                return
            context = self._create_context(request.cont.type, user=request.user, space=space)

        if context is None:
            return

        future = asyncio.run_coroutine_threadsafe(context.handle_request(request), self._loop)
        future.result()

    # ==================== AEContextDelegate 实现 ====================
    # 网络请求/回复转发给 delegate（AENetworkDelegate）；
    # LLM 请求由本类自行调用客户端并在本用户内派发，不经 delegate。

    def send_request(self, request: AENetReq) -> None:
        """Context 需要发送 NetReq 时调用，转发给 delegate"""
        request.user = self.user
        self.delegate.send_request(request)

    def send_response(self, response: AENetRsp) -> None:
        """Context 需要发送 NetRsp 时调用，转发给 delegate"""
        response.user = self.user
        self.delegate.send_response(response)

    def send_llm_request(self, payload) -> str:
        """发送 LLM 请求，收到回复后在本用户内按 ident 路由到对应 Context"""
        from ..Context.AELLMClient import send_llm_request as _send_llm

        reply = _send_llm(payload)
        self._dispatch_llm_response(reply)
        return reply

    def _dispatch_llm_response(self, reply: str) -> None:
        """解析 LLM 回复 JSON，按其中的 ident 把数据传给本用户内对应 Context"""
        if not reply:
            logger.warning("LLM 回复为空，跳过 dispatch")
            return
        try:
            data = json.loads(self._strip_code_fence(reply))
        except (ValueError, TypeError) as e:
            logger.error(f"[{self.user.user_key}] LLM 回复非合法 JSON: {e}, reply={reply!r}")
            return
        if not isinstance(data, dict):
            logger.error(f"[{self.user.user_key}] LLM 回复非 JSON 对象: {reply!r}")
            return
        ident = data.get("ident")
        if not ident:
            logger.error(f"[{self.user.user_key}] LLM 回复缺少 ident: {data!r}")
            return
        context = self._find_context_by_ident(ident)
        if context is None:
            logger.error(f"[{self.user.user_key}] 未找到 ident={ident!r} 的 Context，丢弃 LLM 回复")
            return
        context.receive_llm_response(data)

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

    # ==================== 自有方法 ====================

    def _handle_context_list(self, request: AENetReq) -> None:
        """返回该用户当前所有 context 配置列表。"""
        contexts = [context.context_config() for context in self._user_contexts.values()]
        response = AENetRsp(
            code=AENetRspCode.success,
            rsp={"contexts": contexts},
            req=request.req,
            user=request.user,
        )
        self.delegate.send_response(response)

    def _get_context(self, context_ident: str) -> Optional[AEBaseContext]:
        return self._user_contexts.get(context_ident)

    def _create_context(self, context_type_str: str, user=None, space: str = "") -> Optional[AEBaseContext]:
        try:
            context_type = AEContextType(context_type_str)
        except ValueError:
            logger.warning(f"Unknown context type: {context_type_str}")
            return None

        if context_type in self._SINGLETON_TYPES:
            existing = self._find_context_by_type(context_type)
            if existing:
                return existing

        context_map = {
            AEContextType.permission: AEPermissionContext,
            AEContextType.directory: AEDirectoryContext,
            AEContextType.workspace: AEWorkSpaceContext,
        }

        context = context_map[context_type](user=user, space=space)
        context.set_delegate(self)

        self._user_contexts[context.ident] = context
        logger.info(
            f"Context created: user_key={self.user.user_key}, ident={context.ident}, "
            f"type={context_type_str}({context_type!r})"
        )
        return context

    def _find_context_by_type(self, context_type: AEContextType) -> Optional[AEBaseContext]:
        for context in self._user_contexts.values():
            if context.context_type == context_type:
                return context
        return None

    def _find_context_by_ident(self, context_ident: str) -> Optional[AEBaseContext]:
        """在本 AEUserContext 内按 ident 查找 context。"""
        return self._user_contexts.get(context_ident)

    def get_contexts(self):
        """返回该用户下所有 context。"""
        return list(self._user_contexts.values())
