"""
日志管理模块

提供统一的日志记录功能。
"""
import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime


class Logger:
    """日志管理器"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._setup_logger()

    def _setup_logger(self):
        """设置日志系统"""
        # Create logs directory
        logs_dir = Path.home() / ".findSameVideo" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Create logger
        self.logger = logging.getLogger("findSameVideo")
        self.logger.setLevel(logging.DEBUG)

        # Prevent duplicate handlers
        if self.logger.handlers:
            return

        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )

        # File handler - debug level (rotating)
        log_file = logs_dir / f"findSameVideo_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        self.logger.addHandler(file_handler)

        # Console handler - info level
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(simple_formatter)
        self.logger.addHandler(console_handler)

        # Error file handler - error level only
        error_log_file = logs_dir / "errors.log"
        error_handler = RotatingFileHandler(
            error_log_file,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        self.logger.addHandler(error_handler)

        self.logger.info("日志系统初始化完成")

    def debug(self, message: str):
        """记录调试信息"""
        self.logger.debug(message)

    def info(self, message: str):
        """记录一般信息"""
        self.logger.info(message)

    def warning(self, message: str):
        """记录警告信息"""
        self.logger.warning(message)

    def error(self, message: str, exc_info: bool = False):
        """记录错误信息"""
        self.logger.error(message, exc_info=exc_info)

    def critical(self, message: str, exc_info: bool = False):
        """记录严重错误信息"""
        self.logger.critical(message, exc_info=exc_info)

    def set_level(self, level: str):
        """设置日志级别"""
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        self.logger.setLevel(level_map.get(level.upper(), logging.INFO))

    def get_logger(self) -> logging.Logger:
        """获取原始 logger 对象"""
        return self.logger


# 全局日志实例
logger = Logger()


def get_logger() -> Logger:
    """获取日志管理器实例"""
    return logger


def debug(message: str):
    """快捷方式：记录调试信息"""
    logger.debug(message)


def info(message: str):
    """快捷方式：记录一般信息"""
    logger.info(message)


def warning(message: str):
    """快捷方式：记录警告信息"""
    logger.warning(message)


def error(message: str, exc_info: bool = False):
    """快捷方式：记录错误信息"""
    logger.error(message, exc_info=exc_info)


def critical(message: str, exc_info: bool = False):
    """快捷方式：记录严重错误信息"""
    logger.critical(message, exc_info=exc_info)
