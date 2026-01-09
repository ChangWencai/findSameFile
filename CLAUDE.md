# CLAUDE.md

此文件为 Claude Code (claude.ai/code) 在此代码库中工作时提供指导。

## 项目概述

这是一个基于 Python 的重复文件查找器应用，带有 PyQt6 图形界面。它使用 SHA256 哈希扫描目录以查找重复文件，并允许用户选择性删除重复文件。

## 开发命令

### 运行应用
```bash
python3 main.py
```

### 安装依赖
```bash
pip3 install -r requirements.txt
```

## 代码架构

应用程序采用模块化架构，职责分离清晰：

### 核心模块

- **main.py** - 启动 GUI 应用程序的入口点

- **file_scanner.py** - 核心文件扫描和哈希逻辑
  - `FileScanner` - 递归扫描目录，按扩展名过滤，跳过问题文件（如 .app 捆绑包、系统文件）
  - `HashCalculator` - 使用分块读取（32KB 块）计算 SHA256 哈希，提高内存效率
  - `FileInfo` dataclass - 存储文件元数据（路径、大小、修改时间）

- **duplicate_finder.py** - 重复检测编排
  - `DuplicateFinder` - 协调多阶段重复查找过程：
    1. 扫描目录中的所有文件
    2. 按大小分组（快速预过滤）
    3. 对相同大小的文件计算 SHA256 哈希
    4. 返回实际的重复文件组
  - `DuplicateGroup` dataclass - 表示共享同一哈希的一组重复文件

- **gui.py** - 基于 PyQt6 的 GUI 应用
  - `DuplicateFileFinderGUI` - 主窗口，包含路径选择、文件类型过滤、结果树
  - `ScanThread` - 在后台运行重复查找的 QThread，保持 UI 响应

### 关键设计决策

1. **多阶段过滤** - 在哈希之前先按大小分组，避免不必要的哈希计算（快速拒绝）

2. **线程执行** - 扫描操作在单独的 QThread 中运行，防止 UI 冻结，支持进度回调和取消

3. **分块文件读取** - HashCalculator 使用 32KB 块处理大文件时提高内存效率

4. **文件类型过滤** - 通过 FileScanner 的 `extensions` 参数支持按扩展名过滤（例如仅视频文件）

5. **平台特定文件操作** - "打开文件所在位置" 功能在不同平台使用不同命令：macOS (`open -R`)、Windows (`explorer`)、Linux (`xdg-open`)

### 跳过的文件

扫描器会自动跳过：
- macOS 特殊文件：.app、.bundle、.pkg、.dmg、.iso 扩展名
- 系统元数据：.DS_Store、Thumbs.db、.Spotlight-V100、.Trashes
- 以 "._" 开头的文件（资源分支）
- 零大小文件
