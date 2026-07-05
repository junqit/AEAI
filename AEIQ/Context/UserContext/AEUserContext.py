"""
AEUserContext - 单用户的请求入口与隔离单元。

AENetRouteCenter 通过 user.user_key 命中对应的本类实例，把请求转交本类处理。
本类持有：用户信息、网络委托（AENetworkDelegate）、持久事件循环；
Context 的命中/创建/存储与 LLM 回复的分发交由 AEContextCenter 完成。
"""
import asyncio
import logging
import threading
import contextvars

from Network.Core import AENetReq, AENetRsp
from Network.Core.AENetReq import AEUserInfo
from Network.Core.AENetRsp import AENetRspCode
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

# 当前请求的 req（按 asyncio task 隔离），send_response 回填进响应，供客户端按 path 路由
_req_ctx: contextvars.ContextVar = contextvars.ContextVar("ae_req")


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
        asyncio.run_coroutine_threadsafe(self._dispatch(request), self._loop)

    async def _dispatch(self, request: AENetReq) -> None:
        """全路径分解后命中/创建 context 并分发（在事件循环内异步执行，无同步阻塞）。"""
        # 关键判断：context 信息
        if not request.cont or not request.cont.type:
            logger.warning("Request has no context info, ignored")
            return

        # 按当前 task 记录 req，供 send_response 回填（并发 task 互不串）
        _req_ctx.set(request.req)
        path = request.req.path if request.req else None
        cont = request.cont

        # context list 无需具体 context
        if path == AE_PATH_CONTEXT_LIST:
            await self._handle_context_list()
            return

        # 路径分解：create / chat / chat_list / info，交 AEContextCenter 异步处理（各自内部 resolve）
        if path == AE_PATH_CONTEXT_CREATE:
            await self._context_center.handle_create(cont)
            return
        if path == AE_PATH_CONTEXT_CHAT:
            await self._context_center.handle_chat(cont)
            return
        if path == AE_PATH_CONTEXT_CHAT_LIST:
            await self._context_center.handle_chat_list(cont)
            return
        if path == AE_PATH_CONTEXT_INFO:
            await self._context_center.handle_info(cont)
            return

        logger.info(f"Unhandled path: {path}")

    # ==================== AEContextDelegate 实现 ====================
    # 网络请求/回复转发给 delegate（AENetworkDelegate）；
    # LLM 请求由本类调用客户端，回复交由 AEContextCenter 在本用户内派发。

    def send_request(self, request: AENetReq) -> None:
        """Context 需要发送 NetReq 时调用，转发给 delegate"""
        request.user = self.user
        self.delegate.send_request(request)

    def send_response(self, response: AENetRsp) -> None:
        """Context 需要发送 NetRsp 时调用，回填 user/req 后转发给 delegate。
        req 取 contextvar（_dispatch 在本 task 内设置），并发 task 互不串。"""
        response.user = self.user
        if response.req is None:
            response.req = _req_ctx.get(None)
        self.delegate.send_response(response)

    def send_llm_request(self, payload) -> None:
        """异步发送 LLM 请求：提交到 loop 立即返回（无返回值）；回复到达后由 AEContextCenter 派发。"""
        asyncio.run_coroutine_threadsafe(self._do_llm(payload), self._loop)

    async def _do_llm(self, payload) -> None:
        """在 loop 上 await async LLM，回复到达后直接 dispatch 驱动 flow（与请求同在一个异步线程）。"""
        from ..Context.AELLMClient import send_llm_request

        reply = await send_llm_request(payload)
        self._context_center.dispatch_llm_response(reply)

    # ==================== 自有方法 ====================

    async def _handle_context_list(self) -> None:
        """返回该用户当前所有 context 配置列表。"""
        contexts = [context.context_config() for context in self._context_center.get_all()]
        response = AENetRsp(
            code=AENetRspCode.success,
            rsp={"contexts": contexts},
        )
        self.send_response(response)
