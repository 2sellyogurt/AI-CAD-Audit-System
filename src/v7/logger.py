# -*- coding: utf-8 -*-
"""统一日志系统

提供结构化的日志记录，支持文件输出和控制台输出。
"""

import os
import sys
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path

# 日志目录
LOG_DIR = os.environ.get("V7_LOG_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs"))
os.makedirs(LOG_DIR, exist_ok=True)

# 日志格式
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    """获取命名日志记录器。
    
    Args:
        name: 日志记录器名称，通常使用模块名
        
    Returns:
        配置好的日志记录器
    """
    logger = logging.getLogger(name)
    
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.DEBUG)
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(console_handler)
    
    # 文件处理器（按天轮转）
    log_file = os.path.join(LOG_DIR, f"v7_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=30, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(file_handler)
    
    # 错误日志单独文件
    error_file = os.path.join(LOG_DIR, "v7_errors.log")
    error_handler = logging.handlers.RotatingFileHandler(
        error_file, maxBytes=10*1024*1024, backupCount=10, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(error_handler)
    
    return logger
