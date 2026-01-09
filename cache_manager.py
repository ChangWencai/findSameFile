"""
哈希缓存管理器

使用 SQLite 存储文件哈希结果，避免重复计算未修改的文件。
"""
import os
import sqlite3
import hashlib
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime
from logger import get_logger


class HashCache:
    """文件哈希缓存管理器"""

    def __init__(self, cache_path: str = "hash_cache.db"):
        self.cache_path = cache_path
        self.conn = None
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        self.conn = sqlite3.connect(self.cache_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")  # Enable Write-Ahead Logging for better concurrency
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS hash_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL,
                hash_value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_path ON hash_cache(path)
        """)
        self.conn.commit()

    def get(self, file_path: str, size: int, mtime: float) -> Optional[str]:
        """
        获取文件缓存哈希值

        Args:
            file_path: 文件路径
            size: 文件大小
            mtime: 文件修改时间

        Returns:
            缓存的哈希值，如果缓存无效则返回 None
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT hash_value FROM hash_cache
            WHERE path = ? AND size = ? AND mtime = ?
        """, (file_path, size, mtime))
        result = cursor.fetchone()
        return result[0] if result else None

    def set(self, file_path: str, size: int, mtime: float, hash_value: str):
        """
        设置文件哈希缓存

        Args:
            file_path: 文件路径
            size: 文件大小
            mtime: 文件修改时间
            hash_value: 哈希值
        """
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT OR REPLACE INTO hash_cache (path, size, mtime, hash_value, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (file_path, size, mtime, hash_value, now))
        self.conn.commit()

    def set_batch(self, entries: List[Dict]):
        """
        批量设置缓存

        Args:
            entries: 包含 (path, size, mtime, hash_value) 的字典列表
        """
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        for entry in entries:
            cursor.execute("""
                INSERT OR REPLACE INTO hash_cache (path, size, mtime, hash_value, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (entry['path'], entry['size'], entry['mtime'], entry['hash_value'], now))
        self.conn.commit()

    def invalidate(self, file_path: str):
        """
        使指定文件的缓存失效

        Args:
            file_path: 文件路径
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM hash_cache WHERE path = ?", (file_path,))
        self.conn.commit()

    def invalidate_by_prefix(self, prefix: str):
        """
        使指定前缀的缓存失效

        Args:
            prefix: 路径前缀
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM hash_cache WHERE path LIKE ?", (f"{prefix}%",))
        self.conn.commit()

    def clear(self):
        """清空所有缓存"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM hash_cache")
        self.conn.commit()

    def get_stats(self) -> Dict:
        """
        获取缓存统计信息

        Returns:
            包含缓存统计信息的字典
        """
        cursor = self.conn.cursor()

        # Total entries
        cursor.execute("SELECT COUNT(*) FROM hash_cache")
        total_entries = cursor.fetchone()[0]

        # Total cached files size
        cursor.execute("SELECT SUM(size) FROM hash_cache")
        total_size = cursor.fetchone()[0] or 0

        # Database file size
        db_size = os.path.getsize(self.cache_path) if os.path.exists(self.cache_path) else 0

        # Oldest and newest entries
        cursor.execute("SELECT MIN(created_at), MAX(created_at) FROM hash_cache")
        oldest, newest = cursor.fetchone()

        return {
            'total_entries': total_entries,
            'total_size': total_size,
            'db_size': db_size,
            'oldest_entry': oldest,
            'newest_entry': newest
        }

    def cleanup_invalid_paths(self, valid_paths: Optional[List[str]] = None):
        """
        清理无效路径的缓存

        Args:
            valid_paths: 有效路径列表，如果为 None 则检查所有缓存路径
        """
        cursor = self.conn.cursor()

        if valid_paths is not None:
            valid_set = set(valid_paths)
            cursor.execute("SELECT path FROM hash_cache")
            to_delete = [row[0] for row in cursor.fetchall() if row[0] not in valid_set]
        else:
            # Check if files still exist
            cursor.execute("SELECT path FROM hash_cache")
            to_delete = [row[0] for row in cursor.fetchall() if not os.path.exists(row[0])]

        for path in to_delete:
            cursor.execute("DELETE FROM hash_cache WHERE path = ?", (path,))

        self.conn.commit()
        return len(to_delete)

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
