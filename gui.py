import os
import sys
import subprocess
import platform
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QProgressBar, QFileDialog,
    QTreeWidget, QTreeWidgetItem, QSplitter, QGroupBox, QMessageBox,
    QListWidget, QAbstractItemView, QCheckBox, QMenu, QDialog,
    QDialogButtonBox, QRadioButton, QButtonGroup, QLineEdit, QSpinBox, QTabWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint, QMimeData
from PyQt6.QtGui import QFont, QAction, QDropEvent

from file_scanner import FileScanner, HashCalculator, FileInfo
from duplicate_finder import DuplicateFinder, DuplicateGroup
from export_manager import ExportManager
from config_manager import ConfigManager
from logger import get_logger
from utils import format_size  # 导入工具函数

# Try to import similarity detector
try:
    from similarity_detector import SimilarityDetector, SimilarGroup, SimilarFile, SimilarityMethod
    SIMILARITY_AVAILABLE = True
except ImportError:
    SIMILARITY_AVAILABLE = False

# Try to import send2trash for safe deletion
try:
    from send2trash import send2trash
    SEND2TRASH_AVAILABLE = True
except ImportError:
    SEND2TRASH_AVAILABLE = False
    print("警告: send2trash 未安装，将使用永久删除。请运行: pip install send2trash")


# Common file types for filtering
FILE_TYPES = [
    "所有文件",
    "视频文件 (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm)",
    "图片文件 (*.jpg *.jpeg *.png *.gif *.bmp *.tiff *.webp)",
    "音频文件 (*.mp3 *.wav *.flac *.aac *.ogg *.wma)",
    "文档文件 (*.pdf *.doc *.docx *.xls *.xlsx *.ppt *.pptx *.txt)",
    "压缩文件 (*.zip *.rar *.7z *.tar *.gz)",
    "可执行文件 (*.exe *.app *.dmg)",
    "自定义 (在下方输入框中编辑)",
]


class ScanThread(QThread):
    progress_update = pyqtSignal(int, int, str)
    scan_complete = pyqtSignal(list, int, list)  # (results, wasted_space, scanned_files)
    error_occurred = pyqtSignal(str)

    def __init__(self, root_path: str, extensions: set = None):
        super().__init__()
        self.root_path = root_path
        self.extensions = extensions
        self.scanner = FileScanner(extensions)
        self.hash_calculator = HashCalculator()
        self.finder = DuplicateFinder(self.scanner, self.hash_calculator)
        self._cancelled = False
        self.all_scanned_files = []  # Store all scanned files for similarity detection

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            results = self.finder.find_duplicates(
                self.root_path,
                scan_progress_callback=lambda c, t: self.progress_update.emit(c, t, "scan"),
                hash_progress_callback=lambda c, t: self.progress_update.emit(c, t, "hash"),
                cancel_callback=lambda: self._cancelled
            )
            # Get all scanned files from the finder for similarity detection
            self.all_scanned_files = self.finder.get_all_scanned_files()
            wasted_space = self.finder.get_total_wasted_space(results)
            self.scan_complete.emit(results, wasted_space, self.all_scanned_files)
        except Exception as e:
            self.error_occurred.emit(str(e))


class SimilarityScanThread(QThread):
    """相似度扫描线程"""
    progress_update = pyqtSignal(int, int)
    scan_complete = pyqtSignal(list, list)  # (similar_images, similar_videos)
    error_occurred = pyqtSignal(str)

    def __init__(self, files: list, detector: SimilarityDetector):
        super().__init__()
        self.files = files
        self.detector = detector
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            similar_images, similar_videos = self.detector.find_similar_files(
                self.files,
                progress_callback=lambda c, t: self.progress_update.emit(c, t)
            )
            self.scan_complete.emit(similar_images, similar_videos)
        except Exception as e:
            self.error_occurred.emit(str(e))


class DuplicateFileFinderGUI(QMainWindow):
    DELETION_HISTORY_FILE = "deletion_history.json"

    def __init__(self):
        super().__init__()
        # Initialize logger
        self.log = get_logger()
        self.log.info("应用程序启动")

        self.scan_thread = None
        self.selected_path = ""
        self.duplicate_groups = []
        self.deletion_history = self._load_deletion_history()
        self.dark_mode = False
        # Similarity detection
        self.similarity_thread = None
        self.scanned_files = []  # Store all scanned files for similarity detection
        self.similarity_detector = None
        # Time tracking for ETA calculation
        self.scan_start_time = None
        self.last_progress_update = None
        # Initialize config manager
        self.config = ConfigManager(ConfigManager.get_config_path())
        self.init_ui()
        self._load_settings_from_config()

    def _load_settings_from_config(self):
        """从配置加载设置"""
        # Load theme
        theme = self.config.get("theme", "light")
        if theme == "dark":
            self.dark_mode = True
            self.setStyleSheet(ThemeManager.get_dark_theme())
            self.theme_action.setText("切换到浅色模式")
        else:
            self.dark_mode = False
            self.setStyleSheet(ThemeManager.get_light_theme())
            self.theme_action.setText("切换到深色模式")

        # Load window size
        if self.config.get("remember_window_size", True):
            width = self.config.get("window_width", 1100)
            height = self.config.get("window_height", 700)
            self.resize(width, height)

        # Load default file types
        default_extensions = self.config.get("default_extensions", [])
        if default_extensions:
            for ext in default_extensions:
                for i in range(self.file_type_list.count()):
                    item = self.file_type_list.item(i)
                    if item.text() == ext:
                        item.setCheckState(Qt.CheckState.Checked)
                    else:
                        item.setCheckState(Qt.CheckState.Unchecked)

    def init_ui(self):
        self.setWindowTitle("重复文件查找器")
        self.setGeometry(100, 100, 1100, 700)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        # Top section - Path and file type selection
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)

        # Path selection
        path_group = QGroupBox("扫描路径")
        path_layout = QHBoxLayout()

        self.path_label = QLabel("未选择路径")
        self.path_label.setStyleSheet("color: gray;")
        self.browse_button = QPushButton("浏览...")
        self.browse_button.clicked.connect(self.browse_directory)

        path_layout.addWidget(self.path_label)
        path_layout.addWidget(self.browse_button)
        path_group.setLayout(path_layout)

        top_layout.addWidget(path_group)

        # File type selection
        type_group = QGroupBox("文件类型（可多选）")
        type_layout = QVBoxLayout()

        self.select_all_checkbox = QCheckBox("全选")
        self.select_all_checkbox.setChecked(True)
        self.select_all_checkbox.stateChanged.connect(self.toggle_select_all)

        self.file_type_list = QListWidget()
        self.file_type_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for file_type in FILE_TYPES:
            item = self.file_type_list.addItem(file_type)
            # Get the item we just added and make it checkable
            item_widget = self.file_type_list.item(self.file_type_list.count() - 1)
            item_widget.setFlags(item_widget.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item_widget.setCheckState(Qt.CheckState.Checked)
            # 默认取消"自定义"选项
            if "自定义" in file_type:
                item_widget.setCheckState(Qt.CheckState.Unchecked)

        # 连接列表项点击事件，用于处理自定义选项
        self.file_type_list.itemClicked.connect(self.on_file_type_item_clicked)

        type_layout.addWidget(self.select_all_checkbox)
        type_layout.addWidget(self.file_type_list)

        # 自定义文件扩展名输入区域
        custom_ext_layout = QHBoxLayout()
        custom_ext_label = QLabel("自定义扩展名:")
        self.custom_extensions_input = QLineEdit()
        self.custom_extensions_input.setPlaceholderText("例如: .py .js .ts (用空格分隔)")
        self.custom_extensions_input.setText(self.config.get("custom_extensions", ""))
        self.custom_extensions_input.setEnabled(False)  # 默认禁用
        custom_ext_layout.addWidget(custom_ext_label)
        custom_ext_layout.addWidget(self.custom_extensions_input)
        type_layout.addLayout(custom_ext_layout)

        type_group.setLayout(type_layout)

        top_layout.addWidget(type_group)

        layout.addWidget(top_widget)

        # Middle section - Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side - Progress and controls
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # Progress section
        progress_group = QGroupBox("进度")
        progress_layout = QVBoxLayout()

        self.status_label = QLabel("就绪")
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)

        progress_layout.addWidget(self.status_label)
        progress_layout.addWidget(self.progress_bar)
        progress_group.setLayout(progress_layout)
        left_layout.addWidget(progress_group)

        # Control buttons
        button_layout = QVBoxLayout()
        self.scan_button = QPushButton("开始扫描")
        self.scan_button.clicked.connect(self.start_scan)
        self.scan_button.setEnabled(False)

        self.stop_button = QPushButton("停止扫描")
        self.stop_button.clicked.connect(self.stop_scan)
        self.stop_button.setEnabled(False)

        button_layout.addWidget(self.scan_button)
        button_layout.addWidget(self.stop_button)
        left_layout.addLayout(button_layout)

        # Statistics
        stats_group = QGroupBox("统计信息")
        stats_layout = QVBoxLayout()

        self.files_scanned_label = QLabel("扫描文件数: 0")
        self.duplicate_groups_label = QLabel("重复组数: 0")
        self.wasted_space_label = QLabel("浪费空间: 0 B")
        self.selected_files_label = QLabel("已选文件: 0")

        stats_layout.addWidget(self.files_scanned_label)
        stats_layout.addWidget(self.duplicate_groups_label)
        stats_layout.addWidget(self.wasted_space_label)
        stats_layout.addWidget(self.selected_files_label)
        stats_group.setLayout(stats_layout)
        left_layout.addWidget(stats_group)

        # Selection buttons
        selection_group = QGroupBox("智能选择")
        selection_layout = QVBoxLayout()

        # Smart select button
        self.smart_select_button = QPushButton("智能选择...")
        self.smart_select_button.clicked.connect(self.show_smart_select_dialog)
        self.smart_select_button.setEnabled(False)
        selection_layout.addWidget(self.smart_select_button)

        # Quick action buttons
        quick_actions_layout = QHBoxLayout()
        self.select_all_button = QPushButton("全选")
        self.select_all_button.clicked.connect(self.select_all_files)
        self.select_all_button.setEnabled(False)
        self.deselect_all_button = QPushButton("不选")
        self.deselect_all_button.clicked.connect(self.deselect_all_files)
        self.deselect_all_button.setEnabled(False)
        self.invert_selection_button = QPushButton("反选")
        self.invert_selection_button.clicked.connect(self.invert_selection)
        self.invert_selection_button.setEnabled(False)
        quick_actions_layout.addWidget(self.select_all_button)
        quick_actions_layout.addWidget(self.deselect_all_button)
        quick_actions_layout.addWidget(self.invert_selection_button)
        selection_layout.addLayout(quick_actions_layout)

        # Advanced selection button
        self.advanced_select_button = QPushButton("高级选择...")
        self.advanced_select_button.clicked.connect(self.show_advanced_select_dialog)
        self.advanced_select_button.setEnabled(False)
        selection_layout.addWidget(self.advanced_select_button)

        selection_group.setLayout(selection_layout)
        left_layout.addWidget(selection_group)

        # Export button
        self.export_button = QPushButton("导出报告...")
        self.export_button.clicked.connect(self.show_export_dialog)
        self.export_button.setEnabled(False)
        left_layout.addWidget(self.export_button)

        # Similarity detection button
        if SIMILARITY_AVAILABLE:
            self.similarity_button = QPushButton("查找相似文件...")
            self.similarity_button.clicked.connect(self.show_similarity_dialog)
            self.similarity_button.setEnabled(False)
            left_layout.addWidget(self.similarity_button)
        else:
            self.similarity_button = None

        # Delete button
        self.delete_button = QPushButton("删除选中文件")
        self.delete_button.clicked.connect(self.delete_selected_files)
        self.delete_button.setEnabled(False)
        self.delete_button.setStyleSheet("QPushButton { background-color: #ffcccc; }")
        left_layout.addWidget(self.delete_button)

        left_layout.addStretch()
        splitter.addWidget(left_widget)

        # Right side - Results tree
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        results_group = QGroupBox("重复文件（勾选要删除的文件）")
        results_layout = QVBoxLayout()

        # Search box
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入文件名或路径进行过滤...")
        self.search_input.textChanged.connect(self.filter_results)
        self.clear_search_button = QPushButton("清除")
        self.clear_search_button.clicked.connect(self.clear_search)
        self.clear_search_button.setEnabled(False)

        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.clear_search_button)
        results_layout.addLayout(search_layout)

        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabels(["选择", "文件名", "路径", "大小"])
        self.results_tree.setColumnWidth(0, 60)
        self.results_tree.setColumnWidth(1, 180)
        self.results_tree.setColumnWidth(2, 350)
        self.results_tree.setColumnWidth(3, 100)
        self.results_tree.itemChanged.connect(self.on_item_changed)
        self.results_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_tree.customContextMenuRequested.connect(self.show_context_menu)

        results_layout.addWidget(self.results_tree)
        results_group.setLayout(results_layout)
        right_layout.addWidget(results_group)

        # File preview panel
        preview_group = QGroupBox("文件预览")
        preview_layout = QVBoxLayout()

        # Preview label (shows info when no file selected)
        self.preview_label = QLabel("选择一个文件以预览")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("color: gray; font-style: italic;")
        preview_layout.addWidget(self.preview_label)

        # Preview details (initially hidden)
        self.preview_details = QLabel()
        self.preview_details.setVisible(False)
        self.preview_details.setTextFormat(Qt.TextFormat.PlainText)
        preview_layout.addWidget(self.preview_details)

        # Preview thumbnail area
        self.preview_thumbnail = QLabel()
        self.preview_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_thumbnail.setMinimumHeight(150)
        self.preview_thumbnail.setStyleSheet("border: 1px solid #cccccc; background-color: #f5f5f5;")
        self.preview_thumbnail.setVisible(False)
        preview_layout.addWidget(self.preview_thumbnail)

        preview_group.setLayout(preview_layout)
        right_layout.addWidget(preview_group)

        # Connect tree selection to preview update
        self.results_tree.itemSelectionChanged.connect(self.update_file_preview)

        splitter.addWidget(right_widget)
        layout.addWidget(splitter)

        # Menu bar
        menubar = self.menuBar()
        view_menu = menubar.addMenu("视图")

        # Theme toggle action
        self.theme_action = QAction("切换到深色模式", self)
        self.theme_action.triggered.connect(self.toggle_theme)
        view_menu.addAction(self.theme_action)

        # Status bar
        self.statusBar().showMessage("就绪")

        # Enable drag and drop
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        """处理拖拽进入事件"""
        if event.mimeData().hasUrls():
            # Check if any URL is a directory
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if os.path.isdir(path):
                        event.acceptProposedAction()
                        return
        event.ignore()

    def dragMoveEvent(self, event):
        """处理拖拽移动事件"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """处理拖拽放下事件"""
        if event.mimeData().hasUrls():
            directories = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if os.path.isdir(path):
                        directories.append(path)

            if directories:
                if len(directories) == 1:
                    # Single directory - start scan
                    self.selected_path = directories[0]
                    self.path_label.setText(directories[0])
                    self.path_label.setStyleSheet("color: black;")
                    self.scan_button.setEnabled(True)
                    # Auto start scan
                    self.start_scan()
                else:
                    # Multiple directories - show selection dialog
                    # For now, just use the first one
                    self.selected_path = directories[0]
                    self.path_label.setText(f"{directories[0]} (+{len(directories)-1} 更多)")
                    self.path_label.setStyleSheet("color: black;")
                    self.scan_button.setEnabled(True)
                    self.statusBar().showMessage(f"已选择 {len(directories)} 个目录，将扫描第一个", 3000)

            event.acceptProposedAction()

    def toggle_select_all(self, state):
        check_state = Qt.CheckState.Checked if state == 2 else Qt.CheckState.Unchecked
        for i in range(self.file_type_list.count()):
            item = self.file_type_list.item(i)
            item.setCheckState(check_state)

    def on_file_type_item_clicked(self, item):
        """处理文件类型列表项点击事件"""
        text = item.text()
        # 如果点击的是"自定义"选项，启用/禁用输入框
        if "自定义" in text:
            is_checked = item.checkState() == Qt.CheckState.Checked
            self.custom_extensions_input.setEnabled(is_checked)
            if is_checked:
                self.custom_extensions_input.setFocus()

    def get_selected_extensions(self):
        extensions = set()
        for i in range(self.file_type_list.count()):
            item = self.file_type_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                text = item.text()
                # 处理"自定义"选项
                if "自定义" in text:
                    # 从输入框获取自定义扩展名
                    custom_ext_text = self.custom_extensions_input.text().strip()
                    if custom_ext_text:
                        # 保存自定义扩展名到配置
                        self.config.set("custom_extensions", custom_ext_text)
                        # 解析扩展名（支持空格或逗号分隔）
                        import re
                        # 移除多余的空格和换行
                        custom_ext_text = ' '.join(custom_ext_text.split())
                        # 匹配扩展名（支持 .ext 或 ext 格式）
                        ext_matches = re.findall(r'[,\s]?([.\w]+)', custom_ext_text)
                        for ext in ext_matches:
                            if ext:
                                # 确保以点开头
                                if not ext.startswith('.'):
                                    ext = f'.{ext}'
                                extensions.add(ext.lower())
                elif "所有文件" in text:
                    # 所有文件选中，返回 None 表示不筛选
                    return None
                elif "*.pdf" in text:
                    extensions.update(['.pdf'])
                elif "*.doc" in text:
                    extensions.update(['.doc', '.docx'])
                elif "*.xls" in text:
                    extensions.update(['.xls', '.xlsx'])
                elif "*.ppt" in text:
                    extensions.update(['.ppt', '.pptx'])
                elif "*.txt" in text:
                    extensions.add('.txt')
                else:
                    # Extract all extensions from parentheses
                    import re
                    matches = re.findall(r'\*\.(\\w+)', text)
                    extensions.update(f'.{ext}' for ext in matches)
        return extensions if extensions else None  # None means all files

    def browse_directory(self):
        path = QFileDialog.getExistingDirectory(self, "选择要扫描的目录")
        if path:
            self.selected_path = path
            self.path_label.setText(path)
            self.path_label.setStyleSheet("color: black;")
            self.scan_button.setEnabled(True)

    def start_scan(self):
        if not self.selected_path:
            QMessageBox.warning(self, "警告", "请先选择要扫描的目录")
            return

        extensions = self.get_selected_extensions()

        # 重置进度条和状态
        self.progress_bar.setValue(0)
        self.status_label.setText("准备扫描...")
        self.last_progress_update = 0

        # Initialize time tracking
        self.scan_start_time = time.time()
        self.last_progress_update = time.time()

        self.scan_thread = ScanThread(self.selected_path, extensions)
        self.scan_thread.progress_update.connect(self.update_progress)
        self.scan_thread.scan_complete.connect(self.scan_complete)
        self.scan_thread.error_occurred.connect(self.scan_error)
        self.scan_thread.start()

        self.scan_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.browse_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.smart_select_button.setEnabled(False)
        self.select_all_button.setEnabled(False)
        self.deselect_all_button.setEnabled(False)
        self.invert_selection_button.setEnabled(False)
        self.advanced_select_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.results_tree.clear()

    def stop_scan(self):
        if self.scan_thread:
            self.scan_thread.cancel()
        self.stop_button.setEnabled(False)
        self.statusBar().showMessage("正在停止...")

    def update_progress(self, current: int, total: int, stage: str):
        percentage = int((current / total * 100)) if total > 0 else 0
        self.progress_bar.setValue(percentage)

        # Calculate ETA
        eta_text = self._calculate_eta(current, total)

        if stage == "scan":
            text = f"扫描中... ({current}/{total})"
            if eta_text:
                text += f" - {eta_text}"
            self.status_label.setText(text)
        elif stage == "hash":
            text = f"计算哈希... ({current}/{total})"
            if eta_text:
                text += f" - {eta_text}"
            self.status_label.setText(text)

        self.last_progress_update = time.time()

    def _calculate_eta(self, current: int, total: int) -> str:
        """计算预计剩余时间"""
        if not self.scan_start_time or current <= 0 or total <= 0:
            return ""

        elapsed = time.time() - self.scan_start_time

        # Calculate progress rate
        progress_rate = current / elapsed if elapsed > 0 else 0

        if progress_rate <= 0:
            return ""

        # Calculate remaining time
        remaining = total - current
        eta_seconds = remaining / progress_rate if progress_rate > 0 else 0

        # Format ETA
        if eta_seconds < 60:
            return f"预计剩余 {int(eta_seconds)} 秒"
        elif eta_seconds < 3600:
            minutes = int(eta_seconds / 60)
            seconds = int(eta_seconds % 60)
            return f"预计剩余 {minutes} 分 {seconds} 秒"
        else:
            hours = int(eta_seconds / 3600)
            minutes = int((eta_seconds % 3600) / 60)
            return f"预计剩余 {hours} 小时 {minutes} 分"

    def stop_scan(self):
        if self.scan_thread:
            self.scan_thread.cancel()
        self.stop_button.setEnabled(False)
        self.statusBar().showMessage("正在停止...")

    def scan_complete(self, results: list, wasted_space: int, scanned_files: list = None):
        self.duplicate_groups = results
        # Store scanned files for similarity detection
        if scanned_files is not None:
            self.scanned_files = scanned_files
        self.populate_results(results)
        self.update_statistics(results, wasted_space)

        self.scan_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.browse_button.setEnabled(True)
        self.delete_button.setEnabled(len(results) > 0)
        self.smart_select_button.setEnabled(len(results) > 0)
        self.select_all_button.setEnabled(len(results) > 0)
        self.deselect_all_button.setEnabled(len(results) > 0)
        self.invert_selection_button.setEnabled(len(results) > 0)
        self.advanced_select_button.setEnabled(len(results) > 0)
        self.export_button.setEnabled(len(results) > 0)

        # Enable similarity button if we have scanned files
        if self.similarity_button and self.scanned_files:
            # Check if there are any image or video files
            has_images_or_videos = any(
                Path(f.path).suffix.lower() in SimilarityDetector.IMAGE_EXTENSIONS or
                Path(f.path).suffix.lower() in SimilarityDetector.VIDEO_EXTENSIONS
                for f in self.scanned_files
            ) if SIMILARITY_AVAILABLE else False
            self.similarity_button.setEnabled(has_images_or_videos)

        self.status_label.setText("扫描完成")

        # Check for permission errors
        if hasattr(self.scan_thread, 'scanner') and self.scan_thread.scanner:
            error_count, error_summary = self.scan_thread.scanner.get_permission_summary()
            if error_count > 0:
                self.statusBar().showMessage(f"扫描完成 - 找到 {len(results)} 组重复文件 - {error_summary}")
                # Show permission warning if there were errors
                if self.scan_thread.scanner.permission_errors:
                    self._show_permission_warning()
            else:
                self.statusBar().showMessage(f"扫描完成 - 找到 {len(results)} 组重复文件")
        else:
            self.statusBar().showMessage(f"扫描完成 - 找到 {len(results)} 组重复文件")

        # Reset time tracking
        self.scan_start_time = None
        self.last_progress_update = None

    def _show_permission_warning(self):
        """显示权限错误警告"""
        if not hasattr(self.scan_thread, 'scanner') or not self.scan_thread.scanner:
            return

        scanner = self.scan_thread.scanner
        if not scanner.permission_errors:
            return

        # Show warning dialog with permission errors
        error_list = [f"• {err.path}: {err.error}" for err in scanner.permission_errors[:10]]
        message = f"扫描过程中遇到权限问题，跳过了 {len(scanner.skipped_directories)} 个目录。\n\n"
        if len(scanner.permission_errors) > 10:
            message += f"前 10 个错误：\n" + "\n".join(error_list)
            message += f"\n\n... 还有 {len(scanner.permission_errors) - 10} 个错误"
        else:
            message += "错误列表：\n" + "\n".join(error_list)

        QMessageBox.warning(self, "权限问题", message)

    def scan_error(self, error: str):
        QMessageBox.critical(self, "错误", f"扫描过程中发生错误:\n{error}")
        self.scan_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.browse_button.setEnabled(True)
        self.status_label.setText("错误")

    def filter_results(self, search_text: str):
        """根据搜索文本过滤结果"""
        search_text_lower = search_text.lower().strip()

        root = self.results_tree.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)

            # Check if any file in this group matches
            group_has_match = False
            for j in range(group_item.childCount()):
                file_item = group_item.child(j)
                file_name = file_item.text(1).lower()
                file_path = file_item.text(2).lower()

                if search_text_lower in file_name or search_text_lower in file_path:
                    file_item.setHidden(False)
                    group_has_match = True
                else:
                    file_item.setHidden(True)

            # Hide group if no files match
            group_item.setHidden(not group_has_match)

        # Enable/disable clear button
        self.clear_search_button.setEnabled(bool(search_text))

        # Update status bar with filter info
        if search_text_lower:
            visible_groups = sum(1 for i in range(root.childCount())
                               if not root.child(i).isHidden())
            self.statusBar().showMessage(f"过滤: 显示 {visible_groups} 组结果")
        else:
            self.statusBar().showMessage("就绪")

    def clear_search(self):
        """清除搜索过滤"""
        self.search_input.clear()

    def update_file_preview(self):
        """更新文件预览"""
        selected_items = self.results_tree.selectedItems()
        if not selected_items:
            # No file selected
            self.preview_label.setVisible(True)
            self.preview_label.setText("选择一个文件以预览")
            self.preview_details.setVisible(False)
            self.preview_thumbnail.setVisible(False)
            return

        item = selected_items[0]

        # Check if it's a file item (has UserRole data) or a group item
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not file_path:
            # It's a group item, try to get first file
            if item.childCount() > 0:
                child = item.child(0)
                file_path = child.data(0, Qt.ItemDataRole.UserRole)
            else:
                self.preview_label.setVisible(True)
                self.preview_label.setText("此组为空")
                self.preview_details.setVisible(False)
                self.preview_thumbnail.setVisible(False)
                return

        if not file_path or not os.path.exists(file_path):
            self.preview_label.setVisible(True)
            self.preview_label.setText("文件不存在")
            self.preview_details.setVisible(False)
            self.preview_thumbnail.setVisible(False)
            return

        # Update preview
        self.preview_label.setVisible(False)
        self.preview_details.setVisible(True)
        self.preview_thumbnail.setVisible(True)

        # Get file info
        try:
            file_stat = os.stat(file_path)
            file_size = file_stat.st_size
            mtime = file_stat.st_mtime
            path_obj = Path(file_path)

            # Build preview text
            preview_text = f"文件名: {path_obj.name}\n"
            preview_text += f"路径: {path_obj.parent}\n"
            preview_text += f"大小: {format_size(file_size)}\n"
            preview_text += f"修改时间: {datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')}\n"

            # Add extension-specific info
            ext = path_obj.suffix.lower()
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                preview_text += f"类型: 图片文件\n"
            elif ext in ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv']:
                preview_text += f"类型: 视频文件\n"
            elif ext in ['.mp3', '.flac', '.aac', '.ogg', '.wav', '.m4a']:
                preview_text += f"类型: 音频文件\n"

            self.preview_details.setText(preview_text)

            # Try to load thumbnail for images
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                self._load_image_thumbnail(file_path)
            elif ext in ['.mp4', '.mkv', '.avi', '.mov']:
                self.preview_thumbnail.setText("🎬 [视频文件]")
                self.preview_thumbnail.setStyleSheet("border: 1px solid #cccccc; background-color: #f5f5f5; font-size: 40px;")
            else:
                self.preview_thumbnail.setText(f"📄 [{ext[1:].upper()} 文件]")
                self.preview_thumbnail.setStyleSheet("border: 1px solid #cccccc; background-color: #f5f5f5; font-size: 40px;")

        except Exception as e:
            self.preview_details.setText(f"无法读取文件信息:\n{e}")
            self.preview_thumbnail.setVisible(False)

    def _load_image_thumbnail(self, file_path: str):
        """加载图片缩略图"""
        try:
            from PyQt6.QtGui import QPixmap
            from PyQt6.QtCore import QSize

            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                # Scale thumbnail to fit while maintaining aspect ratio
                scaled = pixmap.scaled(
                    300, 200,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.preview_thumbnail.setPixmap(scaled)
                self.preview_thumbnail.setStyleSheet("border: 1px solid #cccccc;")
            else:
                self.preview_thumbnail.setText("无法加载图片")
                self.preview_thumbnail.setStyleSheet("border: 1px solid #cccccc; background-color: #f5f5f5;")
        except Exception:
            self.preview_thumbnail.setText("无法加载缩略图")
            self.preview_thumbnail.setStyleSheet("border: 1px solid #cccccc; background-color: #f5f5f5;")

    def populate_results(self, results: list):
        self.results_tree.clear()
        self.results_tree.itemChanged.disconnect()  # Disconnect during population

        try:
            for group in results:
                group_item = QTreeWidgetItem(self.results_tree)
                group_item.setText(1, f"重复组 ({len(group.files)} 个文件)")
                group_item.setText(2, f"哈希: {group.hash_value[:16]}...")
                group_item.setText(3, format_size(group.total_size))

                # Set bold font for group item
                font = group_item.font(1)
                font.setBold(True)
                group_item.setFont(1, font)

                # Don't allow group item to be checked
                group_item.setFlags(group_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)

                for file_info in group.files:
                    file_item = QTreeWidgetItem(group_item)
                    file_path = Path(file_info.path)

                    # Add checkbox
                    file_item.setFlags(file_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    file_item.setCheckState(0, Qt.CheckState.Unchecked)

                    file_item.setText(1, file_path.name)
                    file_item.setText(2, str(file_path.parent))
                    file_item.setText(3, format_size(file_info.size))

                    # Store full path in data for easy access
                    file_item.setData(0, Qt.ItemDataRole.UserRole, file_info.path)

            self.results_tree.expandAll()
        finally:
            self.results_tree.itemChanged.connect(self.on_item_changed)

    def on_item_changed(self, item: QTreeWidgetItem, column: int):
        # Update selected files count
        self.update_selected_count()

    def update_selected_count(self):
        count = 0
        root = self.results_tree.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)
            for j in range(group_item.childCount()):
                file_item = group_item.child(j)
                if file_item.checkState(0) == Qt.CheckState.Checked:
                    count += 1
        self.selected_files_label.setText(f"已选文件: {count}")

    def update_statistics(self, results: list, wasted_space: int):
        total_files = sum(len(group.files) for group in results)
        self.files_scanned_label.setText(f"重复文件数: {total_files}")
        self.duplicate_groups_label.setText(f"重复组数: {len(results)}")
        self.wasted_space_label.setText(f"浪费空间: {format_size(wasted_space)}")
        self.selected_files_label.setText(f"已选文件: 0")

    def delete_selected_files(self):
        selected_files = []
        root = self.results_tree.invisibleRootItem()

        # Collect selected files
        for i in range(root.childCount()):
            group_item = root.child(i)
            for j in range(group_item.childCount()):
                file_item = group_item.child(j)
                if file_item.checkState(0) == Qt.CheckState.Checked:
                    file_path = file_item.data(0, Qt.ItemDataRole.UserRole)
                    selected_files.append(file_path)

        if not selected_files:
            QMessageBox.warning(self, "警告", "请先选择要删除的文件")
            return

        # Confirm deletion with preview
        delete_mode = "移至回收站" if SEND2TRASH_AVAILABLE else "永久删除"
        warning_text = "此操作可以撤销" if SEND2TRASH_AVAILABLE else "此操作不可恢复！"

        # Create preview dialog
        preview_text = f"确定要删除 {len(selected_files)} 个文件吗？\n\n模式: {delete_mode}\n{warning_text}\n\n前 10 个文件：\n"
        for i, path in enumerate(selected_files[:10]):
            preview_text += f"  • {Path(path).name}\n"
        if len(selected_files) > 10:
            preview_text += f"  ... 还有 {len(selected_files) - 10} 个文件\n"

        reply = QMessageBox.question(
            self,
            "确认删除",
            preview_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.perform_delete(selected_files)

    def perform_delete(self, files_to_delete: list):
        deleted_count = 0
        failed_files = []
        deleted_files_info = []

        # Calculate total size for history
        total_size = 0

        for file_path in files_to_delete:
            try:
                if os.path.exists(file_path):
                    # Get file size before deletion
                    file_size = os.path.getsize(file_path)
                    total_size += file_size

                    # Use send2trash if available, otherwise permanent delete
                    if SEND2TRASH_AVAILABLE:
                        send2trash(file_path)
                    else:
                        os.remove(file_path)

                    deleted_count += 1
                    deleted_files_info.append({
                        'path': file_path,
                        'size': file_size,
                        'name': Path(file_path).name,
                        'deleted_at': datetime.now().isoformat()
                    })
                else:
                    failed_files.append(f"{file_path} (文件不存在)")
            except Exception as e:
                failed_files.append(f"{file_path} ({str(e)})")

        # Save deletion history
        if deleted_files_info:
            self._save_deletion_record(deleted_files_info)

        # Show result
        mode_text = "移至回收站" if SEND2TRASH_AVAILABLE else "删除"
        if failed_files:
            QMessageBox.warning(
                self,
                "删除完成",
                f"成功{mode_text}: {deleted_count} 个文件\n"
                f"释放空间: {format_size(total_size)}\n\n"
                f"失败:\n" + "\n".join(failed_files[:10])
            )
        else:
            QMessageBox.information(
                self,
                "删除完成",
                f"成功{mode_text} {deleted_count} 个文件\n"
                f"释放空间: {format_size(total_size)}\n\n"
                f"提示：可在删除历史中查看已删除的文件"
            )

        # Refresh results
        if self.scan_thread and self.scan_thread.isRunning():
            return
        else:
            # Clear results and suggest rescan
            self.results_tree.clear()
            self.duplicate_groups = []
            self.delete_button.setEnabled(False)
            self.smart_select_button.setEnabled(False)
            self.select_all_button.setEnabled(False)
            self.deselect_all_button.setEnabled(False)
            self.files_scanned_label.setText("扫描文件数: 0")
            self.duplicate_groups_label.setText("重复组数: 0")
            self.wasted_space_label.setText("浪费空间: 0 B")
            self.selected_files_label.setText("已选文件: 0")
            self.statusBar().showMessage("文件已删除，请重新扫描")

    def show_context_menu(self, position: QPoint):
        item = self.results_tree.itemAt(position)
        if not item:
            return

        # Only show context menu for file items (not group items)
        if item.parent() is None:
            return

        # Get the file path from the item data
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not file_path:
            return

        menu = QMenu(self)

        # Add "Open File Location" action
        open_location_action = QAction("打开文件所在位置", self)
        open_location_action.triggered.connect(lambda: self.open_file_location(file_path))
        menu.addAction(open_location_action)

        # Show the menu at the cursor position
        menu.exec(self.results_tree.mapToGlobal(position))

    def open_file_location(self, file_path: str):
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "错误", f"文件不存在:\n{file_path}")
            return

        try:
            system = platform.system()

            if system == "Darwin":  # macOS
                subprocess.run(["open", "-R", file_path])
            elif system == "Windows":
                subprocess.run(["explorer", "/select,", file_path])
            else:  # Linux and others
                # Open the parent directory and select the file
                file_dir = os.path.dirname(file_path)
                subprocess.run(["xdg-open", file_dir])
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开文件位置:\n{str(e)}")

    def show_smart_select_dialog(self):
        """显示智能选择对话框"""
        if not self.duplicate_groups:
            QMessageBox.warning(self, "警告", "没有可选择的重复文件")
            return

        dialog = SmartSelectDialog(self.duplicate_groups, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            strategy = dialog.get_selected_strategy()
            self.apply_smart_selection(strategy)

    def apply_smart_selection(self, strategy: dict):
        """应用智能选择策略"""
        self.results_tree.itemChanged.disconnect()

        try:
            root = self.results_tree.invisibleRootItem()
            total_selected = 0
            total_space = 0

            for i in range(root.childCount()):
                group_item = root.child(i)

                # Get all file items in this group with their info
                file_items = []
                for j in range(group_item.childCount()):
                    file_item = group_item.child(j)
                    file_path = file_item.data(0, Qt.ItemDataRole.UserRole)
                    # Find corresponding FileInfo
                    file_info = None
                    for group in self.duplicate_groups:
                        for f in group.files:
                            if f.path == file_path:
                                file_info = f
                                break
                        if file_info:
                            break

                    if file_info:
                        file_items.append((file_item, file_info))

                # Apply selection strategy
                to_select = self._select_files_by_strategy(file_items, strategy)

                # Set check states
                for file_item, file_info in file_items:
                    if file_item in to_select:
                        file_item.setCheckState(0, Qt.CheckState.Checked)
                        total_selected += 1
                        total_space += file_info.size
                    else:
                        file_item.setCheckState(0, Qt.CheckState.Unchecked)

            self.update_selected_count()

            # Show summary
            QMessageBox.information(
                self,
                "智能选择完成",
                f"已选择 {total_selected} 个文件\n预计释放空间: {format_size(total_space)}"
            )
        finally:
            self.results_tree.itemChanged.connect(self.on_item_changed)

    def _select_files_by_strategy(self, file_items: list, strategy: dict):
        """根据策略选择要删除的文件"""
        strategy_type = strategy.get('type')
        to_delete = []  # 改为列表，QTreeWidgetItem 不可哈希
        to_keep = []    # 改为列表

        if strategy_type == 'keep_one':
            # 每组只保留第一个文件
            if file_items:
                to_keep.append(file_items[0][0])
                for item, _ in file_items[1:]:
                    to_delete.append(item)

        elif strategy_type == 'keep_shortest_path':
            # 保留路径最短的文件
            file_items.sort(key=lambda x: len(x[1].path))
            to_keep.append(file_items[0][0])
            for item, _ in file_items[1:]:
                to_delete.append(item)

        elif strategy_type == 'keep_longest_path':
            # 保留路径最长的文件
            file_items.sort(key=lambda x: len(x[1].path), reverse=True)
            to_keep.append(file_items[0][0])
            for item, _ in file_items[1:]:
                to_delete.append(item)

        elif strategy_type == 'keep_newest':
            # 保留最新的文件（按修改时间）
            file_items.sort(key=lambda x: x[1].mtime, reverse=True)
            to_keep.append(file_items[0][0])
            for item, _ in file_items[1:]:
                to_delete.append(item)

        elif strategy_type == 'keep_oldest':
            # 保留最旧的文件
            file_items.sort(key=lambda x: x[1].mtime)
            to_keep.append(file_items[0][0])
            for item, _ in file_items[1:]:
                to_delete.append(item)

        elif strategy_type == 'keep_by_pattern':
            # 保留匹配模式的文件
            pattern = strategy.get('pattern', '')
            import re
            regex = re.compile(pattern)

            matched = [item for item, info in file_items if regex.search(info.path)]
            not_matched = [item for item, info in file_items if not regex.search(info.path)]

            if strategy.get('action') == 'keep':
                # 保留匹配的，删除不匹配的
                to_keep.extend(matched)
                to_delete.extend(not_matched)
            else:
                # 删除匹配的，保留不匹配的
                to_delete.extend(matched)
                to_keep.extend(not_matched)

            # 如果没有保留任何文件，保留第一个
            if not to_keep and file_items:
                to_keep.append(file_items[0][0])
                if file_items[0][0] in to_delete:
                    to_delete.remove(file_items[0][0])

        elif strategy_type == 'keep_smallest':
            # 保留最小的文件
            file_items.sort(key=lambda x: x[1].size)
            to_keep.append(file_items[0][0])
            for item, _ in file_items[1:]:
                to_delete.append(item)

        elif strategy_type == 'keep_largest':
            # 保留最大的文件
            file_items.sort(key=lambda x: x[1].size, reverse=True)
            to_keep.append(file_items[0][0])
            for item, _ in file_items[1:]:
                to_delete.append(item)

        # 确保每组至少保留一个文件
        if not to_keep and file_items:
            to_keep.append(file_items[0][0])
            if file_items[0][0] in to_delete:
                to_delete.remove(file_items[0][0])

        return to_delete

    def select_all_files(self):
        """全选所有文件"""
        self.results_tree.itemChanged.disconnect()
        try:
            root = self.results_tree.invisibleRootItem()
            for i in range(root.childCount()):
                group_item = root.child(i)
                for j in range(group_item.childCount()):
                    file_item = group_item.child(j)
                    file_item.setCheckState(0, Qt.CheckState.Checked)
            self.update_selected_count()
        finally:
            self.results_tree.itemChanged.connect(self.on_item_changed)

    def deselect_all_files(self):
        """取消选择所有文件"""
        self.results_tree.itemChanged.disconnect()
        try:
            root = self.results_tree.invisibleRootItem()
            for i in range(root.childCount()):
                group_item = root.child(i)
                for j in range(group_item.childCount()):
                    file_item = group_item.child(j)
                    file_item.setCheckState(0, Qt.CheckState.Unchecked)
            self.update_selected_count()
        finally:
            self.results_tree.itemChanged.connect(self.on_item_changed)

    def invert_selection(self):
        """反选所有文件"""
        self.results_tree.itemChanged.disconnect()
        try:
            root = self.results_tree.invisibleRootItem()
            for i in range(root.childCount()):
                group_item = root.child(i)
                for j in range(group_item.childCount()):
                    file_item = group_item.child(j)
                    current_state = file_item.checkState(0)
                    new_state = Qt.CheckState.Unchecked if current_state == Qt.CheckState.Checked else Qt.CheckState.Checked
                    file_item.setCheckState(0, new_state)
            self.update_selected_count()
        finally:
            self.results_tree.itemChanged.connect(self.on_item_changed)

    def show_advanced_select_dialog(self):
        """显示高级选择对话框"""
        if not self.duplicate_groups:
            QMessageBox.warning(self, "警告", "没有可选择的重复文件")
            return

        dialog = AdvancedSelectDialog(self.results_tree, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Update selection count
            self.update_selected_count()

    def select_by_directory(self, directory: str, select: bool = True):
        """按目录选择/取消选择"""
        self.results_tree.itemChanged.disconnect()
        try:
            root = self.results_tree.invisibleRootItem()
            for i in range(root.childCount()):
                group_item = root.child(i)
                for j in range(group_item.childCount()):
                    file_item = group_item.child(j)
                    file_path = file_item.data(0, Qt.ItemDataRole.UserRole)
                    if directory in file_path:
                        file_item.setCheckState(0, Qt.CheckState.Checked if select else Qt.CheckState.Unchecked)
            self.update_selected_count()
        finally:
            self.results_tree.itemChanged.connect(self.on_item_changed)

    def select_by_size_range(self, min_size: int, max_size: int, select: bool = True):
        """按大小范围选择/取消选择"""
        self.results_tree.itemChanged.disconnect()
        try:
            root = self.results_tree.invisibleRootItem()
            for i in range(root.childCount()):
                group_item = root.child(i)
                for j in range(group_item.childCount()):
                    file_item = group_item.child(j)
                    # Get file size from the size column
                    size_text = file_item.text(3)
                    # Parse size text (e.g., "1.23 MB")
                    size_bytes = self._parse_size_string(size_text)
                    if min_size <= size_bytes <= max_size:
                        file_item.setCheckState(0, Qt.CheckState.Checked if select else Qt.CheckState.Unchecked)
            self.update_selected_count()
        finally:
            self.results_tree.itemChanged.connect(self.on_item_changed)

    @staticmethod
    def _parse_size_string(size_str: str) -> int:
        """解析大小字符串为字节数"""
        size_str = size_str.strip().upper()
        units = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}

        for unit, multiplier in units.items():
            if unit in size_str:
                value = float(size_str.replace(unit, '').strip())
                return int(value * multiplier)

        return 0

    def _load_deletion_history(self) -> list:
        """加载删除历史记录"""
        try:
            if os.path.exists(self.DELETION_HISTORY_FILE):
                with open(self.DELETION_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            self.log.warning(f"加载删除历史失败: {e}")
        return []

    def _save_deletion_record(self, files_info: list):
        """保存删除记录到历史"""
        record = {
            'timestamp': datetime.now().isoformat(),
            'count': len(files_info),
            'total_size': sum(f['size'] for f in files_info),
            'files': files_info
        }

        self.deletion_history.append(record)

        # Keep only last 100 records
        if len(self.deletion_history) > 100:
            self.deletion_history = self.deletion_history[-100:]

        try:
            with open(self.DELETION_HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.deletion_history, f, ensure_ascii=False, indent=2)
            self.log.info(f"保存删除记录: {len(files_info)} 个文件")
        except Exception as e:
            self.log.error(f"保存删除历史失败: {e}")

    def toggle_theme(self):
        """切换主题"""
        self.dark_mode = not self.dark_mode

        if self.dark_mode:
            self.setStyleSheet(ThemeManager.get_dark_theme())
            self.theme_action.setText("切换到浅色模式")
            self.config.set("theme", "dark")
        else:
            self.setStyleSheet(ThemeManager.get_light_theme())
            self.theme_action.setText("切换到深色模式")
            self.config.set("theme", "light")

        self.statusBar().showMessage(f"已切换到{'深色' if self.dark_mode else '浅色'}模式", 2000)

    def resizeEvent(self, event):
        """窗口大小改变时保存"""
        super().resizeEvent(event)
        if self.config.get("remember_window_size", True):
            self.config.set("window_width", self.width(), save=False)
            self.config.set("window_height", self.height(), save=False)
            # 延迟保存以避免频繁写入
            # 注意：实际应用中可能需要更复杂的去抖动逻辑

    def closeEvent(self, event):
        """窗口关闭时保存配置"""
        # Save config on close
        self.config.save_config()
        super().closeEvent(event)

    def show_export_dialog(self):
        """显示导出对话框"""
        if not self.duplicate_groups:
            QMessageBox.warning(self, "警告", "没有可导出的扫描结果")
            return

        dialog = ExportDialog(self.duplicate_groups, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            format_type, output_path, include_metadata = dialog.get_export_settings()
            if output_path:
                self.perform_export(format_type, output_path, include_metadata)

    def perform_export(self, format_type: str, output_path: str, include_metadata: bool):
        """执行导出操作"""
        exporter = ExportManager()
        success = False

        if format_type == 'csv':
            success = exporter.export_to_csv(self.duplicate_groups, output_path, include_metadata)
        elif format_type == 'json':
            success = exporter.export_to_json(self.duplicate_groups, output_path, include_metadata)
        elif format_type == 'html':
            success = exporter.export_to_html(self.duplicate_groups, output_path)

        if success:
            QMessageBox.information(
                self,
                "导出成功",
                f"报告已成功导出到:\n{output_path}"
            )
            self.statusBar().showMessage(f"报告已导出到: {output_path}")
        else:
            QMessageBox.critical(
                self,
                "导出失败",
                f"导出报告时发生错误:\n{output_path}"
            )

    def show_similarity_dialog(self):
        """显示相似度检测对话框"""
        if not self.scanned_files:
            QMessageBox.warning(self, "警告", "请先扫描文件")
            return

        dialog = SimilarityDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            settings = dialog.get_settings()
            self.start_similarity_scan(settings)

    def start_similarity_scan(self, settings: dict):
        """开始相似度扫描"""
        if not SIMILARITY_AVAILABLE:
            QMessageBox.warning(self, "警告", "相似度检测功能不可用，请安装必要的依赖库")
            return

        # Filter files based on settings
        files_to_scan = []
        for file_info in self.scanned_files:
            ext = Path(file_info.path).suffix.lower()
            if settings['check_images'] and ext in SimilarityDetector.IMAGE_EXTENSIONS:
                files_to_scan.append(file_info)
            elif settings['check_videos'] and ext in SimilarityDetector.VIDEO_EXTENSIONS:
                files_to_scan.append(file_info)

        if not files_to_scan:
            QMessageBox.warning(self, "警告", "没有找到符合条件的图片或视频文件")
            return

        # Initialize detector with settings
        self.similarity_detector = SimilarityDetector()
        self.similarity_detector.set_threshold(settings['threshold'])
        method_map = {
            'perceptual_hash': SimilarityMethod.PERCEPTUAL_HASH,
            'average_hash': SimilarityMethod.AVERAGE_HASH,
            'difference_hash': SimilarityMethod.DIFFERENCE_HASH,
            'wavelet_hash': SimilarityMethod.WAVELET_HASH,
        }
        self.similarity_detector.set_method(method_map.get(settings['method'], SimilarityMethod.PERCEPTUAL_HASH))

        # Start scan thread
        self.similarity_thread = SimilarityScanThread(files_to_scan, self.similarity_detector)
        self.similarity_thread.progress_update.connect(self.update_similarity_progress)
        self.similarity_thread.scan_complete.connect(self.similarity_scan_complete)
        self.similarity_thread.error_occurred.connect(self.similarity_scan_error)
        self.similarity_thread.start()

        # Update UI
        self.similarity_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("正在检测相似文件...")
        self.statusBar().showMessage("正在检测相似文件...")

    def update_similarity_progress(self, current: int, total: int):
        """更新相似度扫描进度"""
        percentage = int((current / total * 100)) if total > 0 else 0
        self.progress_bar.setValue(percentage)
        self.status_label.setText(f"检测相似文件... ({current}/{total})")

    def similarity_scan_complete(self, similar_images: list, similar_videos: list):
        """相似度扫描完成"""
        self.similarity_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.progress_bar.setValue(100)

        total_groups = len(similar_images) + len(similar_videos)
        if total_groups == 0:
            QMessageBox.information(
                self,
                "扫描完成",
                "未找到相似的文件。\n\n您可以尝试降低相似度阈值来获得更多结果。"
            )
            self.status_label.setText("相似度检测完成")
            return

        # Display results in a new dialog
        self.show_similarity_results(similar_images, similar_videos)

        self.status_label.setText(f"相似度检测完成 - 找到 {total_groups} 组相似文件")
        self.statusBar().showMessage(f"相似度检测完成 - 找到 {total_groups} 组相似文件")

    def similarity_scan_error(self, error_message: str):
        """相似度扫描错误"""
        self.similarity_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        QMessageBox.critical(
            self,
            "扫描错误",
            f"相似度检测过程中发生错误:\n{error_message}"
        )
        self.status_label.setText("相似度检测失败")

    def show_similarity_results(self, similar_images: list, similar_videos: list):
        """显示相似度检测结果"""
        dialog = SimilarityResultsDialog(similar_images, similar_videos, self)
        dialog.exec()

    def toggle_theme(self):
        """切换深色/浅色主题"""
        if self.dark_mode:
            self.dark_mode = False
            self.setStyleSheet(ThemeManager.get_light_theme())
            self.theme_action.setText("切换到深色模式")
            self.config.set("theme", "light")
        else:
            self.dark_mode = True
            self.setStyleSheet(ThemeManager.get_dark_theme())
            self.theme_action.setText("切换到浅色模式")
            self.config.set("theme", "dark")
        self.config.save()

    def closeEvent(self, event):
        """窗口关闭事件"""
        # Stop any running scans
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.cancel()
        if self.similarity_thread and self.similarity_thread.isRunning():
            self.similarity_thread.cancel()

        # Save window size if enabled
        if self.config.get("remember_window_size", True):
            self.config.set("window_width", self.width())
            self.config.set("window_height", self.height())

        # Save settings
        self.config.save()

        event.accept()


class SmartSelectDialog(QDialog):
    """智能选择策略对话框"""

    def __init__(self, duplicate_groups: list, parent=None):
        super().__init__(parent)
        self.duplicate_groups = duplicate_groups
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("智能选择策略")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # 说明文本
        info_label = QLabel("选择自动选择重复文件的策略：\n每组重复文件将根据所选策略自动选择要删除的文件")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # 策略选择
        strategy_group = QGroupBox("选择策略")
        strategy_layout = QVBoxLayout()
        self.strategy_group = QButtonGroup()

        strategies = [
            ('keep_one', '每组保留一个文件（保留第一个）'),
            ('keep_shortest_path', '保留路径最短的文件（推荐）'),
            ('keep_longest_path', '保留路径最长的文件'),
            ('keep_newest', '保留最新的文件（按修改时间）'),
            ('keep_oldest', '保留最旧的文件（按修改时间）'),
            ('keep_smallest', '保留最小的文件'),
            ('keep_largest', '保留最大的文件'),
        ]

        for i, (value, text) in enumerate(strategies):
            radio = QRadioButton(text)
            self.strategy_group.addButton(radio, i)
            radio.setProperty('strategy_type', value)
            strategy_layout.addWidget(radio)
            if i == 1:  # 默认选择"保留路径最短"
                radio.setChecked(True)

        strategy_group.setLayout(strategy_layout)
        layout.addWidget(strategy_group)

        # 高级选项：按路径模式选择
        pattern_group = QGroupBox("按路径模式选择（高级）")
        pattern_layout = QVBoxLayout()

        self.use_pattern_checkbox = QCheckBox("使用路径模式")
        pattern_layout.addWidget(self.use_pattern_checkbox)

        pattern_input_layout = QHBoxLayout()
        pattern_input_layout.addWidget(QLabel("模式（正则表达式）:"))
        self.pattern_input = QLineEdit()
        self.pattern_input.setPlaceholderText("例如: /Downloads/ 或 .*backup.*")
        pattern_input_layout.addWidget(self.pattern_input)
        pattern_layout.addLayout(pattern_input_layout)

        pattern_action_layout = QHBoxLayout()
        self.pattern_action_keep = QRadioButton("保留匹配的文件")
        self.pattern_action_delete = QRadioButton("删除匹配的文件")
        self.pattern_action_keep.setChecked(True)
        pattern_action_layout.addWidget(self.pattern_action_keep)
        pattern_action_layout.addWidget(self.pattern_action_delete)
        pattern_layout.addLayout(pattern_action_layout)

        pattern_group.setLayout(pattern_layout)
        pattern_group.setEnabled(False)
        self.pattern_group = pattern_group
        layout.addWidget(pattern_group)

        self.use_pattern_checkbox.toggled.connect(pattern_group.setEnabled)

        # 统计信息
        stats_text = self._get_stats_text()
        stats_label = QLabel(stats_text)
        stats_label.setWordWrap(True)
        layout.addWidget(stats_label)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _get_stats_text(self) -> str:
        """获取统计信息"""
        total_files = sum(len(g.files) for g in self.duplicate_groups)
        total_groups = len(self.duplicate_groups)
        potential_delete = total_files - total_groups

        return f"\n统计信息：\n• 重复文件组数: {total_groups}\n• 重复文件总数: {total_files}\n• 最多可删除: {potential_delete} 个文件\n"

    def get_selected_strategy(self) -> dict:
        """获取选中的策略"""
        if self.use_pattern_checkbox.isChecked():
            pattern = self.pattern_input.text().strip()
            if not pattern:
                return {'type': 'keep_one'}

            action = 'keep' if self.pattern_action_keep.isChecked() else 'delete'
            return {
                'type': 'keep_by_pattern',
                'pattern': pattern,
                'action': action
            }

        checked = self.strategy_group.checkedButton()
        if checked:
            return {'type': checked.property('strategy_type')}

        return {'type': 'keep_one'}


class ExportDialog(QDialog):
    """导出设置对话框"""

    def __init__(self, duplicate_groups: list, parent=None):
        super().__init__(parent)
        self.duplicate_groups = duplicate_groups
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("导出扫描报告")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # 说明文本
        info_label = QLabel("选择导出格式和选项：")
        layout.addWidget(info_label)

        # 格式选择
        format_group = QGroupBox("导出格式")
        format_layout = QVBoxLayout()
        self.format_group = QButtonGroup()

        formats = [
            ('html', 'HTML 网页报告（推荐，包含图表和样式）'),
            ('csv', 'CSV 表格（可在 Excel 中打开）'),
            ('json', 'JSON 数据（用于程序处理）'),
        ]

        for i, (value, text) in enumerate(formats):
            radio = QRadioButton(text)
            self.format_group.addButton(radio, i)
            radio.setProperty('format_type', value)
            format_layout.addWidget(radio)
            if i == 0:  # Default to HTML
                radio.setChecked(True)

        format_group.setLayout(format_layout)
        layout.addWidget(format_group)

        # 选项
        options_group = QGroupBox("选项")
        options_layout = QVBoxLayout()

        self.include_metadata_checkbox = QCheckBox("包含完整元数据（文件名、修改时间等）")
        self.include_metadata_checkbox.setChecked(True)
        options_layout.addWidget(self.include_metadata_checkbox)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # 输出路径
        path_group = QGroupBox("输出路径")
        path_layout = QHBoxLayout()

        self.path_input = QLineEdit()
        self.path_input.setText(f"duplicate_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
        path_layout.addWidget(self.path_input)

        self.browse_button = QPushButton("浏览...")
        self.browse_button.clicked.connect(self.browse_output_path)
        path_layout.addWidget(self.browse_button)

        path_group.setLayout(path_layout)
        layout.addWidget(path_group)

        # 统计信息
        stats_text = self._get_stats_text()
        stats_label = QLabel(stats_text)
        stats_label.setWordWrap(True)
        layout.addWidget(stats_label)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Connect format change to update default extension
        self.format_group.buttonClicked.connect(self.on_format_changed)

    def _get_stats_text(self) -> str:
        """获取统计信息"""
        total_files = sum(len(g.files) for g in self.duplicate_groups)
        total_groups = len(self.duplicate_groups)
        total_size = sum(g.total_size for g in self.duplicate_groups)

        return f"\n统计信息：\n• 重复文件组: {total_groups}\n• 重复文件总数: {total_files}\n• 总大小: {self._format_size(total_size)}\n"

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"

    def on_format_changed(self):
        """格式改变时更新默认扩展名"""
        current_path = self.path_input.text()
        base_name = Path(current_path).stem

        checked = self.format_group.checkedButton()
        if checked:
            format_type = checked.property('format_type')
            self.path_input.setText(f"{base_name}.{format_type}")

    def browse_output_path(self):
        """浏览输出路径"""
        checked = self.format_group.checkedButton()
        if checked:
            format_type = checked.property('format_type')

            if format_type == 'html':
                filter_str = "HTML 文件 (*.html)"
            elif format_type == 'csv':
                filter_str = "CSV 文件 (*.csv)"
            else:
                filter_str = "JSON 文件 (*.json)"

            path, _ = QFileDialog.getSaveFileName(
                self,
                "选择导出路径",
                self.path_input.text(),
                filter_str
            )

            if path:
                self.path_input.setText(path)

    def validate_and_accept(self):
        """验证并接受"""
        output_path = self.path_input.text().strip()
        if not output_path:
            QMessageBox.warning(self, "警告", "请选择输出路径")
            return

        self.accept()

    def get_export_settings(self) -> tuple:
        """获取导出设置"""
        checked = self.format_group.checkedButton()
        format_type = checked.property('format_type') if checked else 'html'

        output_path = self.path_input.text().strip()
        include_metadata = self.include_metadata_checkbox.isChecked()

        return format_type, output_path, include_metadata


class AdvancedSelectDialog(QDialog):
    """高级选择对话框"""

    def __init__(self, results_tree: QTreeWidget, parent=None):
        super().__init__(parent)
        self.results_tree = results_tree
        self.parent_window = parent
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("高级选择")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # 说明文本
        info_label = QLabel("按条件批量选择文件：")
        layout.addWidget(info_label)

        # 按目录选择
        directory_group = QGroupBox("按目录选择")
        directory_layout = QVBoxLayout()

        dir_input_layout = QHBoxLayout()
        dir_input_layout.addWidget(QLabel("目录包含:"))
        self.directory_input = QLineEdit()
        self.directory_input.setPlaceholderText("输入目录路径的一部分，如 /Downloads/")
        dir_input_layout.addWidget(self.directory_input)
        directory_layout.addLayout(dir_input_layout)

        dir_button_layout = QHBoxLayout()
        self.select_dir_button = QPushButton("选择匹配的文件")
        self.select_dir_button.clicked.connect(lambda: self.select_by_directory(True))
        self.deselect_dir_button = QPushButton("取消选择匹配的文件")
        self.deselect_dir_button.clicked.connect(lambda: self.select_by_directory(False))
        dir_button_layout.addWidget(self.select_dir_button)
        dir_button_layout.addWidget(self.deselect_dir_button)
        directory_layout.addLayout(dir_button_layout)

        directory_group.setLayout(directory_layout)
        layout.addWidget(directory_group)

        # 按大小范围选择
        size_group = QGroupBox("按大小范围选择")
        size_layout = QVBoxLayout()

        size_input_layout = QHBoxLayout()
        size_input_layout.addWidget(QLabel("最小:"))
        self.min_size_input = QLineEdit()
        self.min_size_input.setPlaceholderText("例如: 10 MB")
        self.min_size_input.setText("1 MB")
        size_input_layout.addWidget(self.min_size_input)
        size_input_layout.addWidget(QLabel("最大:"))
        self.max_size_input = QLineEdit()
        self.max_size_input.setPlaceholderText("例如: 100 MB")
        self.max_size_input.setText("10 GB")
        size_input_layout.addWidget(self.max_size_input)
        size_layout.addLayout(size_input_layout)

        size_button_layout = QHBoxLayout()
        self.select_size_button = QPushButton("选择范围内的文件")
        self.select_size_button.clicked.connect(lambda: self.select_by_size_range(True))
        self.deselect_size_button = QPushButton("取消选择范围内的文件")
        self.deselect_size_button.clicked.connect(lambda: self.select_by_size_range(False))
        size_button_layout.addWidget(self.select_size_button)
        size_button_layout.addWidget(self.deselect_size_button)
        size_layout.addLayout(size_button_layout)

        size_group.setLayout(size_layout)
        layout.addWidget(size_group)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def select_by_directory(self, select: bool):
        """按目录选择"""
        directory = self.directory_input.text().strip()
        if not directory:
            QMessageBox.warning(self, "警告", "请输入目录路径")
            return

        self.parent_window.select_by_directory(directory, select)
        QMessageBox.information(
            self,
            "完成",
            f"已{'选择' if select else '取消选择'}包含 '{directory}' 的文件"
        )

    def select_by_size_range(self, select: bool):
        """按大小范围选择"""
        min_str = self.min_size_input.text().strip()
        max_str = self.max_size_input.text().strip()

        try:
            min_size = self.parent_window._parse_size_string(min_str)
            max_size = self.parent_window._parse_size_string(max_str)

            if min_size == 0 or max_size == 0:
                QMessageBox.warning(self, "警告", "请输入有效的大小值")
                return

            self.parent_window.select_by_size_range(min_size, max_size, select)
            QMessageBox.information(
                self,
                "完成",
                f"已{'选择' if select else '取消选择'}大小在 {min_str} 到 {max_str} 范围内的文件"
            )
        except Exception as e:
            QMessageBox.warning(self, "错误", f"解析大小失败: {e}")


class SimilarityResultsDialog(QDialog):
    """相似度检测结果对话框"""

    def __init__(self, similar_images: list, similar_videos: list, parent=None):
        super().__init__(parent)
        self.similar_images = similar_images
        self.similar_videos = similar_videos
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("相似文件检测结果")
        self.setMinimumSize(800, 600)

        layout = QVBoxLayout(self)

        # 统计信息
        total_groups = len(self.similar_images) + len(self.similar_videos)
        total_files = sum(len(g.similar_files) + 1 for g in self.similar_images) + \
                      sum(len(g.similar_files) + 1 for g in self.similar_videos)

        stats_label = QLabel(f"找到 {total_groups} 组相似文件，共 {total_files} 个文件")
        stats_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(stats_label)

        # 创建标签页
        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)

        # 图片相似度结果
        if self.similar_images:
            images_tab = QWidget()
            images_layout = QVBoxLayout(images_tab)
            images_list = self._create_similarity_list(self.similar_images, "图片")
            images_layout.addWidget(images_list)
            tab_widget.addTab(images_tab, f"相似图片 ({len(self.similar_images)} 组)")

        # 视频相似度结果
        if self.similar_videos:
            videos_tab = QWidget()
            videos_layout = QVBoxLayout(videos_tab)
            videos_list = self._create_similarity_list(self.similar_videos, "视频")
            videos_layout.addWidget(videos_list)
            tab_widget.addTab(videos_tab, f"相似视频 ({len(self.similar_videos)} 组)")

        # 关闭按钮
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)

    def _create_similarity_list(self, groups: list, file_type: str) -> QTreeWidget:
        """创建相似文件列表"""
        tree = QTreeWidget()
        tree.setHeaderLabels(["参考文件", "相似文件", "相似度", "路径"])
        tree.setColumnWidth(0, 200)
        tree.setColumnWidth(1, 200)
        tree.setColumnWidth(2, 80)

        for i, group in enumerate(groups):
            group_item = QTreeWidgetItem(tree)
            ref_path = Path(group.reference_file)
            group_item.setText(0, ref_path.name)
            group_item.setText(3, str(ref_path.parent))

            # Set bold font for group item
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)

            # Add similar files
            for similar_file in group.similar_files:
                file_item = QTreeWidgetItem(group_item)
                sim_path = Path(similar_file.file_path)
                file_item.setText(0, "")
                file_item.setText(1, sim_path.name)
                file_item.setText(2, f"{similar_file.similarity:.1f}%")
                file_item.setText(3, str(sim_path.parent))

                # Color code based on similarity
                if similar_file.similarity >= 90:
                    file_item.setForeground(2, Qt.GlobalColor.darkGreen)
                elif similar_file.similarity >= 80:
                    file_item.setForeground(2, Qt.GlobalColor.darkYellow)
                else:
                    file_item.setForeground(2, Qt.GlobalColor.darkRed)

        tree.expandAll()
        return tree


class SimilarityDialog(QDialog):
    """相似度检测设置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("相似文件检测设置")
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        # 说明文本
        info_label = QLabel("检测近似相似的图片和视频文件（基于感知哈希算法）：")
        layout.addWidget(info_label)

        # 文件类型选择
        type_group = QGroupBox("文件类型")
        type_layout = QVBoxLayout()
        self.check_images = QCheckBox("检测相似图片")
        self.check_images.setChecked(True)
        self.check_videos = QCheckBox("检测相似视频")
        self.check_videos.setChecked(True)
        type_layout.addWidget(self.check_images)
        type_layout.addWidget(self.check_videos)
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)

        # 相似度阈值
        threshold_group = QGroupBox("相似度阈值")
        threshold_layout = QVBoxLayout()
        threshold_info = QLabel("设置相似度百分比（0-100），值越高匹配越严格")
        threshold_info.setWordWrap(True)
        threshold_layout.addWidget(threshold_info)

        threshold_input_layout = QHBoxLayout()
        threshold_input_layout.addWidget(QLabel("阈值:"))
        self.threshold_spinbox = QSpinBox()
        self.threshold_spinbox.setRange(0, 100)
        self.threshold_spinbox.setValue(80)
        self.threshold_spinbox.setSuffix(" %")
        threshold_input_layout.addWidget(self.threshold_spinbox)
        threshold_input_layout.addStretch()
        threshold_layout.addLayout(threshold_input_layout)

        threshold_help = QLabel("提示: 80% 适合大多数情况，90%+ 只匹配非常相似的文件")
        threshold_help.setStyleSheet("color: gray; font-size: 11px;")
        threshold_help.setWordWrap(True)
        threshold_layout.addWidget(threshold_help)

        threshold_group.setLayout(threshold_layout)
        layout.addWidget(threshold_group)

        # 哈希方法
        method_group = QGroupBox("哈希算法")
        method_layout = QVBoxLayout()
        self.method_group = QButtonGroup()

        methods = [
            ('perceptual_hash', '感知哈希（推荐，对图片变换鲁棒）'),
            ('average_hash', '平均哈希（快速，适合完全相同的图片）'),
            ('difference_hash', '差异哈希（快速，适合检测轻微变化）'),
            ('wavelet_hash', '小波哈希（精确，适合细节丰富的图片）'),
        ]

        for i, (value, text) in enumerate(methods):
            radio = QRadioButton(text)
            self.method_group.addButton(radio, i)
            radio.setProperty('method_type', value)
            method_layout.addWidget(radio)
            if i == 0:  # Default to perceptual hash
                radio.setChecked(True)

        method_group.setLayout(method_layout)
        layout.addWidget(method_group)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validate_and_accept(self):
        """验证并接受"""
        if not self.check_images.isChecked() and not self.check_videos.isChecked():
            QMessageBox.warning(self, "警告", "请至少选择一种文件类型")
            return

        self.accept()

    def get_settings(self) -> dict:
        """获取设置"""
        checked = self.method_group.checkedButton()
        method_type = checked.property('method_type') if checked else 'perceptual_hash'

        return {
            'check_images': self.check_images.isChecked(),
            'check_videos': self.check_videos.isChecked(),
            'threshold': self.threshold_spinbox.value(),
            'method': method_type
        }


class ThemeManager:
    """主题管理器"""

    # 浅色主题样式
    LIGHT_THEME = """
    QWidget {
        background-color: #f5f5f5;
        color: #000000;
    }
    QGroupBox {
        font-weight: bold;
        border: 1px solid #cccccc;
        border-radius: 5px;
        margin-top: 10px;
        padding-top: 10px;
        background-color: #ffffff;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
    }
    QPushButton {
        background-color: #e0e0e0;
        border: 1px solid #aaaaaa;
        border-radius: 4px;
        padding: 6px 12px;
        min-width: 80px;
    }
    QPushButton:hover {
        background-color: #d0d0d0;
    }
    QPushButton:pressed {
        background-color: #c0c0c0;
    }
    QPushButton:disabled {
        background-color: #f0f0f0;
        color: #808080;
    }
    QLineEdit {
        background-color: #ffffff;
        border: 1px solid #cccccc;
        border-radius: 4px;
        padding: 4px;
    }
    QListWidget {
        background-color: #ffffff;
        border: 1px solid #cccccc;
        border-radius: 4px;
    }
    QTreeWidget {
        background-color: #ffffff;
        border: 1px solid #cccccc;
        border-radius: 4px;
        alternate-background-color: #f9f9f9;
    }
    QTreeWidget::item {
        padding: 3px;
    }
    QTreeWidget::item:hover {
        background-color: #e8f4ff;
    }
    QTreeWidget::item:selected {
        background-color: #0078d7;
        color: white;
    }
    QProgressBar {
        background-color: #e0e0e0;
        border: 1px solid #cccccc;
        border-radius: 4px;
        text-align: center;
    }
    QProgressBar::chunk {
        background-color: #0078d7;
        border-radius: 3px;
    }
    QCheckBox {
        spacing: 5px;
    }
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border: 1px solid #aaaaaa;
        border-radius: 3px;
        background-color: #ffffff;
    }
    QCheckBox::indicator:checked {
        background-color: #0078d7;
        border-color: #0078d7;
        image: url(:/icons/check.png);
    }
    QRadioButton {
        spacing: 5px;
    }
    QRadioButton::indicator {
        width: 18px;
        height: 18px;
        border: 1px solid #aaaaaa;
        border-radius: 9px;
        background-color: #ffffff;
    }
    QRadioButton::indicator:checked {
        background-color: #0078d7;
        border-color: #0078d7;
    }
    QScrollBar:vertical {
        background-color: #f0f0f0;
        width: 12px;
        border-radius: 6px;
    }
    QScrollBar::handle:vertical {
        background-color: #c0c0c0;
        border-radius: 6px;
        min-height: 20px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: #a0a0a0;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QMenuBar {
        background-color: #f5f5f5;
        border-bottom: 1px solid #cccccc;
    }
    QMenuBar::item {
        padding: 5px 10px;
        background-color: transparent;
    }
    QMenuBar::item:selected {
        background-color: #e0e0e0;
    }
    QMenu {
        background-color: #ffffff;
        border: 1px solid #cccccc;
    }
    QMenu::item {
        padding: 5px 20px;
    }
    QMenu::item:selected {
        background-color: #0078d7;
        color: white;
    }
    """

    # 深色主题样式
    DARK_THEME = """
    QWidget {
        background-color: #1e1e1e;
        color: #e0e0e0;
    }
    QGroupBox {
        font-weight: bold;
        border: 1px solid #3a3a3a;
        border-radius: 5px;
        margin-top: 10px;
        padding-top: 10px;
        background-color: #252525;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
    }
    QPushButton {
        background-color: #3a3a3a;
        border: 1px solid #4a4a4a;
        border-radius: 4px;
        padding: 6px 12px;
        min-width: 80px;
    }
    QPushButton:hover {
        background-color: #4a4a4a;
    }
    QPushButton:pressed {
        background-color: #5a5a5a;
    }
    QPushButton:disabled {
        background-color: #2a2a2a;
        color: #606060;
    }
    QLineEdit {
        background-color: #2a2a2a;
        border: 1px solid #4a4a4a;
        border-radius: 4px;
        padding: 4px;
        color: #e0e0e0;
    }
    QListWidget {
        background-color: #2a2a2a;
        border: 1px solid #3a3a3a;
        border-radius: 4px;
    }
    QTreeWidget {
        background-color: #2a2a2a;
        border: 1px solid #3a3a3a;
        border-radius: 4px;
        alternate-background-color: #2d2d2d;
    }
    QTreeWidget::item {
        padding: 3px;
    }
    QTreeWidget::item:hover {
        background-color: #3a3a3a;
    }
    QTreeWidget::item:selected {
        background-color: #0078d7;
        color: white;
    }
    QProgressBar {
        background-color: #2a2a2a;
        border: 1px solid #3a3a3a;
        border-radius: 4px;
        text-align: center;
    }
    QProgressBar::chunk {
        background-color: #0078d7;
        border-radius: 3px;
    }
    QCheckBox {
        spacing: 5px;
    }
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border: 1px solid #4a4a4a;
        border-radius: 3px;
        background-color: #2a2a2a;
    }
    QCheckBox::indicator:checked {
        background-color: #0078d7;
        border-color: #0078d7;
    }
    QRadioButton {
        spacing: 5px;
    }
    QRadioButton::indicator {
        width: 18px;
        height: 18px;
        border: 1px solid #4a4a4a;
        border-radius: 9px;
        background-color: #2a2a2a;
    }
    QRadioButton::indicator:checked {
        background-color: #0078d7;
        border-color: #0078d7;
    }
    QScrollBar:vertical {
        background-color: #2a2a2a;
        width: 12px;
        border-radius: 6px;
    }
    QScrollBar::handle:vertical {
        background-color: #4a4a4a;
        border-radius: 6px;
        min-height: 20px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: #5a5a5a;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QMenuBar {
        background-color: #1e1e1e;
        border-bottom: 1px solid #3a3a3a;
    }
    QMenuBar::item {
        padding: 5px 10px;
        background-color: transparent;
    }
    QMenuBar::item:selected {
        background-color: #2a2a2a;
    }
    QMenu {
        background-color: #252525;
        border: 1px solid #3a3a3a;
    }
    QMenu::item {
        padding: 5px 20px;
    }
    QMenu::item:selected {
        background-color: #0078d7;
        color: white;
    }
    """

    @staticmethod
    def get_light_theme() -> str:
        return ThemeManager.LIGHT_THEME

    @staticmethod
    def get_dark_theme() -> str:
        return ThemeManager.DARK_THEME


def main():
    app = QApplication(sys.argv)
    window = DuplicateFileFinderGUI()
    window.show()
    sys.exit(app.exec())
