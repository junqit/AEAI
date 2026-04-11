"""
AEIQ 配置文件

集中管理 AEIQ 工程的所有配置项
"""
import os


class AEIQConfig:
    """AEIQ 配置类"""

    # LLM 服务配置
    LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://localhost:9999")
    LLM_SERVICE_TIMEOUT = 60  # 请求超时时间（秒）

    # 会话管理配置
    SESSION_TIMEOUT = 3600  # 会话超时时间（秒），默认 1 小时

    # 线程池配置
    EXECUTOR_MAX_WORKERS = 4  # 并发调用 LLM 的最大线程数

    # FastAPI 配置
    APP_TITLE = "AEIQ API"
    APP_DESCRIPTION = "AI Agent with Multi-LLM Support via HTTP"
    APP_VERSION = "3.0.0"

    # 服务端口配置
    AEIQ_PORT = 8000  # AEIQ 服务端口

    @classmethod
    def get_llm_service_url(cls) -> str:
        """获取 LLM 服务地址"""
        return cls.LLM_SERVICE_URL

    @classmethod
    def get_session_timeout(cls) -> int:
        """获取会话超时时间"""
        return cls.SESSION_TIMEOUT

    @classmethod
    def get_executor_max_workers(cls) -> int:
        """获取线程池最大工作线程数"""
        return cls.EXECUTOR_MAX_WORKERS

    @classmethod
    def get_llm_service_timeout(cls) -> int:
        """获取 LLM 服务请求超时时间"""
        return cls.LLM_SERVICE_TIMEOUT


# 创建全局配置实例
config = AEIQConfig()
