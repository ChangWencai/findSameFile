from typing import Dict, List, Set, Callable, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass
import os
import logging

from file_scanner import FileInfo, FileScanner, HashCalculator, PermissionErrorInfo
from cache_manager import HashCache
from exceptions import FileScanError, HashCalculationError as HashCalcError
import multiprocessing as mp

# 导入并发执行模块
try:
    from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
    CONCURRENT_AVAILABLE = True
except ImportError:
    CONCURRENT_AVAILABLE = False

# 获取日志记录器
logger = logging.getLogger(__name__)

# 配置常量
HASH_CHUNK_SIZE = 32 * 1024  # 32KB chunks
PROGRESS_BATCH_SIZE_DIVISOR = 4  # 用于计算批处理大小


@dataclass
class DuplicateGroup:
    hash_value: str
    files: List[FileInfo]
    total_size: int


# 静态函数，用于进程池（可被pickle序列化）
def _calculate_file_hash_static(file_path: str, algorithm: str) -> Optional[str]:
    """静态函数：计算文件哈希值（可被pickle序列化用于进程池）"""
    import hashlib
    try:
        hasher = hashlib.new(algorithm)
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(HASH_CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, PermissionError) as e:
        logger.debug(f"无法读取文件: {file_path} - {e}")
        return None
    except Exception as e:
        logger.error(f"哈希计算失败: {file_path} - {e}")
        return None


class DuplicateFinder:
    def __init__(
        self,
        scanner: FileScanner,
        hash_calculator: HashCalculator,
        use_parallel: bool = True,
        cache_enabled: bool = True,
        cache_path: str = "hash_cache.db",
        use_multi_stage: bool = True,
        use_process_pool: bool = False  # 新增：使用进程池而非线程池
    ):
        self.scanner = scanner
        self.hash_calculator = hash_calculator
        self.use_parallel = use_parallel and CONCURRENT_AVAILABLE
        self.cache_enabled = cache_enabled
        self.use_multi_stage = use_multi_stage
        self.use_process_pool = use_process_pool  # 是否使用进程池

        # 根据类型选择worker数量
        if self.use_process_pool:
            # CPU密集型：使用所有CPU核心
            self.max_workers = mp.cpu_count() or 4
            self.executor_class = ProcessPoolExecutor
        else:
            # I/O密集型：限制worker数量
            self.max_workers = min(8, os.cpu_count() or 4)
            self.executor_class = ThreadPoolExecutor

        # Initialize cache
        self.cache = HashCache(cache_path) if cache_enabled else None
        self.cache_hits = 0
        self.cache_misses = 0

        # Store all scanned files for similarity detection
        self.all_scanned_files = []

    def find_duplicates(
        self,
        root_path: str,
        scan_progress_callback: Optional[Callable[[int, int], None]] = None,
        hash_progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None
    ) -> List[DuplicateGroup]:
        # Step 1: Scan all files
        files = self.scanner.scan_directory(root_path, scan_progress_callback)

        # Store all scanned files for similarity detection
        self.all_scanned_files = files.copy()

        # Step 2: Group by size (quick filter)
        size_groups = defaultdict(list)
        for file_info in files:
            size_groups[file_info.size].append(file_info)

        # Filter out groups with only one file (cannot be duplicates)
        potential_duplicates = [group for group in size_groups.values() if len(group) > 1]

        if cancel_callback and cancel_callback():
            return []

        # Step 3: Calculate hashes for potential duplicates
        # Use multi-stage hashing for better performance on large files
        if self.use_multi_stage and self._should_use_multi_stage(potential_duplicates):
            hash_groups = self._calculate_hashes_multi_stage(
                potential_duplicates,
                hash_progress_callback,
                cancel_callback
            )
        elif self.use_parallel and len(potential_duplicates) > 1:
            hash_groups = self._calculate_hashes_parallel(
                potential_duplicates,
                hash_progress_callback,
                cancel_callback
            )
        else:
            hash_groups = self._calculate_hashes_serial(
                potential_duplicates,
                hash_progress_callback,
                cancel_callback
            )

        # Step 4: Create duplicate groups
        duplicate_groups = []
        for hash_value, file_list in hash_groups.items():
            if len(file_list) > 1:
                duplicate_groups.append(DuplicateGroup(
                    hash_value=hash_value,
                    files=file_list,
                    total_size=file_list[0].size * len(file_list)
                ))

        # Sort by total size (largest duplicates first)
        duplicate_groups.sort(key=lambda x: x.total_size, reverse=True)

        return duplicate_groups

    def _should_use_multi_stage(self, potential_duplicates: List[List[FileInfo]]) -> bool:
        """判断是否应该使用多阶段哈希策略"""
        # Count files larger than 5MB
        large_file_count = 0
        total_files = 0

        for group in potential_duplicates:
            for file_info in group:
                total_files += 1
                if file_info.size > 5 * 1024 * 1024:  # 5MB
                    large_file_count += 1

        # Use multi-stage if there are at least 10 large files
        return large_file_count >= 10

    def _calculate_hashes_multi_stage(
        self,
        potential_duplicates: List[List[FileInfo]],
        hash_progress_callback: Optional[Callable[[int, int], None]],
        cancel_callback: Optional[Callable[[], bool]]
    ) -> Dict[str, List[FileInfo]]:
        """多阶段哈希计算：先计算部分哈希快速筛选，再计算完整哈希确认"""
        # Flatten all files to process
        all_files = []
        for group in potential_duplicates:
            all_files.extend(group)

        total = len(all_files)
        processed = 0

        # Report initial progress
        if hash_progress_callback and total > 0:
            hash_progress_callback(0, total)

        # Calculate report interval
        report_interval = max(1, total // 40) if total > 40 else 1  # More frequent updates for multi-stage
        last_reported = 0

        # Stage 1: Calculate partial hashes (first + middle + last 1MB)
        partial_hash_groups = defaultdict(list)
        files_for_full_hash = []

        for file_info in all_files:
            if cancel_callback and cancel_callback():
                return {}

            # Try cache first
            full_hash = None
            if self.cache:
                full_hash = self.cache.get(file_info.path, file_info.size, file_info.mtime)
                if full_hash:
                    self.cache_hits += 1
                    # If we have full hash in cache, use it directly
                    hash_groups = defaultdict(list)
                    hash_groups[full_hash].append(file_info)
                    return hash_groups
                else:
                    self.cache_misses += 1

            # Calculate partial hash
            partial_hash = self._calculate_partial_hash(file_info.path, file_info.size)
            if partial_hash:
                partial_hash_groups[partial_hash].append(file_info)
                # Track files that need full hash calculation
                files_for_full_hash.append((file_info, partial_hash))

            processed += 1
            if hash_progress_callback and (processed - last_reported >= report_interval):
                hash_progress_callback(processed // 2, total)  # First half is partial hashing
                last_reported = processed

        # Stage 2: Group by partial hash and only calculate full hash for groups with multiple files
        final_hash_groups = defaultdict(list)
        second_stage_files = []

        # Group files by partial hash
        partial_to_files = defaultdict(list)
        for file_info, partial_hash in files_for_full_hash:
            partial_to_files[partial_hash].append(file_info)

        # Only calculate full hash for groups with 2+ files sharing partial hash
        for partial_hash, file_list in partial_to_files.items():
            if len(file_list) > 1:
                second_stage_files.extend(file_list)
            else:
                # Single file in partial hash group - not a duplicate
                pass

        # Stage 3: Calculate full hashes only for potential duplicates
        if self.use_parallel and len(second_stage_files) > 1:
            final_hash_groups = self._calculate_full_hashes_parallel(
                second_stage_files,
                hash_progress_callback,
                cancel_callback,
                total,
                total // 2  # Start from halfway point
            )
        else:
            final_hash_groups = self._calculate_full_hashes_serial(
                second_stage_files,
                hash_progress_callback,
                cancel_callback,
                total,
                total // 2
            )

        # Save cache entries
        if self.cache and final_hash_groups:
            cache_entries = []
            for hash_value, file_list in final_hash_groups.items():
                for file_info in file_list:
                    cache_entries.append({
                        'path': file_info.path,
                        'size': file_info.size,
                        'mtime': file_info.mtime,
                        'hash_value': hash_value
                    })
            if cache_entries:
                self.cache.set_batch(cache_entries)

        return final_hash_groups

    def _calculate_partial_hash(self, file_path: str, file_size: int) -> Optional[str]:
        """计算文件的部分哈希（头部+尾部+中间各1MB）"""
        try:
            import hashlib
            hasher = hashlib.new(self.hash_calculator.algorithm)

            with open(file_path, 'rb') as f:
                # Read first 1MB
                chunk = f.read(1024 * 1024)
                if chunk:
                    hasher.update(chunk)

                # If file is larger than 3MB, read middle and last 1MB
                if file_size > 3 * 1024 * 1024:
                    # Seek to middle
                    f.seek(file_size // 2)
                    chunk = f.read(1024 * 1024)
                    if chunk:
                        hasher.update(chunk)

                    # Seek to last 1MB
                    f.seek(max(0, file_size - 1024 * 1024))
                    chunk = f.read(1024 * 1024)
                    if chunk:
                        hasher.update(chunk)

            return hasher.hexdigest()
        except Exception:
            return None

    def _calculate_full_hashes_serial(
        self,
        files: List[FileInfo],
        hash_progress_callback: Optional[Callable[[int, int], None]],
        cancel_callback: Optional[Callable[[], bool]],
        total_files: int,
        start_offset: int
    ) -> Dict[str, List[FileInfo]]:
        """串行计算完整哈希值"""
        hash_groups = defaultdict(list)

        report_interval = max(1, len(files) // 20) if len(files) > 20 else 1
        processed = 0
        last_reported = 0

        for file_info in files:
            if cancel_callback and cancel_callback():
                return {}

            hash_value = self.hash_calculator.calculate_file_hash(file_info.path, None)
            if hash_value:
                hash_groups[hash_value].append(file_info)

            processed += 1
            current = start_offset + processed
            if hash_progress_callback and (processed - last_reported >= report_interval or processed == len(files)):
                hash_progress_callback(current, total_files)
                last_reported = processed

        return hash_groups

    def _calculate_full_hashes_parallel(
        self,
        files: List[FileInfo],
        hash_progress_callback: Optional[Callable[[int, int], None]],
        cancel_callback: Optional[Callable[[], bool]],
        total_files: int,
        start_offset: int
    ) -> Dict[str, List[FileInfo]]:
        """并行计算完整哈希值"""
        hash_groups = defaultdict(list)
        cache_entries_to_save = []

        report_interval = max(1, len(files) // 20) if len(files) > 20 else 1
        processed = 0
        last_reported = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(self.hash_calculator.calculate_file_hash, file_info.path): file_info
                for file_info in files
            }

            for future in as_completed(future_to_file):
                if cancel_callback and cancel_callback():
                    for f in future_to_file:
                        f.cancel()
                    return {}

                file_info = future_to_file[future]
                try:
                    hash_value = future.result()
                    if hash_value:
                        hash_groups[hash_value].append(file_info)
                        if self.cache:
                            cache_entries_to_save.append({
                                'path': file_info.path,
                                'size': file_info.size,
                                'mtime': file_info.mtime,
                                'hash_value': hash_value
                            })

                    processed += 1
                    current = start_offset + processed
                    if hash_progress_callback and (processed - last_reported >= report_interval):
                        hash_progress_callback(current, total_files)
                        last_reported = processed
                except Exception:
                    processed += 1
                    pass

        # Save cache entries
        if cache_entries_to_save and self.cache:
            self.cache.set_batch(cache_entries_to_save)

        return hash_groups

    def _calculate_hashes_serial(
        self,
        potential_duplicates: List[List[FileInfo]],
        hash_progress_callback: Optional[Callable[[int, int], None]],
        cancel_callback: Optional[Callable[[], bool]]
    ) -> Dict[str, List[FileInfo]]:
        """串行计算哈希值"""
        hash_groups = defaultdict(list)
        processed = 0
        total = sum(len(group) for group in potential_duplicates)
        cache_entries_to_save = []

        # Report initial hash progress
        if hash_progress_callback and total > 0:
            hash_progress_callback(0, total)

        # Calculate report interval based on total files (aim for ~20 updates)
        report_interval = max(1, total // 20) if total > 20 else 1
        last_reported = 0

        for group in potential_duplicates:
            for file_info in group:
                if cancel_callback and cancel_callback():
                    # Save any pending cache entries before returning
                    if cache_entries_to_save and self.cache:
                        self.cache.set_batch(cache_entries_to_save)
                    return {}

                # Try to get hash from cache first
                hash_value = None
                if self.cache:
                    hash_value = self.cache.get(file_info.path, file_info.size, file_info.mtime)
                    if hash_value:
                        self.cache_hits += 1
                    else:
                        self.cache_misses += 1

                # Calculate hash if not in cache
                if hash_value is None:
                    hash_value = self.hash_calculator.calculate_file_hash(file_info.path, None)
                    if hash_value and self.cache:
                        cache_entries_to_save.append({
                            'path': file_info.path,
                            'size': file_info.size,
                            'mtime': file_info.mtime,
                            'hash_value': hash_value
                        })

                if hash_value:
                    hash_groups[hash_value].append(file_info)

                processed += 1
                # Report progress at intervals
                if hash_progress_callback and (processed - last_reported >= report_interval or processed == total):
                    hash_progress_callback(processed, total)
                    last_reported = processed

        # Batch save cache entries
        if cache_entries_to_save and self.cache:
            self.cache.set_batch(cache_entries_to_save)

        return hash_groups

    def _calculate_hashes_parallel(
        self,
        potential_duplicates: List[List[FileInfo]],
        hash_progress_callback: Optional[Callable[[int, int], None]],
        cancel_callback: Optional[Callable[[], bool]]
    ) -> Dict[str, List[FileInfo]]:
        """并行计算哈希值（优化版本：批量缓存查询 + 进程池支持）"""
        hash_groups = defaultdict(list)

        # Flatten the list of files to hash
        files_to_hash = []
        for group in potential_duplicates:
            files_to_hash.extend(group)

        total = len(files_to_hash)

        # 使用批量缓存查询（性能优化）
        files_to_calculate = []
        cache_entries_to_save = []
        processed_cached = 0

        if self.cache and hasattr(self.cache, 'get_batch'):
            # 批量查询缓存（性能提升10倍+）
            file_infos = [(f.path, f.size, f.mtime) for f in files_to_hash]
            cached_hashes = self.cache.get_batch(file_infos)

            for file_info in files_to_hash:
                hash_value = cached_hashes.get(file_info.path)
                if hash_value:
                    self.cache_hits += 1
                    hash_groups[hash_value].append(file_info)
                    processed_cached += 1
                else:
                    self.cache_misses += 1
                    files_to_calculate.append(file_info)
        elif self.cache:
            # 回退到逐个查询
            for file_info in files_to_hash:
                hash_value = self.cache.get(file_info.path, file_info.size, file_info.mtime)
                if hash_value:
                    self.cache_hits += 1
                    hash_groups[hash_value].append(file_info)
                    processed_cached += 1
                else:
                    self.cache_misses += 1
                    files_to_calculate.append(file_info)
        else:
            files_to_calculate = files_to_hash

        # Report initial hash progress (including cached files)
        processed = total - len(files_to_calculate)

        if hash_progress_callback and total > 0:
            hash_progress_callback(processed, total)

        # Calculate report interval based on total files (aim for ~20 updates)
        report_interval = max(1, total // 20) if total > 20 else 1
        last_reported = processed

        # If all files were cached, return early
        if not files_to_calculate:
            logger.info(f"所有 {total} 个文件均从缓存获取")
            return hash_groups

        # Calculate hashes for files not in cache
        total_to_calculate = len(files_to_calculate)
        logger.info(f"需要计算 {total_to_calculate}/{total} 个文件的哈希值 (使用 {self.max_workers} 个worker)")

        # Use appropriate executor for parallel hash calculation
        if self.use_parallel:
            if self.use_process_pool:
                # 使用进程池 + 批处理（最佳性能）
                batch_size = max(1, total_to_calculate // (self.max_workers * 4))
                with self.executor_class(max_workers=self.max_workers) as executor:
                    # 使用 map 批量处理（减少IPC开销）
                    algorithm = self.hash_calculator.algorithm
                    paths = [f.path for f in files_to_calculate]
                    results = executor.map(
                        _calculate_file_hash_static,
                        paths,
                        [algorithm] * len(paths),
                        chunksize=batch_size
                    )

                    # 处理结果
                    for file_info, hash_value in zip(files_to_calculate, results):
                        if cancel_callback and cancel_callback():
                            break

                        if hash_value:
                            hash_groups[hash_value].append(file_info)
                            if self.cache:
                                cache_entries_to_save.append({
                                    'path': file_info.path,
                                    'size': file_info.size,
                                    'mtime': file_info.mtime,
                                    'hash_value': hash_value
                                })

                        processed += 1
                        # Report progress at intervals
                        if hash_progress_callback and (processed - last_reported >= report_interval or processed == total):
                            hash_progress_callback(processed, total)
                            last_reported = processed
            else:
                # 使用线程池
                with self.executor_class(max_workers=self.max_workers) as executor:
                    # Submit all hash calculation tasks
                    future_to_file = {
                        executor.submit(self.hash_calculator.calculate_file_hash, file_info.path): file_info
                        for file_info in files_to_calculate
                    }

                    # Process completed tasks
                    for future in as_completed(future_to_file):
                        if cancel_callback and cancel_callback():
                            # Cancel remaining futures
                            for f in future_to_file:
                                f.cancel()
                            break

                        file_info = future_to_file[future]
                        try:
                            hash_value = future.result()
                            if hash_value:
                                hash_groups[hash_value].append(file_info)
                                if self.cache:
                                    cache_entries_to_save.append({
                                        'path': file_info.path,
                                        'size': file_info.size,
                                        'mtime': file_info.mtime,
                                        'hash_value': hash_value
                                    })

                            processed += 1
                            # Report progress at intervals
                            if hash_progress_callback and (processed - last_reported >= report_interval or processed == total):
                                hash_progress_callback(processed, total)
                                last_reported = processed
                        except Exception as e:
                            logger.warning(f"哈希计算失败 {file_info.path}: {e}")
                            processed += 1
        else:
            # 串行计算（不使用并行）
            for file_info in files_to_calculate:
                if cancel_callback and cancel_callback():
                    break

                hash_value = self.hash_calculator.calculate_file_hash(file_info.path)
                if hash_value:
                    hash_groups[hash_value].append(file_info)
                    if self.cache:
                        cache_entries_to_save.append({
                            'path': file_info.path,
                            'size': file_info.size,
                            'mtime': file_info.mtime,
                            'hash_value': hash_value
                        })

                processed += 1
                if hash_progress_callback and (processed - last_reported >= report_interval or processed == total):
                    hash_progress_callback(processed, total)
                    last_reported = processed

        # Batch save cache entries
        if cache_entries_to_save and self.cache:
            self.cache.set_batch(cache_entries_to_save)

        return hash_groups

    def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        if not self.cache:
            return {'enabled': False}

        stats = self.cache.get_stats()
        stats['enabled'] = True
        stats['hits'] = self.cache_hits
        stats['misses'] = self.cache_misses
        total_requests = self.cache_hits + self.cache_misses
        if total_requests > 0:
            stats['hit_rate'] = self.cache_hits / total_requests
        else:
            stats['hit_rate'] = 0.0

        return stats

    def clear_cache(self):
        """清空缓存"""
        if self.cache:
            self.cache.clear()
            self.cache_hits = 0
            self.cache_misses = 0

    def get_total_wasted_space(self, duplicate_groups: List[DuplicateGroup]) -> int:
        wasted = 0
        for group in duplicate_groups:
            wasted += group.total_size - group.files[0].size
        return wasted

    def get_all_scanned_files(self) -> List[FileInfo]:
        """获取所有扫描过的文件，用于相似度检测"""
        return self.all_scanned_files

