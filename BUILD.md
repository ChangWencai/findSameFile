# 编译指南

本文档详细说明如何将重复文件查找器编译为独立可执行文件。

## 目录

- [环境准备](#环境准备)
- [本地编译](#本地编译)
- [Docker 编译](#docker-编译)
- [CI/CD 自动编译](#cicd-自动编译)
- [常见问题](#常见问题)

## 环境准备

### 系统要求

| 平台 | 要求 |
|------|------|
| Linux | Python 3.8+, GCC |
| macOS | Python 3.8+, Xcode Command Line Tools |
| Windows | Python 3.8+, Microsoft Visual C++ 14.0 |

### 安装依赖

```bash
# 克隆仓库
git clone https://github.com/yourusername/findSameVideo.git
cd findSameVideo

# 安装所有依赖（包括编译工具）
pip install -r requirements.txt
```

## 本地编译

### 方式 1: Python 脚本

```bash
# 查看帮助
python3 build.py --help

# 编译 GUI 版本
python3 build.py --gui

# 编译 CLI 版本
python3 build.py --cli

# 编译所有版本
python3 build.py --all
```

### 方式 2: Shell 脚本

```bash
# 查看帮助
./build.sh help

# 编译 GUI 版本
./build.sh gui

# 编译 CLI 版本
./build.sh cli

# 编译所有版本
./build.sh all
```

### 方式 3: Makefile

```bash
# 查看帮助
make help

# 编译 GUI 版本
make build-gui

# 编译 CLI 版本
make build-cli

# 编译并打包
make release
```

## 编译输出

编译完成后，可执行文件位于 `release/` 目录：

### macOS

支持 Intel 和 Apple Silicon 两种架构：

```bash
release/
├── findSameVideo-0.6.0-macos-intel.app/  # Intel x86_64 架构 (macOS 13+)
├── findSameVideo-0.6.0-macos-intel.zip   # Intel 版压缩包
├── findSameVideo-0.6.0-macos-arm.app/    # Apple Silicon ARM64 (M1/M2/M3)
└── findSameVideo-0.6.0-macos-arm.zip     # ARM 版压缩包
```

**选择指南：**
- Intel Mac（2019 年及之前）：下载 `macos-intel` 版本
- Apple Silicon Mac（M1/M2/M3）：下载 `macos-arm` 版本
- 不确定：下载 `macos-arm` 版本（通过 Rosetta 2 也能运行 x86 应用）

### Linux

```bash
release/
└── findSameVideo-0.6.0-linux.tar.gz    # 压缩的可执行文件
```

### Windows

```bash
release/
└── findSameVideo-0.6.0-windows.exe     # 可执行文件
```

## Docker 编译

### 使用 Dockerfile

```bash
# 构建镜像
docker build -t findsamevideo-builder .

# 编译并输出到本地
docker run --rm -v $(pwd)/release:/output findsamevideo-builder
```

### 使用 Docker Compose

```bash
# 创建 docker-compose.yml
docker-compose up
```

## CI/CD 自动编译

### GitHub Actions

项目已配置 GitHub Actions 工作流（`.github/workflows/build.yml`）：

**触发条件：**
- 推送 tag（如 `v1.0.0`）
- 手动触发

**自动编译平台：**
- Ubuntu (Linux x86_64)
- macOS 13 (Intel x86_64)
- macOS 14 (Apple Silicon ARM64)
- Windows (x86_64)

**输出：**
- 自动上传构建产物到 GitHub Actions Artifacts
- 自动创建 GitHub Release（tag 触发时）
- 支持 Intel Mac 和 Apple Silicon Mac 原生运行

### 手动触发工作流

1. 进入 GitHub 仓库页面
2. 点击 "Actions" 标签
3. 选择 "Build Multi-Platform Executables"
4. 点击 "Run workflow" 按钮
5. 选择分支并运行

## 自定义编译

### 修改应用图标

1. 准备图标文件：
   - macOS: `.icns` 格式
   - Windows: `.ico` 格式
   - Linux: `.png` 格式

2. 修改 `build.py` 中的 `icon` 参数

### 修改应用信息

编辑 `build.py` 中的配置：

```python
APP_NAME = "findSameVideo"
VERSION = "0.6.0"
AUTHOR = "Your Name"
DESCRIPTION = "重复文件查找器"
```

### 添加额外文件

修改 spec 文件的 `datas` 参数：

```python
datas=[
    ('CLAUDE.md', '.'),
    ('README.md', '.'),
    ('ROADMAP.md', '.'),
    ('config.json', '.'),  # 添加额外文件
],
```

## 常见问题

### 1. macOS: "未签名的应用"警告

**问题：** 打开应用时提示无法验证开发者

**解决方案：**

```bash
# 移除隔离属性
xattr -cr findSameVideo-0.6.0-macos.app

# 右键点击应用 -> 打开 -> 仍要打开
```

**代码签名（可选）：**

```bash
# 安装开发者证书后
codesign --deep --force --verify --verbose \
  --sign "Developer ID Application: Your Name" \
  findSameVideo-0.6.0-macos.app
```

### 2. Linux: 缺少 Qt 依赖

**问题：** 运行时提示缺少 libQt6

**解决方案：**

```bash
# Ubuntu/Debian
sudo apt-get install \
  libxcb-cursor0 \
  libxcb-xinerama0 \
  libxkbcommon-x11-0 \
  libgl1-mesa-glx
```

### 3. Windows: 杀毒软件误报

**问题：** 杀毒软件可能误报

**解决方案：**

1. 使用 PyInstaller 的 `--noupx` 选项禁用 UPX 压缩
2. 向杀毒软件厂商提交白名单申请

### 4. 编译后文件过大

**问题：** 可执行文件过大（>100MB）

**解决方案：**

1. 使用虚拟环境：
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   python build.py --gui
   ```

2. 排除不需要的模块：
   编辑 spec 文件的 `excludes` 参数

3. 使用 UPX 压缩：
   ```bash
   # 下载 UPX
   wget https://github.com/upx/upx/releases/download/v4.0.2/upx-4.0.2-amd64_linux.tar.xz
   tar -xf upx-4.0.2-amd64_linux.tar.xz

   # 使用 UPX 压缩
   upx --best --lzma findSameVideo
   ```

### 5. 缺少隐藏导入

**问题：** 运行时提示缺少模块

**解决方案：**

在 `build.py` 中添加到 `hiddenimports`：

```python
hiddenimports=[
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    '你的模块名',
],
```

## 性能优化

### 减小文件大小

| 方法 | 效果 |
|------|------|
| 使用虚拟环境 | 减少 30-50% |
| 排除不需要的模块 | 减少 10-20% |
| UPX 压缩 | 减少 30-50% |
| 单文件模式 | 不推荐（启动慢） |

### 加快启动速度

```python
# 在 spec 文件中设置
exclude_binaries=False  # 使用目录模式而非单文件
```

## 发布检查清单

- [ ] 在所有平台测试可执行文件
- [ ] 验证所有功能正常工作
- [ ] 检查文件大小是否合理
- [ ] 测试卸载/清理是否完整
- [ ] 准备发布说明
- [ ] 创建 Git Tag
- [ ] 上传到 GitHub Releases

## 参考资源

- [PyInstaller 官方文档](https://pyinstaller.org/en/stable/)
- [PyQt6 官方文档](https://www.riverbankcomputing.com/static/Docs/PyQt6/)
- [Docker 官方文档](https://docs.docker.com/)
- [GitHub Actions 文档](https://docs.github.com/en/actions)
