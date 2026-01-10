#!/usr/bin/env python3
"""
多平台编译脚本

将重复文件查找器打包为可执行文件，支持 Linux、macOS 和 Windows。
"""
import os
import sys
import platform
import subprocess
import shutil
from pathlib import Path


# 配置
APP_NAME = "findSameVideo"
VERSION = "0.6.0"
AUTHOR = "Your Name"
DESCRIPTION = "重复文件查找器"

# PyInstaller 配置
PYINSTALLER_VERSION = ">=6.0.0"


def setup_ci_environment():
    """为 CI 环境设置必要的环境变量"""
    # 检测是否在 CI 环境中
    is_ci = os.environ.get('CI', '').lower() == 'true'

    if is_ci and platform.system() == 'Linux':
        # 在 Linux CI 环境中，使用 offscreen 平台避免需要 X11 显示服务器
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        print("[OK] CI 环境检测: 设置 QT_QPA_PLATFORM=offscreen")

    return is_ci


def is_ci_environment():
    """检测是否运行在 CI 环境中"""
    return os.environ.get('CI', '').lower() == 'true'


def get_platform():
    """获取当前平台"""
    system = platform.system()
    machine = platform.machine()

    if system == "Darwin":
        return "macos"
    elif system == "Linux":
        return "linux"
    elif system == "Windows":
        return "windows"
    else:
        raise OSError(f"不支持的平台: {system}")


def check_pyinstaller():
    """检查 PyInstaller 是否已安装"""
    try:
        import PyInstaller
        print(f"[OK] PyInstaller 已安装: {PyInstaller.__version__}")
        return True
    except ImportError:
        print("[FAIL] PyInstaller 未安装")
        return False


def install_pyinstaller():
    """安装 PyInstaller"""
    print("正在安装 PyInstaller...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller" + PYINSTALLER_VERSION],
            check=True,
            capture_output=True,
            text=True
        )
        print("[OK] PyInstaller 安装成功")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[FAIL] PyInstaller 安装失败: {e}")
        if e.stderr:
            print(f"错误输出: {e.stderr}")
        return False


def create_spec_file():
    """创建 PyInstaller spec 文件"""
    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('CLAUDE.md', '.'),
        ('README.md', '.'),
        ('ROADMAP.md', '.'),
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PIL._imaging',
        'send2trash',
        'imagehash',
        'cv2',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        'Tkinter',
        'matplotlib',
        'pandas',
        'numpy.tests',
        'scipy.tests',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='{APP_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI 模式，不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 图标文件路径
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='{APP_NAME}',
)
'''

    # 写入 spec 文件
    with open(f'{APP_NAME}.spec', 'w', encoding='utf-8') as f:
        f.write(spec_content)

    print(f"[OK] 创建 spec 文件: {APP_NAME}.spec")


def build_executable(platform_name):
    """编译可执行文件"""
    print(f"\n{'='*50}")
    print(f"开始编译 {platform_name} 版本...")
    print(f"{'='*50}\n")

    # 清理旧的构建文件
    build_dirs = ['build', 'dist', f'{APP_NAME}.spec']
    for dir_name in build_dirs:
        if os.path.exists(dir_name):
            if os.path.isdir(dir_name):
                shutil.rmtree(dir_name)
            else:
                os.remove(dir_name)

    # 创建 spec 文件
    create_spec_file()

    # PyInstaller 命令（使用 spec 文件时不允许额外的命令行选项）
    # 所有配置已在 spec 文件中定义
    cmd = [
        'pyinstaller',
        '--clean',
        f'{APP_NAME}.spec',
        '--noconfirm',
    ]

    # 执行编译
    print("执行命令:")
    print(" ".join(cmd))
    print()

    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print(f"\n[OK] {platform_name} 版本编译成功!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[FAIL] {platform_name} 版本编译失败: {e}")
        return False


def package_executable(platform_name):
    """打包可执行文件"""
    print(f"\n{'='*50}")
    print(f"打包 {platform_name} 版本...")
    print(f"{'='*50}\n")

    dist_dir = Path('dist')
    output_dir = Path('release')
    output_dir.mkdir(exist_ok=True)

    if platform_name == "macos":
        # macOS: 创建 .app 包
        app_path = dist_dir / f'{APP_NAME}.app'
        if app_path.exists():
            output_file = output_dir / f'{APP_NAME}-{VERSION}-macos.app'
            shutil.copytree(app_path, output_file)
            print(f"[OK] macOS 应用包: {output_file}")

            # 创建压缩包
            zip_cmd = ['zip', '-r', '-y', str(output_file.with_suffix('.zip')), str(output_file.name)]
            subprocess.run(zip_cmd, check=True)
            print(f"[OK] macOS 压缩包: {output_file.with_suffix('.zip')}")
            return True

    elif platform_name == "windows":
        # Windows: 可执行文件
        exe_path = dist_dir / f'{APP_NAME}/{APP_NAME}.exe'
        if exe_path.exists():
            output_file = output_dir / f'{APP_NAME}-{VERSION}-windows.exe'
            shutil.copy(exe_path, output_file)
            print(f"[OK] Windows 可执行文件: {output_file}")
            return True

    else:  # linux
        # Linux: 可执行文件
        exe_path = dist_dir / f'{APP_NAME}/{APP_NAME}'
        if exe_path.exists():
            # 设置可执行权限
            os.chmod(exe_path, 0o755)

            # 创建 tar.gz 压缩包
            import tarfile
            output_file = output_dir / f'{APP_NAME}-{VERSION}-linux.tar.gz'
            with tarfile.open(output_file, 'w:gz') as tar:
                tar.add(exe_path, arcname=APP_NAME)
            print(f"[OK] Linux 压缩包: {output_file}")
            return True

    print(f"[FAIL] 未找到编译输出文件")
    return False


def create_cli_spec():
    """创建 CLI 版本的 spec 文件"""
    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-
# CLI 版本 - 显示控制台窗口

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('CLAUDE.md', '.'),
        ('README.md', '.'),
        ('ROADMAP.md', '.'),
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PIL._imaging',
        'send2trash',
        'imagehash',
        'cv2',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        'Tkinter',
        'matplotlib',
        'pandas',
        'numpy.tests',
        'scipy.tests',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='{APP_NAME}-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # CLI 模式，显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='{APP_NAME}-cli',
)
'''

    # 写入 CLI spec 文件
    with open(f'{APP_NAME}-cli.spec', 'w', encoding='utf-8') as f:
        f.write(spec_content)

    print(f"[OK] 创建 CLI spec 文件: {APP_NAME}-cli.spec")


def build_all():
    """编译所有平台版本"""
    print(f"\n{'='*60}")
    print(f"{APP_NAME} 多平台编译脚本")
    print(f"版本: {VERSION}")
    print(f"{'='*60}\n")

    # 检查 PyInstaller
    if not check_pyinstaller():
        if not install_pyinstaller():
            print("\n请手动安装 PyInstaller:")
            print("pip install pyinstaller")
            return 1

    # 获取当前平台
    current_platform = get_platform()
    print(f"当前平台: {current_platform}\n")

    # 询问编译模式
    print("请选择编译模式:")
    print("1. GUI 版本（默认）")
    print("2. CLI 版本")
    print("3. 同时编译 GUI 和 CLI 版本")

    choice = input("\n请输入选项 (1-3): ").strip() or "1"

    success = False

    if choice == "1":
        success = build_executable(current_platform)
        if success:
            package_executable(current_platform)

    elif choice == "2":
        # 创建 CLI spec 文件
        create_cli_spec()

        # 编译 CLI 版本
        cmd = [
            'pyinstaller',
            '--clean',
            f'{APP_NAME}-cli.spec',
            '--noconfirm',
        ]

        print("执行命令:")
        print(" ".join(cmd))

        try:
            subprocess.run(cmd, check=True)
            print(f"\n[OK] CLI 版本编译成功!")

            # 打包
            dist_dir = Path('dist')
            output_dir = Path('release')
            output_dir.mkdir(exist_ok=True)

            exe_name = APP_NAME if current_platform != "windows" else f'{APP_NAME}-cli.exe'
            exe_path = dist_dir / f'{APP_NAME}-cli' / exe_name

            if exe_path.exists():
                if current_platform == "windows":
                    output_file = output_dir / f'{APP_NAME}-cli-{VERSION}-{current_platform}.exe'
                    shutil.copy(exe_path, output_file)
                else:
                    os.chmod(exe_path, 0o755)
                    import tarfile
                    output_file = output_dir / f'{APP_NAME}-cli-{VERSION}-{current_platform}.tar.gz'
                    with tarfile.open(output_file, 'w:gz') as tar:
                        tar.add(exe_path, arcname=f'{APP_NAME}-cli')

                print(f"[OK] 输出文件: {output_file}")
                success = True

        except subprocess.CalledProcessError as e:
            print(f"\n[FAIL] 编译失败: {e}")

    elif choice == "3":
        # 编译 GUI 版本
        gui_success = build_executable(current_platform)
        if gui_success:
            package_executable(current_platform)

        # 编译 CLI 版本
        create_cli_spec()

        cmd = [
            'pyinstaller',
            '--clean',
            f'{APP_NAME}-cli.spec',
            '--noconfirm',
        ]

        try:
            subprocess.run(cmd, check=True)
            print(f"\n[OK] CLI 版本编译成功!")
        except subprocess.CalledProcessError as e:
            print(f"\n[FAIL] CLI 版本编译失败: {e}")

        success = gui_success

    else:
        print("无效的选项")
        return 1

    # 显示结果
    print(f"\n{'='*60}")
    if success:
        print("[OK] 编译完成!")
        print(f"\n输出目录: {Path('release').absolute()}")
        print(f"\n文件列表:")
        release_dir = Path('release')
        if release_dir.exists():
            for file in release_dir.iterdir():
                size = file.stat().st_size / (1024 * 1024)  # MB
                print(f"  - {file.name} ({size:.1f} MB)")
    else:
        print("[FAIL] 编译失败")
    print(f"{'='*60}\n")

    return 0 if success else 1


def main():
    """主函数"""
    import argparse

    # 设置 CI 环境变量（必须在最前面）
    setup_ci_environment()

    parser = argparse.ArgumentParser(description='多平台编译脚本')
    parser.add_argument('--all', action='store_true', help='编译所有版本')
    parser.add_argument('--gui', action='store_true', help='仅编译 GUI 版本')
    parser.add_argument('--cli', action='store_true', help='仅编译 CLI 版本')
    parser.add_argument('--no-input', action='store_true', help='非交互模式')

    args = parser.parse_args()

    if args.no_input:
        # 非交互模式，默认编译 GUI 版本
        current_platform = get_platform()

        if not check_pyinstaller():
            if not install_pyinstaller():
                return 1

        success = build_executable(current_platform)
        if success:
            package_executable(current_platform)

        return 0 if success else 1

    # 交互模式
    return build_all()


if __name__ == "__main__":
    sys.exit(main())
