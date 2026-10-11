from typing import Dict, Optional
import logging

from Network.Core import AENetReq, AENetRsp
from Network.Socket.Connection.AESocketListener import AESocketInterface
from ..UserContext.AEUserContext import AEUserContext

logger = logging.getLogger(__name__)


class AENetRouteCenter:
    """
    网络路由中心：接收网络请求，按 user.user_key 命中/创建用户上下文并转交；
    同时作为网络委托，为用户上下文提供网络请求/回复的发送出口。
    LLM 请求与回程路由由各用户上下文自行处理。
    """

    def __init__(self, socket_interface: Optional[AESocketInterface] = None):
        self._socket_interface = socket_interface
        # userKey -> 用户上下文：收到网络请求后按 user.user_key 命中/创建并存储
        self.userCenters: Dict[str, AEUserContext] = {}

    # ==================== 接口实现 ====================

    def on_request_received(self, request: AENetReq) -> None:
        """按 user.user_key 命中/创建用户上下文，转交请求。"""
        if not request.user:
            logger.warning("Request has no user info, ignored")
            return

        try:
            user_key = request.user.user_key
        except ValueError:
            logger.warning("Request user has no uid, ignored")
            return


        center = self.userCenters.get(user_key)
        if center is None:
            center = AEUserContext(request.user, self)
            self.userCenters[user_key] = center
            logger.info("[AENetRouteCenter] 用户连接: user_key=%s", user_key)

        center.handle_request(request)

    # ==================== 网络委托实现 ====================

    def send_request(self, request: AENetReq) -> None:
        """Context 需要发送网络请求时调用"""
        if self._socket_interface:
            self._socket_interface.send_request(request)

    def send_response(self, response: AENetRsp) -> None:
        """Context 需要发送网络回复时调用"""
        if self._socket_interface:
            self._socket_interface.send_response(response)
