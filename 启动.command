#!/bin/sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
export UV_CACHE_DIR="$APP_DIR/.runtime/uv-cache"

if ! command -v uv >/dev/null 2>&1; then
  echo "正在安装 Python 管理工具 uv…"
  INSTALLER=$(mktemp "${TMPDIR:-/tmp}/uv-install.XXXXXX")
  curl -LsSf https://astral.sh/uv/install.sh -o "$INSTALLER"
  sh "$INSTALLER"
  rm -f "$INSTALLER"
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

cd "$APP_DIR"
exec uv run --python 3.11 --with certifi python scripts/setup_and_start.py
