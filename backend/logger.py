#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一日志模块
提供全项目一致的日志格式和输出
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 日志目录
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 日志格式
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 全局 logger 实例
_loggers = {}


def get_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    console: bool = True
) -> logging.Logger:
    """
    获取或创建 logger 实例

    Args:
        name: logger 名称，通常用模块名 __name__
        level: 日志级别，默认 INFO
        log_file: 日志文件名，默认使用 name.log
        console: 是否输出到控制台，默认 True

    Returns:
        配置好的 logger 实例
    """
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    # 避免重复添加 handler
    if logger.handlers:
        _loggers[name] = logger
        return logger

    # 控制台 handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    # 文件 handler
    if log_file is None:
        log_file = f"{name.split('.')[-1]}.log"

    file_path = LOG_DIR / log_file
    file_handler = RotatingFileHandler(
        file_path,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)  # 文件记录 DEBUG 及以上
    file_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    _loggers[name] = logger
    return logger


# 便捷函数：快速获取模块 logger
def get_module_logger(module_name: str) -> logging.Logger:
    """获取模块 logger，等同于 get_logger(__name__)"""
    return get_logger(module_name)


# 预配置的常用 logger
pdf2latex_logger = get_logger("pdf2latex", logging.INFO, "pdf2latex.log")
client_logger = get_logger("clients", logging.INFO, "clients.log")
parser_logger = get_logger("parser", logging.INFO, "parser.log")
app_logger = get_logger("app", logging.INFO, "app.log")