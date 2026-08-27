"""一键双打包脚本（EXE 使用中文名，避免 .bat 的编码问题，由 Python 驱动 PyInstaller）。

产物：
    dist\\多功能计算平台\\多功能计算平台.exe       文件夹版（启动快，推荐）
    dist\\多功能计算平台单文件版.exe               单文件版（便携）
运行：py -3 scripts/build.py（或双击 scripts\\build.bat）
"""

import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "fiber_tensile" / "assets"
ICON = ASSETS / "app_icon.ico"

_COMMON = [
    "-m", "PyInstaller",
    "--noconfirm", "--clean", "--windowed",
    "--icon", str(ICON),
    "--add-data", f"{ASSETS}{os.pathsep}fiber_tensile/assets",
    "--hidden-import", "matplotlib.backends.backend_qtagg",
    "--exclude-module", "tkinter",
    "--exclude-module", "PySide6.QtWebEngineWidgets",
    # pandas/numpy 的 PyInstaller hooks 会把测试与构建工具链一并收集；运行时不需要。
    "--exclude-module", "pytest",
    "--exclude-module", "_pytest",
    "--exclude-module", "setuptools",
    "--exclude-module", "pygments",
    "--exclude-module", "pandas.tests",
    "--exclude-module", "numpy.tests",
]


def run(args: list) -> None:
    print(">> py " + " ".join(args))
    subprocess.check_call([sys.executable, *args], cwd=str(ROOT))


def main() -> None:
    run([*_COMMON, "--name", "多功能计算平台", "main.py"])
    run([*_COMMON, "--onefile", "--name", "多功能计算平台单文件版", "main.py"])
    print("打包完成：")
    print("  文件夹版：dist\\多功能计算平台\\多功能计算平台.exe")
    print("  单文件版：dist\\多功能计算平台单文件版.exe")


if __name__ == "__main__":
    main()
