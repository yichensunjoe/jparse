"""Release packaging tool for JParse (Windows & macOS).

Creates clean, standalone distribution zip archives ready for end-users,
and places them in `release/` and `outbox/`.
"""

import os
from pathlib import Path
import shutil
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RELEASE_DIR = PROJECT_ROOT / "release"
OUTBOX_DIR = PROJECT_ROOT / "outbox"
BUILD_DIR = PROJECT_ROOT / "build" / "package_staging"

VERSION = "v2.1.0"
WIN_PKG_NAME = f"JParse-Windows-{VERSION}"
MAC_PKG_NAME = f"JParse-macOS-{VERSION}"


def create_readme_txt(dest_dir: Path) -> None:
    readme_content = (
        "========================================================================\r\n"
        "  JParse - 学术级 PDF 智能重构与排版引擎 (Windows 独立绿色便携版)\r\n"
        "========================================================================\r\n"
        "\r\n"
        "【快速上手三步】：\r\n"
        "  第一步：确保您的电脑安装了 Python 3.9 ~ 3.12 (并勾选 Add Python to PATH)。\r\n"
        "          如果没有，可直接在 PowerShell 运行：winget install Python.Python.3.12\r\n"
        "  第二步：双击运行 [一键安装环境-Windows.bat] (首次运行自动创建独立虚拟环境并安装排版库)。\r\n"
        "  第三步：双击运行 [启动JParse桌面应用(无黑框).vbs] 开启专属桌面应用！\r\n"
        "\r\n"
        "【常用快捷方式】：\r\n"
        "  - 启动JParse桌面应用(无黑框).vbs  : 纯净静默拉起独立桌面视窗 (日常主力推荐)\r\n"
        "  - 启动JParse桌面应用.bat          : 以桌面应用启动并保留控制台日志\r\n"
        "  - 打开交互应用.bat                : 在系统默认浏览器打开 Web 交互工作台\r\n"
        "  - 打开PDF投递箱.bat               : 在资源管理器打开 inbox 文件夹 (放入待处理文献)\r\n"
        "  - 打开识别结果.bat               : 在资源管理器打开 outbox 文件夹 (查收转换成果)\r\n"
        "  - 启动自动识别.bat                : 启动后台监控进程 (全自动批量无人值守)\r\n"
        "  - 停止自动识别.bat                : 停止后台自动监控进程\r\n"
        "  - 查看运行状态.bat                : 查看当前运行状态与队列计数\r\n"
        "\r\n"
        "【详细文档】：\r\n"
        "  请查阅文件夹内的 README_WINDOWS.md 获取更多高级设置与常见问题解答。\r\n"
    )
    (dest_dir / "使用说明-先看我.txt").write_bytes(readme_content.encode("utf-8-sig"))


def package_windows() -> Path:
    print(f"📦 正在打包 Windows 发布版本: {WIN_PKG_NAME}...")
    staging = BUILD_DIR / WIN_PKG_NAME
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    # 1. Copy batch files & VBS
    batch_files = [
        "一键安装环境-Windows.bat",
        "install_windows.bat",
        "启动JParse桌面应用(无黑框).vbs",
        "启动JParse桌面应用.bat",
        "打开交互应用.bat",
        "启动自动识别.bat",
        "停止自动识别.bat",
        "查看运行状态.bat",
        "打开PDF投递箱.bat",
        "打开识别结果.bat",
        "翻译已识别文献.bat",
    ]
    for bf in batch_files:
        src = PROJECT_ROOT / bf
        if src.is_file():
            shutil.copy2(src, staging / bf)

    # 2. Copy configs and docs
    for doc in ["README_WINDOWS.md", "README.md", "requirements.txt", "config.json"]:
        src = PROJECT_ROOT / doc
        if src.is_file():
            shutil.copy2(src, staging / doc)

    # 3. Create instruction text
    create_readme_txt(staging)

    # 4. Copy src/
    shutil.copytree(PROJECT_ROOT / "src", staging / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    # 5. Copy assets/ if present
    assets_src = PROJECT_ROOT / "assets"
    if assets_src.is_dir():
        shutil.copytree(
            assets_src,
            staging / "assets",
            ignore=shutil.ignore_patterns("*.bin", "*.onnx", "*.pth", "__pycache__"),
        )

    # 6. Pre-create clean inbox / outbox / processed / failed / logs
    for d in ["inbox", "outbox", "processed", "failed", "logs"]:
        target_dir = staging / d
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / ".gitkeep").write_text("", encoding="utf-8")

    # 7. Zip staging directory
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    zip_dest = RELEASE_DIR / f"{WIN_PKG_NAME}.zip"
    if zip_dest.exists():
        zip_dest.unlink()

    print(f"🗜 正在压缩为 zip 归档: {zip_dest}...")
    with zipfile.ZipFile(zip_dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(staging):
            for file in files:
                full_path = Path(root) / file
                arcname = full_path.relative_to(staging)
                zf.write(full_path, arcname)

    # Also deliver to outbox
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    outbox_copy = OUTBOX_DIR / f"{WIN_PKG_NAME}.zip"
    shutil.copy2(zip_dest, outbox_copy)

    pkg_size = zip_dest.stat().st_size / (1024 * 1024)
    print(f"✅ Windows 安装包生成成功: {zip_dest} ({pkg_size:.2f} MB)")
    print(f"✅ 已同步至成果目录: {outbox_copy}")
    return zip_dest


def package_macos() -> Path:
    print(f"📦 正在打包 macOS 原生应用发布版本: {MAC_PKG_NAME}...")
    app_src = PROJECT_ROOT / "JParse.app"
    if not app_src.is_dir():
        print("⚠️ 未找到 JParse.app，尝试从 outbox/JParse.app 寻找...")
        app_src = OUTBOX_DIR / "JParse.app"

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    zip_dest = RELEASE_DIR / f"{MAC_PKG_NAME}.zip"
    if zip_dest.exists():
        zip_dest.unlink()

    if app_src.is_dir():
        # Zip JParse.app
        shutil.make_archive(str(RELEASE_DIR / MAC_PKG_NAME), "zip", PROJECT_ROOT, "JParse.app")
        outbox_copy = OUTBOX_DIR / f"{MAC_PKG_NAME}.zip"
        shutil.copy2(zip_dest, outbox_copy)
        pkg_size = zip_dest.stat().st_size / (1024 * 1024)
        print(f"✅ macOS 安装包生成成功: {zip_dest} ({pkg_size:.2f} MB)")
        return zip_dest
    else:
        print("⚠️ 跳过 macOS 打包 (JParse.app 不存在)")
        return Path()


def main():
    win_zip = package_windows()
    mac_zip = package_macos()
    print("\n🎉 发布包构建完成！")
    print(f"   Windows 安装包路径: {win_zip}")
    if mac_zip.exists():
        print(f"   macOS 安装包路径:   {mac_zip}")


if __name__ == "__main__":
    main()
