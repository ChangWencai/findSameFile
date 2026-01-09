"""
配置管理模块

支持加载和保存应用程序配置。
"""
import json
import os
from typing import Any, Dict, List
from pathlib import Path


class ConfigManager:
    """配置管理器"""

    DEFAULT_CONFIG = {
        # 主题设置
        "theme": "light",  # light, dark

        # 缓存设置
        "cache_enabled": True,
        "cache_path": "hash_cache.db",

        # 并行设置
        "use_parallel": True,

        # 多阶段哈希设置
        "use_multi_stage": True,

        # 默认文件类型
        "default_extensions": [
            ".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm", ".m4v",
            ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg",
            ".mp3", ".flac", ".aac", ".ogg", ".wav", ".m4a",
            ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
            ".zip", ".rar", ".7z", ".tar", ".gz"
        ],

        # 智能选择默认设置
        "smart_select_default_strategy": "keep_shortest_path",

        # 导出设置
        "export_format": "html",  # html, csv, json
        "export_include_metadata": True,

        # 窗口设置
        "remember_window_size": True,
        "window_width": 1100,
        "window_height": 700,

        # 其他设置
        "auto_start_scan_on_drop": True,
        "show_eta": True,
    }

    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                # 合并用户配置和默认配置
                config = self.DEFAULT_CONFIG.copy()
                config.update(user_config)
                return config
            except Exception as e:
                print(f"加载配置文件失败: {e}，使用默认配置")
                return self.DEFAULT_CONFIG.copy()
        else:
            # 创建默认配置文件
            self.save_config(self.DEFAULT_CONFIG)
            return self.DEFAULT_CONFIG.copy()

    def save_config(self, config: Dict[str, Any] = None) -> bool:
        """保存配置文件"""
        try:
            config_to_save = config or self.config
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config_to_save, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False

    def save(self) -> bool:
        """保存配置（便捷方法）"""
        return self.save_config()

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self.config.get(key, default)

    def set(self, key: str, value: Any, save: bool = True) -> None:
        """设置配置项"""
        self.config[key] = value
        if save:
            self.save_config()

    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self.config.copy()

    def reset_to_default(self) -> None:
        """重置为默认配置"""
        self.config = self.DEFAULT_CONFIG.copy()
        self.save_config()

    @staticmethod
    def get_config_path() -> str:
        """获取配置文件路径"""
        # 优先使用用户目录
        user_config_dir = Path.home() / ".findSameVideo"
        user_config_dir.mkdir(exist_ok=True)
        return str(user_config_dir / "config.json")

    @staticmethod
    def get_default_extensions() -> List[str]:
        """获取默认文件扩展名列表"""
        return ConfigManager.DEFAULT_CONFIG["default_extensions"].copy()
