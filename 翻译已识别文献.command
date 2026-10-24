#!/bin/zsh
cd -- "${0:A:h}"

PYTHON_BIN=""
for cand in python3 \
    "$HOME/.local/share/agent-tools/bin/python3" \
    "$HOME/.local/venvs/translation/bin/python3" \
    "/opt/homebrew/bin/python3" \
    "/usr/local/bin/python3" \
    "$HOME/.pyenv/shims/python3"; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import ctranslate2" >/dev/null 2>&1; then
        PYTHON_BIN="$cand"
        break
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    printf '\n未检测到已安装 ctranslate2 的 Python 环境。\n'
    printf '请先在终端运行：pip install ctranslate2 sentencepiece\n'
    printf '或检查您的 Python 虚拟环境配置。\n\n按任意键退出…'
    read -k 1
    exit 1
fi

if "$PYTHON_BIN" src/translator.py --interactive; then
    sleep 2
else
    printf '\n翻译程序退出，按任意键关闭…'
    read -k 1
fi
