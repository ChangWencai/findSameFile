"""
工具函数模块

包含项目中使用的各种工具函数。
"""
import os
from typing import Optional
from pathlib import Path
import hashlib


def format_size(size: int) -> str:
    """
    格式化文件大小显示

    Args:
        size: 文件大小（字节）

    Returns:
        格式化后的大小字符串，如 "1.23 MB"
    """
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} EB"


def format_duration(seconds: float) -> str:
    """
    格式化时间显示

    Args:
        seconds: 秒数

    Returns:
        格式化后的时间字符串，如 "1:23:45" 或 "45s"
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"


def calculate_file_size(file_path: str) -> int:
    """
    安全地计算文件大小

    Args:
        file_path: 文件路径

    Returns:
        文件大小（字节），如果出错返回 0
    """
    try:
        return os.path.getsize(file_path)
    except (OSError, FileNotFoundError):
        return 0


def get_file_extension(file_path: str) -> str:
    """
    获取文件扩展名（包含点号）

    Args:
        file_path: 文件路径

    Returns:
        扩展名，如 ".txt"，如果没有扩展名返回空字符串
    """
    return Path(file_path).suffix.lower()


def normalize_extension(ext: str) -> str:
    """
    规范化文件扩展名格式

    Args:
        ext: 扩展名（带或不带点号）

    Returns:
        规范化后的扩展名（包含点号，小写）
    """
    ext = ext.strip().lower()
    if not ext.startswith('.'):
        ext = f'.{ext}'
    return ext


def validate_path_safe(
    file_path: str,
    allowed_base: Optional[str] = None,
    must_exist: bool = False
) -> str:
    """
    验证路径安全性，防止路径遍历攻击

    Args:
        file_path: 要验证的路径
        allowed_base: 允许的基础目录（用于防止路径遍历）
        must_exist: 路径是否必须存在

    Returns:
        规范化后的绝对路径

    Raises:
        ValidationError: 如果路径不安全或无效
    """
    from exceptions import ValidationError, PathTraversalError, FileNotFoundError as FindSameVideoFileNotFound

    # 规范化路径
    try:
        real_path = os.path.realpath(file_path)
        real_path = os.path.abspath(real_path)
    except (ValueError, OSError) as e:
        raise ValidationError(f"无效的路径: {file_path}", value=file_path)

    # 检查路径是否存在
    if must_exist and not os.path.exists(real_path):
        raise FindSameVideoFileNotFound(f"路径不存在: {file_path}", path=file_path)

    # 检查路径遍历攻击
    if allowed_base:
        real_base = os.path.realpath(allowed_base)
        real_base = os.path.abspath(real_base)

        # 确保real_path在real_base之内
        if not real_path.startswith(real_base + os.sep) and real_path != real_base:
            raise PathTraversalError(file_path, allowed_base)

    return real_path


def ensure_directory_exists(dir_path: str) -> str:
    """
    确保目录存在，如果不存在则创建

    Args:
        dir_path: 目录路径

    Returns:
        目录的绝对路径
    """
    path = Path(dir_path)
    path.mkdir(parents=True, exist_ok=True)
    return str(path.absolute())


def safe_delete(file_path: str) -> bool:
    """
    安全地删除文件（使用回收站）

    Args:
        file_path: 文件路径

    Returns:
        是否成功删除
    """
    try:
        # 尝试使用 send2trash
        from send2trash import send2trash
        send2trash(file_path)
        return True
    except ImportError:
        # 如果 send2trash 不可用，使用永久删除
        try:
            os.remove(file_path)
            return True
        except OSError:
            return False
    except Exception:
        return False


def calculate_hash_quick(file_path: str, algorithm: str = 'sha256') -> Optional[str]:
    """
    快速计算文件哈希（用于小文件或快速检查）

    Args:
        file_path: 文件路径
        algorithm: 哈希算法

    Returns:
        哈希值，失败返回 None
    """
    try:
        hasher = hashlib.new(algorithm)
        with open(file_path, 'rb') as f:
            # 一次性读取（适用于小文件）
            hasher.write(f.read())
        return hasher.hexdigest()
    except (OSError, ValueError):
        return None


def parse_size_string(size_str: str) -> int:
    """
    解析大小字符串（如 "1MB"）为字节数

    Args:
        size_str: 大小字符串，如 "1MB", "256KB", "1.5GB"

    Returns:
        字节数

    Raises:
        ValidationError: 如果格式无效
    """
    from exceptions import ValidationError

    size_str = size_str.strip().upper()
    units = {
        'B': 1,
        'KB': 1024,
        'MB': 1024 ** 2,
        'GB': 1024 ** 3,
        'TB': 1024 ** 4,
    }

    for unit, multiplier in units.items():
        if size_str.endswith(unit):
            try:
                value = float(size_str[:-len(unit)])
                return int(value * multiplier)
            except ValueError:
                raise ValidationError(f"无效的大小格式: {size_str}", field="size_str", value=size_str)

    raise ValidationError(f"未知的大小单位: {size_str}", field="size_str", value=size_str)


def truncate_path(path: str, max_length: int = 50) -> str:
    """
    截断过长的路径显示

    Args:
        path: 文件路径
        max_length: 最大长度

    Returns:
        截断后的路径，如 ".../very/long/path/file.txt"
    """
    if len(path) <= max_length:
        return path

    # 保留文件名
    filename = os.path.basename(path)
    available = max_length - len(filename) - 4  # 4 for ".../"

    if available <= 0:
        return "..." + filename[-(max_length - 3):]

    # 截断目录部分
    dirname = os.path.dirname(path)
    if len(dirname) > available:
        dirname = "..." + dirname[-(available - 3):]

    return os.path.join(dirname, filename)


def get_common_path(paths: list) -> str:
    """
    获取多个路径的公共父目录

    Args:
        paths: 路径列表

    Returns:
        公共父目录路径
    """
    if not paths:
        return ""
    if len(paths) == 1:
        return os.path.dirname(paths[0])

    return os.path.commonpath(paths)
