"""
统一日志配置
提供项目级别的日志管理
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime


def setup_logger(
    name: str,
    level: int = logging.INFO,
    log_to_file: bool = False,
    log_dir: str = "logs",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> logging.Logger:
    """
    设置日志记录器

    Args:
        name: 日志记录器名称
        level: 日志级别
        log_to_file: 是否输出到文件
        log_dir: 日志文件目录
        max_bytes: 单个日志文件最大字节数
        backup_count: 保留的日志文件数量

    Returns:
        配置好的 logger 实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件输出
    if log_to_file:
        # 创建日志目录
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # 按日期命名日志文件
        log_filename = os.path.join(
            log_dir,
            f"{name}_{datetime.now().strftime('%Y%m%d')}.log"
        )

        file_handler = RotatingFileHandler(
            log_filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# 日志级别配置
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
}


# 默认日志配置
DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_LOG_TO_FILE = True
DEFAULT_LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")


def get_logger(name: str) -> logging.Logger:
    """
    获取日志记录器（使用默认配置）

    Args:
        name: 日志记录器名称

    Returns:
        配置好的 logger 实例
    """
    return setup_logger(
        name=name,
        level=DEFAULT_LOG_LEVEL,
        log_to_file=DEFAULT_LOG_TO_FILE,
        log_dir=DEFAULT_LOG_DIR
    )


# 预定义的日志记录器
context_logger = get_logger("AEContext")
question_logger = get_logger("AEQuestion")
llm_logger = get_logger("LLM")
cache_logger = get_logger("Cache")


if __name__ == "__main__":
    # 测试日志配置
    test_logger = get_logger("test")

    test_logger.debug("这是一条 DEBUG 消息")
    test_logger.info("这是一条 INFO 消息")
    test_logger.warning("这是一条 WARNING 消息")
    test_logger.error("这是一条 ERROR 消息")
    test_logger.critical("这是一条 CRITICAL 消息")

    print(f"\n日志文件保存在: {DEFAULT_LOG_DIR}")
