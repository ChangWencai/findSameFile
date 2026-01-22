"""
自定义异常类

定义项目中使用的所有异常类型，提供更好的错误处理和调试体验。
"""
from typing import Optional, List
from pathlib import Path


class FindSameVideoError(Exception):
    """项目基础异常类"""

    def __init__(self, message: str, details: Optional[str] = None):
        self.message = message
        self.details = details
        super().__init__(self.format_message())

    def format_message(self) -> str:
        """格式化错误消息"""
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class FileScanError(FindSameVideoError):
    """文件扫描异常"""

    def __init__(
        self,
        message: str,
        path: Optional[str] = None,
        original_error: Optional[Exception] = None
    ):
        self.path = path
        self.original_error = original_error
        details = f"path={path}" if path else None
        if original_error:
            details = f"{details}, original={type(original_error).__name__}" if details else str(original_error)
        super().__init__(message, details)


class PermissionDeniedError(FileScanError):
    """权限拒绝异常"""

    def __init__(self, path: str, reason: str = "无访问权限"):
        super().__init__(f"权限被拒绝: {path}", path=path)
        self.reason = reason


class HashCalculationError(FileScanError):
    """哈希计算异常"""

    def __init__(self, path: str, reason: str):
        super().__init__(f"哈希计算失败: {reason}", path=path)


class FileNotFoundError(FileScanError):
    """文件未找到异常"""

    def __init__(self, path: str):
        super().__init__(f"文件不存在: {path}", path=path)


class CacheError(FindSameVideoError):
    """缓存操作异常"""

    def __init__(self, message: str, db_path: Optional[str] = None):
        details = f"db={db_path}" if db_path else None
        super().__init__(message, details)
        self.db_path = db_path


class ConfigError(FindSameVideoError):
    """配置异常"""

    def __init__(self, message: str, config_key: Optional[str] = None):
        details = f"key={config_key}" if config_key else None
        super().__init__(message, details)
        self.config_key = config_key


class ValidationError(FindSameVideoError):
    """输入验证异常"""

    def __init__(self, message: str, field: Optional[str] = None, value=None):
        details = f"{field}={value}" if field else None
        super().__init__(message, details)
        self.field = field
        self.value = value


class PathTraversalError(ValidationError):
    """路径遍历攻击异常"""

    def __init__(self, path: str, allowed_base: str):
        super().__init__(
            f"检测到路径遍历攻击",
            field="path",
            value=path
        )
        self.path = path
        self.allowed_base = allowed_base


class ExportError(FindSameVideoError):
    """导出异常"""

    def __init__(self, message: str, output_path: Optional[str] = None):
        details = f"output={output_path}" if output_path else None
        super().__init__(message, details)
        self.output_path = output_path


class SimilarityDetectionError(FindSameVideoError):
    """相似度检测异常"""

    def __init__(self, message: str, missing_library: Optional[str] = None):
        if missing_library:
            message = f"{message} (缺少库: {missing_library})"
        super().__init__(message)
        self.missing_library = missing_library
