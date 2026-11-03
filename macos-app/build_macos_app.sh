#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_NAME="LiteParse Studio"
APP_BUNDLE="$PROJECT_ROOT/$APP_NAME.app"
OUTBOX_APP="$PROJECT_ROOT/outbox/$APP_NAME.app"

echo "=================================================="
echo "🚀 正在编译与封装 macOS 原生 Liquid Glass 桌面应用"
echo "   应用名称: $APP_NAME.app"
echo "   工程路径: $PROJECT_ROOT"
echo "=================================================="

# 1. 确保图标已生成
if [ ! -f "$SCRIPT_DIR/AppIcon.icns" ]; then
    echo "🎨 正在生成高保真应用图标..."
    python3 "$SCRIPT_DIR/generate_icon.py"
fi

# 2. 创建 .app 目录结构
echo "📁 创建 Bundle 目录结构..."
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# 3. 复制元数据与资源
cp "$SCRIPT_DIR/Info.plist" "$APP_BUNDLE/Contents/Info.plist"
cp "$SCRIPT_DIR/AppIcon.icns" "$APP_BUNDLE/Contents/Resources/AppIcon.icns"
echo "APPL????" > "$APP_BUNDLE/Contents/PkgInfo"

# 4. 编译 Swift 源码
echo "⚡️ 正在使用 Apple Swift 编译器编译原生 Liquid Glass 渲染前端..."
SWIFT_SOURCES=(
    "$SCRIPT_DIR/Sources/Models/Models.swift"
    "$SCRIPT_DIR/Sources/Models/AppSettings.swift"
    "$SCRIPT_DIR/Sources/Services/BackendManager.swift"
    "$SCRIPT_DIR/Sources/Views/LightTheme.swift"
    "$SCRIPT_DIR/Sources/Views/LightHeaderView.swift"
    "$SCRIPT_DIR/Sources/Views/LightDropZoneView.swift"
    "$SCRIPT_DIR/Sources/Views/LightTaskCardView.swift"
    "$SCRIPT_DIR/Sources/Views/LightFooterView.swift"
    "$SCRIPT_DIR/Sources/Views/LightContentView.swift"
    "$SCRIPT_DIR/Sources/Views/SettingsView.swift"
    "$SCRIPT_DIR/Sources/Views/MainContentView.swift"
    "$SCRIPT_DIR/Sources/App.swift"
)

swiftc -O -parse-as-library "${SWIFT_SOURCES[@]}" \
    -o "$APP_BUNDLE/Contents/MacOS/LiteParseStudio"

# 5. 本地 ad-hoc 代码签名
echo "🔏 正在进行本机安全签名..."
codesign --force --deep --sign - "$APP_BUNDLE"

# 6. 同步交付一份至 outbox/
echo "📦 正在交付至 outbox/ 成果目录..."
mkdir -p "$PROJECT_ROOT/outbox"
rm -rf "$OUTBOX_APP"
cp -R "$APP_BUNDLE" "$OUTBOX_APP"

echo "=================================================="
echo "🎉 恭喜！LiteParse Studio 原生 Liquid Glass 应用构建完成！"
echo "   应用程序路径: $APP_BUNDLE"
echo "   交付产物路径: $OUTBOX_APP"
echo "   大小: $(du -sh "$APP_BUNDLE" | cut -f1)"
echo "   双击打开即可直接享受原生 Liquid Glass 液态毛玻璃交互！"
echo "=================================================="
