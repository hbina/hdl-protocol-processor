ARG VARIANT=ubuntu-24.04
FROM mcr.microsoft.com/vscode/devcontainers/base:${VARIANT}

ENV DEBIAN_FRONTEND=noninteractive
ENV PDK_ROOT=/home/vscode/ttsetup/pdk
ENV PDK=ihp-sg13g2
ARG TT_SUPPORT_TOOLS_BRANCH=main

RUN apt update
RUN apt install -y iverilog gtkwave python3 python3-venv python3-tk python-is-python3 libcairo2 verilator libpng-dev libqhull-dev

# Use uv for Python environments and dependency installation.
RUN curl -LsSf https://astral.sh/uv/0.11.8/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

# Clone tt-support-tools
RUN mkdir -p /ttsetup
RUN git clone -b ${TT_SUPPORT_TOOLS_BRANCH} https://github.com/TinyTapeout/tt-support-tools /ttsetup/tt-support-tools

COPY .devcontainer/copy_tt_support_tools.sh /ttsetup

RUN uv venv --python 3.12 /ttsetup/venv
RUN uv pip install --python /ttsetup/venv/bin/python -r /ttsetup/tt-support-tools/requirements.txt

# Install verible (for formatting)
RUN umask 022 && \
    curl -L https://github.com/chipsalliance/verible/releases/download/v0.0-4023-gc1271a00/verible-v0.0-4023-gc1271a00-linux-static-x86_64.tar.gz | \
    tar zxf - -C /usr/local --strip-components=1 && \
    chmod 755 /usr/local/bin

# Install LibreLane
RUN uv pip install --python /ttsetup/venv/bin/python librelane==3.0.0.dev44
