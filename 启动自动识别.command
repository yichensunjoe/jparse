#!/bin/zsh
cd -- "${0:A:h}"

PYTHON_BIN="/usr/bin/python3"
for cand in python3 \
    "$HOME/.local/share/agent-tools/bin/python3" \
    "$HOME/.local/venvs/translation/bin/python3" \
    "/opt/homebrew/bin/python3" \
    "/usr/local/bin/python3"; do
    if command -v "$cand" >/dev/null 2>&1; then
        PYTHON_BIN="$cand"
        break
    fi
done

if "$PYTHON_BIN" src/manage.py start; then
    sleep 2
else
    printf '\n启动失败，按任意键关闭…'
    read -k 1
fi
