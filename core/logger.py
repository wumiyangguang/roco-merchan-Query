"""统一日志配置模块。

通过环境变量 ROCOM_LOG_LEVEL 控制日志级别（默认 INFO）。
设为 DEBUG 可输出详细调试信息。
"""
import logging
import os
import sys

# 默认日志格式：时间 [级别] [模块] 消息
_LOG_FORMAT = "%(asctime)s [%(levelname)-5s] [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _build_console_handler() -> logging.Handler:
    """创建控制台日志处理器（stdout）。"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    return handler


def _resolve_level() -> int:
    """从环境变量读取日志级别，默认 INFO。"""
    raw = os.getenv("ROCOM_LOG_LEVEL", "INFO").strip().upper()
    try:
        return getattr(logging, raw)
    except AttributeError:
        return logging.INFO


_initialized = False


def setup_logging() -> None:
    """初始化根日志器（幂等，只执行一次）。"""
    global _initialized
    if _initialized:
        return

    root = logging.getLogger()
    root.setLevel(_resolve_level())
    # 避免重复添加 handler
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(_build_console_handler())

    _initialized = True
