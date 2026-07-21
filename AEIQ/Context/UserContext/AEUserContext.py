"""
AEUserContext - 单用户的请求入口与隔离单元。

AENetRouteCenter 通过 user.user_key 命中对应的本类实例，把请求转交本类处理。
本类持有：用户信息、网络委托（AENetworkDelegate）、持久事件循环；
Context 的命中/创建/存储与 LLM 回复的分发交由 AEContextCenter 完成。
"""
import asyncio
import logging
import threading

from Network.Core import AENetReq, AENetRsp
from Network.Core.AENetReq import AEUserInfo
from ..Context.AEContextDelegate import AENetworkDelegate
from ..Context.AEContextPath import (
    AE_PATH_CONTEXT_LIST,
    AE_PATH_CONTEXT_CREATE,
    AE_PATH_CONTEXT_CHAT,
    AE_PATH_CONTEXT_CHAT_LIST,
    AE_PATH_CONTEXT_INFO,
)
from .AEContextCenter import AEContextCenter

logger = logging.getLogger(__name__)


class AEUserContext:
    """单用户请求入口：用户隔离 + 事件循环 + 网络/LLM 发送；Context 管理委托给 AEContextCenter。"""

    def __init__(self, user: AEUserInfo, delegate: AENetworkDelegate):
        self.user = user
        self.delegate = delegate
        # Context 命中/创建/存储 + LLM 回复分发
        self._context_center = AEContextCenter(self)
        # 持久事件循环，避免 httpx 连接池在 loop.close() 时报错
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._loop_thread.start()
        logger.info(f"AEUserContext initialized - user_key={user.user_key if user else None}")

    # ==================== 接口（请求入口） ====================

    def handle_request(self, request: AENetReq) -> None:
        """处理该用户请求：提交到事件循环异步处理，不阻塞调用方（socket 解析线程）。"""
        logger.info("[AEUserContext] handle_request: 提交到事件循环, user=%s, path=%s",
                    request.user.user_key if request.user else None,
                    request.req.path if request.req else None)
        asyncio.run_coroutine_threadsafe(self._dispatch(request), self._loop)

    async def _dispatch(self, request: AENetReq) -> None:
        """全路径分解后命中/创建 context 并分发（在事件循环内异步执行，无同步阻塞）。"""
        # 关键判断：context 信息
        if not request.cont or not request.cont.type:
            logger.warning("[AEUserContext] _dispatch: 无 context 信息, cont=%r, 忽略", request.cont)
            return

        path = request.req.path if request.req else None
        cont = request.cont
        req = request.req

        logger.info("[AEUserContext] _dispatch: path=%s, cont_type=%s, cont_ident=%s, cont_space=%s",
                    path, cont.type, cont.ident, cont.space)

        # context list 无需具体 context
        if path == AE_PATH_CONTEXT_LIST:
            logger.info("[AEUserContext] → handle_context_list")
            self._context_center.handle_context_list(req)
            return

        # 路径分解：create / chat / chat_list / info，交 AEContextCenter 处理（各自内部 resolve）
        if path == AE_PATH_CONTEXT_CREATE:
            logger.info("[AEUserContext] → handle_create")
            self._context_center.handle_create(cont, req)
            return
        if path == AE_PATH_CONTEXT_CHAT:
            logger.info("[AEUserContext] → handle_chat")
            self._context_center.handle_chat(cont, req)
            return
        if path == AE_PATH_CONTEXT_CHAT_LIST:
            logger.info("[AEUserContext] → handle_chat_list")
            self._context_center.handle_chat_list(cont, req)
            return
        if path == AE_PATH_CONTEXT_INFO:
            logger.info("[AEUserContext] → handle_info")
            await self._context_center.handle_info(cont, req)
            return

        logger.warning("[AEUserContext] _dispatch: 未处理的 path=%s", path)

    # ==================== AEContextDelegate 实现 ====================
    # 网络请求/回复转发给 delegate（AENetworkDelegate）；
    # LLM 请求由本类调用客户端，回复交由 AEContextCenter 在本用户内派发。

    def send_request(self, request: AENetReq) -> None:
        """Context 需要发送 NetReq 时调用，转发给 delegate"""
        request.user = self.user
        self.delegate.send_request(request)

    def send_response(self, response: AENetRsp) -> None:
        """Context 需要发送 NetRsp 时调用，回填 user 后转发给 delegate（req 由各 handle_* 写入）。"""
        response.user = self.user
        self.delegate.send_response(response)

    def send_llm_request(self, payload) -> None:
        """异步发送 LLM 请求：提交到 loop 立即返回（无返回值）；回复到达后由 AEContextCenter 派发。"""
        asyncio.run_coroutine_threadsafe(self._do_llm(payload), self._loop)

    async def _do_llm(self, payload) -> None:
        """在 loop 上 await async LLM，回复到达后回填信封并 dispatch 驱动 flow（与请求同在一个异步线程）。"""
        from ..Context.AELLMClient import send_llm_request

        envelope = await send_llm_request(payload)
        if envelope is None:
            return
        self._context_center.dispatch_llm_response(envelope)
