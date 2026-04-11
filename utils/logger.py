"""
日志系统
提供统一的日志记录和追踪功能
"""

import logging
import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any
import uuid
import json
from pathlib import Path


# 日志颜色
class LogColors:
    """日志颜色定义"""
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器"""

    COLORS = {
        'DEBUG': LogColors.CYAN,
        'INFO': LogColors.GREEN,
        'WARNING': LogColors.YELLOW,
        'ERROR': LogColors.RED,
        'CRITICAL': LogColors.RED + LogColors.BOLD
    }

    def format(self, record):
        # 保存原始 levelname
        original_levelname = record.levelname

        # 添加颜色
        if original_levelname in self.COLORS:
            record.levelname = f"{self.COLORS[original_levelname]}{original_levelname}{LogColors.RESET}"

        # 格式化消息
        result = super().format(record)

        # 恢复原始 levelname（避免影响其他 handler）
        record.levelname = original_levelname

        return result


class TraceLogger:
    """
    追踪日志器
    支持调用链追踪和性能监控
    """

    def __init__(self, logger: logging.Logger, component: str):
        """
        初始化追踪日志器

        Args:
            logger: 日志对象
            component: 组件名称
        """
        self.logger = logger
        self.component = component
        self._trace_id = None
        self._start_times = {}

    def set_trace_id(self, trace_id: str):
        """设置追踪ID"""
        self._trace_id = trace_id

    def get_trace_id(self) -> Optional[str]:
        """获取追踪ID"""
        return self._trace_id

    def _format_message(self, message: str, **kwargs) -> str:
        """格式化日志消息"""
        parts = [f"[{self.component}]"]

        if self._trace_id:
            parts.append(f"[trace:{self._trace_id[:8]}]")

        parts.append(message)

        if kwargs:
            # 格式化额外参数
            extra_parts = []
            for key, value in kwargs.items():
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                extra_parts.append(f"{key}={value}")

            if extra_parts:
                parts.append(f"({', '.join(extra_parts)})")

        return " ".join(parts)

    def debug(self, message: str, **kwargs):
        """DEBUG 级别日志"""
        self.logger.debug(self._format_message(message, **kwargs))

    def info(self, message: str, **kwargs):
        """INFO 级别日志"""
        self.logger.info(self._format_message(message, **kwargs))

    def warning(self, message: str, **kwargs):
        """WARNING 级别日志"""
        self.logger.warning(self._format_message(message, **kwargs))

    def error(self, message: str, **kwargs):
        """ERROR 级别日志"""
        self.logger.error(self._format_message(message, **kwargs))

    def critical(self, message: str, **kwargs):
        """CRITICAL 级别日志"""
        self.logger.critical(self._format_message(message, **kwargs))

    def step(self, step_name: str, message: str, **kwargs):
        """记录步骤"""
        self.info(f"📍 {step_name}: {message}", **kwargs)

    def start(self, operation: str, **kwargs):
        """开始操作"""
        self._start_times[operation] = time.time()
        self.info(f"🚀 开始 {operation}", **kwargs)

    def end(self, operation: str, success: bool = True, **kwargs):
        """结束操作"""
        elapsed = 0
        if operation in self._start_times:
            elapsed = time.time() - self._start_times[operation]
            del self._start_times[operation]

        status = "✅ 成功" if success else "❌ 失败"
        self.info(f"{status} {operation}", elapsed_ms=f"{elapsed*1000:.2f}ms", **kwargs)

    def exception(self, message: str, exc_info=True):
        """记录异常"""
        self.logger.exception(self._format_message(f"💥 异常: {message}"), exc_info=exc_info)


# 全局日志配置
_loggers: Dict[str, TraceLogger] = {}
_log_level = logging.INFO


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    format_string: Optional[str] = None
):
    """
    设置全局日志配置

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径（可选）
        format_string: 自定义格式字符串
    """
    global _log_level

    # 转换日志级别
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    _log_level = level_map.get(level.upper(), logging.INFO)

    # 默认格式
    if format_string is None:
        format_string = "%(asctime)s | %(levelname)s | %(message)s"

    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(_log_level)

    # 清除现有处理器
    root_logger.handlers.clear()

    # 控制台处理器（带颜色）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(_log_level)
    console_formatter = ColoredFormatter(
        format_string,
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器（如果指定）
    if log_file:
        # 确保日志目录存在
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(_log_level)
        file_formatter = logging.Formatter(
            format_string,
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # 禁用第三方库的日志
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def get_logger(component: str) -> TraceLogger:
    """
    获取组件日志器

    Args:
        component: 组件名称

    Returns:
        TraceLogger 实例
    """
    if component not in _loggers:
        logger = logging.getLogger(component)
        logger.setLevel(_log_level)
        _loggers[component] = TraceLogger(logger, component)

    return _loggers[component]


def create_trace_id() -> str:
    """创建追踪ID"""
    return f"trace_{uuid.uuid4().hex[:16]}"


# 便捷函数
def log_function_call(logger: TraceLogger):
    """
    装饰器：记录函数调用

    使用示例:
    @log_function_call(logger)
    def my_function(a, b):
        return a + b
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            func_name = func.__name__
            logger.start(f"函数 {func_name}", args=str(args)[:100], kwargs=str(kwargs)[:100])

            try:
                result = func(*args, **kwargs)
                logger.end(f"函数 {func_name}", success=True)
                return result
            except Exception as e:
                logger.end(f"函数 {func_name}", success=False, error=str(e))
                raise

        return wrapper
    return decorator


# 初始化默认日志配置
setup_logging(level="INFO")


if __name__ == "__main__":
    # 测试日志系统
    print("测试日志系统\n")

    # 设置日志级别为 DEBUG
    setup_logging(level="DEBUG")

    # 创建日志器
    logger = get_logger("TestComponent")

    # 设置追踪ID
    trace_id = create_trace_id()
    logger.set_trace_id(trace_id)

    # 测试各种日志级别
    logger.debug("这是一条调试消息", param1="value1", param2=123)
    logger.info("这是一条信息消息", user="Alice", action="login")
    logger.warning("这是一条警告消息", reason="资源不足")
    logger.error("这是一条错误消息", error_code=500)

    # 测试步骤日志
    logger.step("步骤1", "初始化组件", status="success")
    logger.step("步骤2", "加载数据", count=100)

    # 测试操作追踪
    logger.start("数据处理", input_size=1000)
    time.sleep(0.1)
    logger.end("数据处理", success=True, output_size=900)

    # 测试异常记录
    try:
        raise ValueError("测试异常")
    except Exception:
        logger.exception("捕获到异常")

    print("\n✅ 日志系统测试完成")
