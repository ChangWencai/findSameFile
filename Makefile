.PHONY: help install build build-gui build-cli clean release test

# 默认目标
help:
	@echo "可用命令:"
	@echo "  make install      - 安装依赖"
	@echo "  make build        - 交互式编译（选择 GUI/CLI）"
	@echo "  make build-gui    - 编译 GUI 版本"
	@echo "  make build-cli    - 编译 CLI 版本"
	@echo "  make release      - 编译并打包发布版本"
	@echo "  make clean        - 清理构建文件"
	@echo "  make test         - 运行测试"
	@echo ""
	@echo "示例:"
	@echo "  make install build-gui"
	@echo "  make clean release"

# 安装依赖
install:
	@echo "安装依赖..."
	pip3 install -r requirements.txt

# 交互式编译
build:
	@python3 build.py

# 编译 GUI 版本
build-gui:
	@python3 build.py --gui --no-input

# 编译 CLI 版本
build-cli:
	@python3 build.py --cli --no-input

# 编译发布版本
release: clean
	@python3 build.py --gui --no-input

# 清理构建文件
clean:
	@echo "清理构建文件..."
	@rm -rf build dist *.spec release
	@rm -rf __pycache__ */__pycache__
	@find . -name "*.pyc" -delete
	@find . -name "*.pyo" -delete
	@echo "清理完成"

# 运行测试
test:
	@python3 test_features.py

# 安装 PyInstaller
install-pyinstaller:
	@pip3 install pyinstaller>=6.0.0
