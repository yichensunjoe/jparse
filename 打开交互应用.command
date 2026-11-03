#!/bin/zsh
cd -- "${0:A:h}"

PYTHON_BIN="/usr/bin/python3"
for cand in "$HOME/.local/share/agent-tools/bin/python3" \
    python3 \
    "$HOME/.local/venvs/translation/bin/python3" \
    "/opt/homebrew/bin/python3" \
    "/usr/local/bin/python3"; do
    if command -v "$cand" >/dev/null 2>&1; then
        PYTHON_BIN="$cand"
        break
    fi
done

echo "正在启动 JParse 交互式工作台 (支持拖放单文件与整套文件夹)..."
"$PYTHON_BIN" src/web_app.py
