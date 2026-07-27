"""AgentForge — 日志系统

贯穿所有模块的结构化日志记录。
"""

import logging
import sys
from pathlib import Path

LOG_DIR = Path.home() / ".cache" / "agentforge" / "logs"
_LOG_INITIALIZED = False


def setup_logger(name: str = "agentforge", level=logging.INFO) -> logging.Logger:
    """初始化并获取一个日志记录器

    Args:
        name: 日志器名称
        level: 日志级别

    Returns:
        配置好的 Logger 实例
    """
    global _LOG_INITIALIZED
    logger = logging.getLogger(name)

    if _LOG_INITIALIZED:
        return logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(level)

    # 控制台 Handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(console)

    # 文件 Handler
    fh = logging.FileHandler(
        LOG_DIR / f"{name}.log",
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s",
    ))
    logger.addHandler(fh)

    _LOG_INITIALIZED = True
    return logger


def get_logger(name: str = "agentforge") -> logging.Logger:
    """获取已存在的日志器"""
    return logging.getLogger(name)
