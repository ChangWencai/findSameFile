#!/bin/bash
# 多平台编译脚本

set -e

APP_NAME="findSameVideo"
VERSION="0.6.0"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 获取当前平台
get_platform() {
    case "$(uname -s)" in
        Darwin)
            echo "macos"
            ;;
        Linux)
            echo "linux"
            ;;
        MINGW*|MSYS*|CYGWIN*)
            echo "windows"
            ;;
        *)
            print_error "不支持的平台: $(uname -s)"
            exit 1
            ;;
    esac
}

# 检查依赖
check_dependencies() {
    print_info "检查依赖..."

    # 检查 Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 未安装"
        exit 1
    fi
    print_info "Python 版本: $(python3 --version)"

    # 检查 pip
    if ! command -v pip3 &> /dev/null; then
        print_error "pip3 未安装"
        exit 1
    fi

    # 检查 PyInstaller
    if ! python3 -c "import PyInstaller" 2>/dev/null; then
        print_warn "PyInstaller 未安装，正在安装..."
        pip3 install pyinstaller
    fi

    print_info "所有依赖检查完成"
}

# 清理旧的构建文件
clean_build() {
    print_info "清理旧的构建文件..."
    rm -rf build dist *.spec release
    print_info "清理完成"
}

# 编译可执行文件
build_executable() {
    local build_type=$1  # gui or cli
    local platform=$(get_platform)

    print_info "开始编译 ${build_type} 版本 (${platform})..."

    # 创建 spec 文件
    python3 build.py --${build_type} --no-input

    # 检查编译结果
    if [ "${build_type}" = "gui" ]; then
        dist_dir="dist/${APP_NAME}"
    else
        dist_dir="dist/${APP_NAME}-cli"
    fi

    if [ -d "${dist_dir}" ]; then
        print_info "编译成功!"

        # 创建 release 目录
        mkdir -p release

        # 打包
        case "${platform}" in
            macos)
                if [ "${build_type}" = "gui" ]; then
                    # macOS .app 包
                    if [ -d "dist/${APP_NAME}.app" ]; then
                        cp -r "dist/${APP_NAME}.app" "release/${APP_NAME}-${VERSION}-macos.app"
                        cd release
                        zip -r -y "${APP_NAME}-${VERSION}-macos.zip" "${APP_NAME}-${VERSION}-macos.app"
                        cd ..
                        print_info "创建: release/${APP_NAME}-${VERSION}-macos.app"
                        print_info "创建: release/${APP_NAME}-${VERSION}-macos.zip"
                    fi
                fi
                ;;
            linux)
                # Linux 可执行文件
                exe_name="${APP_NAME}"
                if [ "${build_type}" = "cli" ]; then
                    exe_name="${APP_NAME}-cli"
                fi

                if [ -f "${dist_dir}/${exe_name}" ]; then
                    chmod +x "${dist_dir}/${exe_name}"
                    tar -czf "release/${APP_NAME}-${VERSION}-linux-${build_type}.tar.gz" -C "${dist_dir}" "${exe_name}"
                    print_info "创建: release/${APP_NAME}-${VERSION}-linux-${build_type}.tar.gz"
                fi
                ;;
        esac

        return 0
    else
        print_error "编译失败，未找到输出目录"
        return 1
    fi
}

# 显示帮助
show_help() {
    cat << EOF
多平台编译脚本

用法: ./build.sh [选项]

选项:
    install     安装依赖
    clean       清理构建文件
    gui         编译 GUI 版本
    cli         编译 CLI 版本
    all         编译 GUI 和 CLI 版本
    release     编译并打包发布版本
    test        运行测试
    help        显示此帮助信息

示例:
    ./build.sh install      # 安装依赖
    ./build.sh gui          # 编译 GUI 版本
    ./build.sh cli          # 编译 CLI 版本
    ./build.sh all          # 编译所有版本
    ./build.sh release      # 编译发布版本

使用 Makefile:
    make install            # 安装依赖
    make build-gui          # 编译 GUI 版本
    make build-cli          # 编译 CLI 版本
    make release            # 编译发布版本
    make clean              # 清理构建文件
    make test               # 运行测试
EOF
}

# 主函数
main() {
    local command=${1:-help}

    case "${command}" in
        install)
            check_dependencies
            pip3 install -r requirements.txt
            ;;
        clean)
            clean_build
            ;;
        gui)
            check_dependencies
            build_executable gui
            ;;
        cli)
            check_dependencies
            build_executable cli
            ;;
        all)
            check_dependencies
            build_executable gui
            build_executable cli
            ;;
        release)
            check_dependencies
            clean_build
            build_executable gui

            # 显示发布文件
            echo ""
            print_info "发布文件:"
            ls -lh release/ 2>/dev/null || echo "  (无文件)"
            ;;
        test)
            print_info "运行测试..."
            python3 test_features.py
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "未知命令: ${command}"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"
