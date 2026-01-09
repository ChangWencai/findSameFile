# 多平台编译 Dockerfile
# 用于在 Linux 环境中编译 Windows 和 Linux 可执行文件

FROM ubuntu:22.04

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHON_VERSION=3.10

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    python${PYTHON_VERSION} \
    python${PYTHON_VERSION}-pip \
    python${PYTHON_VERSION}-dev \
    wget \
    unzip \
    zip \
    && rm -rf /var/lib/apt/lists/*

# 设置 Python 命令
RUN ln -sf /usr/bin/python${PYTHON_VERSION} /usr/bin/python3 && \
    ln -sf /usr/bin/python${PYTHON_VERSION} /usr/bin/python

# 设置工作目录
WORKDIR /app

# 复制项目文件
COPY requirements.txt .
COPY main.py .
COPY gui.py .
COPY file_scanner.py .
COPY duplicate_finder.py .
COPY cache_manager.py .
COPY config_manager.py .
COPY export_manager.py .
COPY logger.py .
COPY similarity_detector.py .
COPY build.py .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 编译 Linux 版本
RUN python build.py --gui --no-input

# 复制编译结果到输出目录
RUN mkdir -p /output && \
    cp -r dist/* /output/ && \
    ls -lah /output/

# 设置输出目录
VOLUME ["/output"]

# 默认命令
CMD ["/bin/bash"]
