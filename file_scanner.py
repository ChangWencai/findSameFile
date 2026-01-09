import os
import hashlib
from pathlib import Path
from typing import Dict, List, Set, Callable, Optional, Tuple
from dataclasses import dataclass


# Skip these special file types that can cause hangs
SKIP_EXTENSIONS = {'.app', '.bundle', '.pkg', '.dmg', '.iso'}
SKIP_NAMES = {'._', '.DS_Store', 'Thumbs.db', '.Spotlight-V100', '.Trashes'}


@dataclass
class PermissionError:
    """权限错误信息"""
    path: str
    error: str


@dataclass
class FileInfo:
    path: str
    size: int
    mtime: float


class FileScanner:
    def __init__(self, extensions: Optional[Set[str]] = None):
        self.extensions = extensions
        self.permission_errors: List[PermissionError] = []
        self.skipped_directories: List[str] = []

    def check_permissions(self, root_path: str) -> List[PermissionError]:
        """
        预检查目录权限

        Returns:
            无权限访问的目录列表
        """
        self.permission_errors = []
        root = Path(root_path)

        if not root.exists():
            return [PermissionError(str(root), "路径不存在")]

        if not os.access(root, os.R_OK):
            self.permission_errors.append(PermissionError(str(root), "无读取权限"))

        # Check subdirectories
        for dir_path in root.rglob('*'):
            if dir_path.is_dir():
                try:
                    # Try to list directory
                    list(dir_path.iterdir())
                except PermissionError:
                    self.permission_errors.append(PermissionError(str(dir_path), "无访问权限"))
                except Exception as e:
                    self.permission_errors.append(PermissionError(str(dir_path), str(e)))

        return self.permission_errors

    def get_permission_summary(self) -> Tuple[int, str]:
        """
        获取权限错误摘要

        Returns:
            (错误数量, 摘要文本)
        """
        if not self.permission_errors:
            return 0, "无权限问题"

        skipped = len(self.skipped_directories)
        return (len(self.permission_errors),
                f"发现 {len(self.permission_errors)} 个权限问题，跳过 {skipped} 个目录")

    def scan_directory(self, root_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> List[FileInfo]:
        files = []
        root = Path(root_path)
        self.permission_errors = []
        self.skipped_directories = []

        if not root.exists():
            raise ValueError(f"Path does not exist: {root_path}")

        if not os.access(root, os.R_OK):
            raise PermissionError(f"无读取权限: {root_path}")

        def should_skip_file(file_path: Path) -> bool:
            # Skip special file types
            if file_path.suffix.lower() in SKIP_EXTENSIONS:
                return True
            # Skip special file names
            if any(file_path.name.startswith(name) for name in SKIP_NAMES):
                return True
            # Skip zero-sized files
            try:
                if file_path.stat().st_size == 0:
                    return True
            except:
                return True
            # Filter by extensions if specified
            if self.extensions is not None:
                # Normalize extension for comparison
                ext = file_path.suffix.lower()
                normalized_extensions = {e.lower() if e.startswith('.') else f'.{e.lower()}' for e in self.extensions}
                if ext not in normalized_extensions:
                    return True
            return False

        def is_accessible(path: Path) -> bool:
            """检查路径是否可访问"""
            try:
                os.access(path, os.R_OK)
                return True
            except:
                return False

        # Count total files first for progress tracking
        total_files = 0
        skipped_dirs = set()

        try:
            for item in root.rglob('*'):
                if item.is_file() and not should_skip_file(item):
                    total_files += 1
                elif item.is_dir():
                    # Check directory accessibility
                    if not is_accessible(item):
                        skipped_dirs.add(str(item))
        except Exception as e:
            pass  # Ignore errors during counting

        self.skipped_directories = list(skipped_dirs)

        # Report initial progress
        if progress_callback and total_files > 0:
            progress_callback(0, total_files)

        # Calculate report interval based on total files (aim for ~20 updates)
        report_interval = max(1, total_files // 20) if total_files > 20 else 1
        processed = 0
        last_reported = 0

        for file_path in root.rglob('*'):
            if file_path.is_file():
                if should_skip_file(file_path):
                    continue

                try:
                    stat = file_path.stat()
                    files.append(FileInfo(
                        path=str(file_path),
                        size=stat.st_size,
                        mtime=stat.st_mtime
                    ))
                    processed += 1
                    # Report progress at intervals
                    if progress_callback and (processed - last_reported >= report_interval or processed == total_files):
                        progress_callback(processed, total_files)
                        last_reported = processed
                except PermissionError as e:
                    self.permission_errors.append(PermissionError(str(file_path), "无访问权限"))
                except Exception as e:
                    # Silently skip files with other errors
                    pass

        return files


class HashCalculator:
    CHUNK_SIZE = 8192 * 4
    PROGRESS_INTERVAL = 1024 * 1024  # Report progress every 1MB

    def __init__(self, algorithm: str = 'sha256'):
        self.algorithm = algorithm

    def calculate_file_hash(self, file_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> Optional[str]:
        try:
            hasher = hashlib.new(self.algorithm)
            file_size = os.path.getsize(file_path)
            bytes_read = 0
            last_progress_report = 0

            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    bytes_read += len(chunk)

                    # Only report progress at intervals to avoid overwhelming the GUI
                    if progress_callback and file_size > 0:
                        if bytes_read - last_progress_report >= self.PROGRESS_INTERVAL:
                            progress_callback(bytes_read, file_size)
                            last_progress_report = bytes_read

                # Final progress report
                if progress_callback and file_size > 0:
                    progress_callback(bytes_read, file_size)

            return hasher.hexdigest()
        except (OSError, PermissionError, Exception):
            return None

    def calculate_partial_hash(self, file_path: str, sample_size: int = 1024 * 1024) -> Optional[str]:
        try:
            hasher = hashlib.new(self.algorithm)
            with open(file_path, 'rb') as f:
                chunk = f.read(sample_size)
                hasher.update(chunk)
            return hasher.hexdigest()
        except (OSError, PermissionError):
            return None
