"""
API 认证模块
提供基于 API Key 的接口验证
"""

from fastapi import Header, HTTPException, status
from config import config


async def verify_api_key(x_api_key: str = Header(..., description="API Key for authentication")):
    """
    验证 API Key

    Args:
        x_api_key: 从请求头中获取的 API Key

    Raises:
        HTTPException: 如果 API Key 无效或缺失

    Returns:
        str: 验证通过的 API Key
    """
    if x_api_key != config.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return x_api_key


# 可选：更宽松的验证（允许 Query 参数或 Header）
async def verify_api_key_flexible(
    x_api_key: str = Header(None, description="API Key in header"),
    api_key: str = None  # 来自 Query 参数
):
    """
    灵活的 API Key 验证（支持 Header 或 Query 参数）

    Args:
        x_api_key: 从 Header 获取的 API Key
        api_key: 从 Query 参数获取的 API Key

    Raises:
        HTTPException: 如果 API Key 无效或缺失

    Returns:
        str: 验证通过的 API Key
    """
    provided_key = x_api_key or api_key

    if not provided_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key is required (provide via X-API-Key header or api_key query parameter)",
        )

    if provided_key != config.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
        )

    return provided_key
