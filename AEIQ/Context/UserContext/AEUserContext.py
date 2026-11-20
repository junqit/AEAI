"""
AEUserContext - 单用户的请求入口与隔离单元。

通过 user.user_key 命中对应的本类实例，把请求转交本类处理。
本类持有：用户信息、网络委托、持久事件循环；
Context 的命中/创建/存储与 LLM 回复的分发委托下层完成。
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
    """单用户请求入口：用户隔离 + 事件循环 + 网络/LLM 发送；Context 管理委托给下层。"""

    def __init__(self, user: AEUserInfo, delegate: AENetworkDelegate):
        self.user = user
        self.delegate = delegate
        # Context 命中/创建/存储 + LLM 回复分发
        self._context_center = AEContextCenter(self)
        # 持久事件循环，避免 httpx 连接池在 loop.close() 时报错
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._loop_thread.start()

    # ==================== 接口（请求入口） ====================

    def handle_request(self, request: AENetReq) -> None:
        """处理该用户请求：提交到事件循环异步处理，不阻塞调用方（socket 解析线程）。"""
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


        # context list 无需具体 context
        if path == AE_PATH_CONTEXT_LIST:
            self._context_center.handle_context_list(req)
            return

        # 路径分解：create / chat / chat_list / info，交下层处理（各自内部 resolve）
        if path == AE_PATH_CONTEXT_CREATE:
            self._context_center.handle_create(cont, req)
            return
        if path == AE_PATH_CONTEXT_CHAT:
            self._context_center.handle_chat(cont, req)
            return
        if path == AE_PATH_CONTEXT_CHAT_LIST:
            self._context_center.handle_chat_list(cont, req)
            return
        if path == AE_PATH_CONTEXT_INFO:
            await self._context_center.handle_info(cont, req)
            return

        logger.warning("[AEUserContext] _dispatch: 未处理的 path=%s", path)

    # ==================== 委托实现 ====================
    # 网络请求/回复转发给 delegate；
    # LLM 请求由本类调用客户端，回复交由下层管理中心在本用户内派发。

    def send_request(self, request: AENetReq) -> None:
        """Context 需要发送网络请求时调用，转发给 delegate"""
        request.user = self.user
        self.delegate.send_request(request)

    def send_response(self, response: AENetRsp) -> None:
        """Context 需要发送网络回复时调用，回填 user 后转发给 delegate（req 由各 handle_* 写入）。"""
        response.user = self.user
        self.delegate.send_response(response)

    def send_llm_request(self, payload) -> None:
        """异步发送 LLM 请求：提交到 loop 立即返回（无返回值）；回复到达后由下层派发。"""
        asyncio.run_coroutine_threadsafe(self._do_llm(payload), self._loop)

    async def _do_llm(self, payload) -> None:
        """在 loop 上 await async LLM，回复到达后回填信封并 dispatch 驱动 flow（与请求同在一个异步线程）。"""
        import json
        from ..Context.AELLMClient import send_llm_request
        from Roles.RoleBase.AERoleType import AEConentRole, AE_ROLE
        from WorkFlows.FlowWork.AEFlowInfo import AE_CONTENT
        # system 要求：所有回答必须基于当前用户的实际环境与所提供的数据，不得臆想与瞎说
        payload.messages.insert(0, {
            AE_ROLE: AEConentRole.SYSTEM.value,
            AE_CONTENT: (
                "所有回答必须基于当前用户的实际环境与所提供的上下文、数据：\n"
                "- 不得编造、臆测或凭空生成未经验证的信息\n"
                "- 涉及事实、数据或外部信息时，若用户未提供或无法确认，须明确说明信息不足，不得自行补全\n"
                "- 不得臆想与瞎说"
            ),
        })
        logger.info("📤 发送 LLM:\n%s", json.dumps(payload.messages, ensure_ascii=False, indent=2))
        envelope = await send_llm_request(payload)
        if envelope is None:
            return
        logger.info("📥 接收 LLM:\n%s", json.dumps(envelope, ensure_ascii=False, indent=2, default=str))
        self._context_center.dispatch_llm_response(envelope)
