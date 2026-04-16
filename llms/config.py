"""
配置文件
"""

import os
from typing import Optional


class Config:
    """服务配置"""

    # 服务配置
    SERVICE_NAME: str = "Agent API"
    VERSION: str = "2.0.0"
    DESCRIPTION: str = "AI Agent with Router, Skills, MCP, RAG"

    # 服务器配置
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "9999"))
    RELOAD: bool = os.getenv("RELOAD", "true").lower() == "true"

    # 日志配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")

    # CORS 配置
    CORS_ORIGINS: list = ["*"]  # 生产环境应限制具体域名

    # API 配置
    API_PREFIX: str = "/api/v1"  # 可选的 API 前缀

    # LLM 配置
    # 支持: local, claude, chatgpt, deepseek
    LLM_BACKEND: str = os.getenv("LLM_BACKEND", "local")
    LLM_API_KEY: Optional[str] = os.getenv("LLM_API_KEY")
    LLM_MODEL: Optional[str] = os.getenv("LLM_MODEL")
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "256"))

    # RAG 配置（待集成）
    RAG_ENABLED: bool = os.getenv("RAG_ENABLED", "false").lower() == "true"
    RAG_INDEX_PATH: Optional[str] = os.getenv("RAG_INDEX_PATH")

    # MCP 配置（待集成）
    MCP_ENABLED: bool = os.getenv("MCP_ENABLED", "false").lower() == "true"

    # API 认证配置
    API_KEY: str = os.getenv("API_KEY", "ae-agent-2024-fixed-key-9527")  # 固定的 API Key
    API_KEY_HEADER: str = "AE-API-Key"  # HTTP Header 名称

    @classmethod
    def get_config(cls) -> dict:
        """获取配置字典"""
        return {
            "service_name": cls.SERVICE_NAME,
            "version": cls.VERSION,
            "description": cls.DESCRIPTION,
            "host": cls.HOST,
            "port": cls.PORT,
            "reload": cls.RELOAD,
            "log_level": cls.LOG_LEVEL,
        }


# 创建配置实例
config = Config()
