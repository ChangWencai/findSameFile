# 重复文件查找器

一个功能强大的重复文件查找工具，支持 GUI 和 CLI 双模式运行。使用 SHA-256 哈希算法精确识别重复文件，提供智能选择、安全删除、相似文件检测等高级功能。

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## 功能特性

### 核心功能
- **精确重复检测** - 使用 SHA-256 哈希算法精确识别重复文件
- **多格式支持** - 支持图片、视频、音频、文档等各种文件类型
- **智能选择** - 多种策略自动选择要删除的重复文件
- **安全删除** - 移动到回收站而非永久删除，支持撤销

### 性能优化
- **并行哈希计算** - 支持多线程/多进程并行，利用多核 CPU 加速哈希计算
- **进程池支持** - 可选使用进程池突破 GIL 限制，性能提升 2-3 倍
- **批量缓存查询** - SQLite 批量查询优化，缓存性能提升 10 倍+
- **多阶段哈希策略** - 先部分哈希筛选，再完整哈希确认
- **智能缓存机制** - SQLite 缓存哈希结果，大幅提升重复扫描速度

### 高级功能
- **自定义文件类型** - 支持手动输入文件扩展名，灵活过滤文件类型
- **相似文件检测** - 检测近似相似的图片和视频（基于感知哈希）
- **文件预览** - 图片缩略图预览和文件元信息显示
- **批量操作** - 全选、反选、按目录/大小选择
- **导出报告** - 支持 CSV、JSON、HTML 格式

### 用户体验
- **深色模式** - 完整的主题切换支持
- **拖拽支持** - 拖拽文件夹即可开始扫描
- **搜索过滤** - 实时搜索和过滤结果
- **预计剩余时间** - 实时显示扫描进度和预计完成时间

## 截图

### 主界面
- 直观的图形界面
- 实时进度显示
- 详细的文件信息展示

### 智能选择
- 保留路径最短的文件
- 保留最新/最旧的文件
- 保留最大/最小的文件
- 按路径模式选择

### 相似文件检测
- 图片相似度检测
- 视频关键帧相似度检测
- 可配置相似度阈值
- 彩色编码结果显示

## 安装

### 环境要求

- Python 3.8 或更高版本
- macOS / Linux / Windows

### 安装步骤

1. 克隆仓库
```bash
git clone https://github.com/yourusername/findSameVideo.git
cd findSameVideo
```

2. 安装依赖

**基础依赖（必需）**
```bash
pip install -r requirements.txt
```

**可选依赖**
```bash
# 安全删除（移至回收站）
pip install send2trash==1.8.2

# 相似文件检测（图片和视频）
pip install Pillow==10.4.0
pip install imagehash==4.3.1
pip install opencv-python==4.9.0.80
```

或一键安装所有依赖：
```bash
pip install PyQt6==6.7.0 send2trash==1.8.2 Pillow==10.4.0 imagehash==4.3.1 opencv-python==4.9.0.80
```

## 使用方法

### GUI 模式

直接运行程序启动图形界面：
```bash
python main.py
```

#### 基本操作流程

1. **选择目录** - 点击"浏览..."按钮或直接拖拽文件夹到窗口
2. **选择文件类型** - 勾选要扫描的文件类型
3. **开始扫描** - 点击"开始扫描"按钮
4. **查看结果** - 扫描完成后在右侧列表查看重复文件
5. **选择要删除的文件** - 勾选要删除的文件，或使用智能选择功能
6. **删除文件** - 点击"删除选中文件"按钮

#### 高级功能

**智能选择策略**
- 点击"智能选择..."按钮
- 选择自动选择策略（如保留路径最短的文件）
- 预览将要删除的文件数量和空间

**批量操作**
- 全选/不选/反选
- 按目录选择或取消选择
- 按文件大小范围选择

**相似文件检测**
- 点击"查找相似文件..."按钮
- 选择文件类型（图片/视频）
- 设置相似度阈值（默认 80%）
- 查看相似文件组及相似度百分比

**导出报告**
- 点击"导出报告..."按钮
- 选择导出格式（HTML/CSV/JSON）
- 选择是否包含完整元数据
- 设置输出路径

### CLI 模式

#### 扫描目录
```bash
# 基本扫描
python main.py scan ~/Pictures

# 详细输出
python main.py scan ~/Documents -v

# 只扫描特定文件类型
python main.py scan ~/Downloads -e jpg,png,mp4

# 禁用并行计算
python main.py scan ~/Music --no-parallel
```

#### 导出报告
```bash
# 导出 HTML 报告
python main.py export ~/Pictures -f html -o report.html

# 导出 JSON 报告
python main.py export ~/Documents -f json -o report.json

# 导出 CSV 报告（不包含元数据）
python main.py export ~/Downloads -f csv --minimal
```

#### 自动删除重复文件
```bash
# 扫描并自动删除（保留每组第一个文件）
python main.py scan ~/Duplicates --delete

# 强制删除（不提示确认）
python main.py scan ~/Temp --delete --force
```

#### 帮助信息
```bash
python main.py --help
python main.py scan --help
python main.py export --help
```

## 配置文件

配置文件保存在 `~/.findSameVideo/config.json`，包含以下设置：

```json
{
  "theme": "light",
  "cache_enabled": true,
  "use_parallel": true,
  "use_multi_stage": true,
  "default_extensions": [".mp4", ".mkv", ".jpg", ".png", ...],
  "smart_select_default_strategy": "keep_shortest_path",
  "export_format": "html",
  "export_include_metadata": true,
  "remember_window_size": true,
  "window_width": 1100,
  "window_height": 700
}
```

## 数据文件

应用程序数据保存在 `~/.findSameVideo/` 目录：

```
~/.findSameVideo/
├── config.json           # 用户配置
├── deletion_history.json # 删除历史
├── hash_cache.db         # 哈希缓存
└── logs/                 # 日志目录
    ├── findSameVideo_YYYYMMDD.log
    └── errors.log
```

## 项目结构

```
findSameVideo/
├── main.py                 # 应用入口（支持 GUI/CLI）
├── gui.py                  # PyQt6 图形界面
├── file_scanner.py         # 文件扫描和哈希计算
├── duplicate_finder.py     # 重复检测核心逻辑
├── similarity_detector.py  # 相似文件检测
├── cache_manager.py        # 哈希缓存管理（批量查询优化）
├── export_manager.py       # 报告导出功能
├── config_manager.py       # 配置文件管理
├── logger.py               # 日志系统
├── exceptions.py           # 自定义异常类
├── utils.py                # 工具函数模块
├── test_features.py        # 功能测试套件
├── build.py                # 编译脚本（Python）
├── build.sh                # 编译脚本（Shell）
├── Makefile                # Make 构建文件
├── Dockerfile              # Docker 编译镜像
├── requirements.txt        # 依赖列表
├── README.md               # 项目文档
├── BUILD.md                # 编译指南
├── CLAUDE.md              # 开发指南
└── ROADMAP.md             # 需求迭代文档
```

## 常见问题

### 1. 扫描速度慢怎么办？

- 启用并行哈希计算（默认启用）
- 启用缓存机制（默认启用）
- 使用多阶段哈希策略（默认自动启用）

### 2. 如何恢复误删的文件？

文件被移动到系统回收站，可以：
- macOS: 在 Finder 中访达"废纸篓"
- Windows: 打开"回收站"
- Linux: 查看桌面回收站或 `~/.local/share/Trash/`

查看删除历史记录：
```bash
cat ~/.findSameVideo/deletion_history.json
```

### 3. 相似文件检测不准确？

- 调整相似度阈值（80% 适合大多数情况）
- 尝试不同的哈希算法
- 90%+ 只匹配非常相似的文件

### 4. 如何跳过某些目录？

- 权限不足的目录会自动跳过
- 可在日志中查看跳过的目录列表

## 编译

### 快速开始

使用提供的编译脚本快速构建可执行文件：

```bash
# 方式 1: 使用 Python 脚本
python3 build.py --gui --no-input

# 方式 2: 使用 Shell 脚本
./build.sh gui

# 方式 3: 使用 Makefile
make build-gui
```

### 编译选项

**GUI 版本（默认）**
```bash
python3 build.py --gui
./build.sh gui
make build-gui
```

**CLI 版本**
```bash
python3 build.py --cli
./build.sh cli
make build-cli
```

**同时编译 GUI 和 CLI**
```bash
python3 build.py --all
./build.sh all
```

**交互式编译**
```bash
python3 build.py
./build.sh
```

### 编译输出

编译完成后，可执行文件位于 `release/` 目录：

| 平台 | GUI 版本 | CLI 版本 |
|------|----------|----------|
| macOS | `findSameVideo-x.x.x-macos.app` | `findSameVideo-cli-x.x.x-macos.tar.gz` |
| Linux | `findSameVideo-x.x.x-linux.tar.gz` | `findSameVideo-cli-x.x.x-linux.tar.gz` |
| Windows | `findSameVideo-x.x.x-windows.exe` | `findSameVideo-cli-x.x.x-windows.exe` |

### 清理构建文件

```bash
python3 build.py --clean
./build.sh clean
make clean
```

### Docker 编译

使用 Docker 在 Linux 环境中编译：

```bash
# 构建镜像
docker build -t findsamevideo-builder .

# 编译并复制输出
docker run --rm -v $(pwd)/release:/output findsamevideo-builder
```

### CI/CD 自动编译

项目包含 GitHub Actions 工作流，支持自动编译多平台版本：

- 推送 tag 时自动触发编译
- 编译 Linux、macOS、Windows 三个平台
- 自动创建 GitHub Release

## 开发

### 运行测试

```bash
python test_features.py
```

### 代码风格

项目遵循 PEP 8 代码规范。

### 贡献

欢迎提交 Issue 和 Pull Request！

## 版本历史

### v0.7.0（当前版本）
- ✅ 代码质量和性能优化
  - 自定义异常类体系
  - 错误处理改进（移除裸except）
  - SQL注入安全修复
  - 批量缓存查询（10倍性能提升）
  - 进程池支持（2-3倍性能提升）
  - 路径安全验证
- ✅ 自定义文件类型支持
- ✅ 修复第二次扫描进度条不重置的bug

### v0.6.0
- ✅ 命令行模式（CLI）
- ✅ 相似文件检测功能
- ✅ 权限检查功能
- ✅ 文件预览功能
- ✅ 多平台编译支持

### v0.5.0
- 相似文件检测功能
- 权限检查功能
- 文件预览功能

### v0.4.0
- 预计剩余时间显示
- 拖拽支持
- 搜索和过滤功能
- 配置文件支持
- 日志系统

### v0.3.0
- 多阶段哈希策略
- 批量操作增强
- 深色模式支持

### v0.2.0
- 智能选择策略
- 安全删除（回收站）
- 并行哈希计算
- 缓存机制
- 导出功能

### v0.1.0
- 基本的文件扫描功能
- 重复文件检测
- 手动选择和删除

## 许可证

MIT License

## 致谢

- PyQt6 - 图形界面框架
- Pillow - 图片处理库
- imagehash - 图片感知哈希库
- opencv-python - 视频处理库
- send2trash - 安全删除库

## 联系方式

- GitHub Issues: [项目地址]
- Email: your@email.com

---

**享受整洁的文件系统！** 🚀
