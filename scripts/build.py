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


def _build_environment() -> dict[str, str]:
    """Return a clean environment for PyInstaller binary discovery.

    Qt6Core intentionally uses the Windows system ICU DLLs.  If PATH contains
    another product's unversioned ``icuuc.dll`` (for example Poppler),
    PyInstaller may bundle that incompatible copy and Qt will fail at startup
    with "The specified procedure could not be found".  Remove only those
    third-party directories while keeping Windows' own system directories.
    """
    env = os.environ.copy()
    windows_dir = Path(env.get("WINDIR", r"C:\Windows")).resolve()
    system_dirs = {
        (windows_dir / "System32").resolve(),
        (windows_dir / "SysWOW64").resolve(),
    }
    kept: list[str] = []
    removed: list[str] = []
    for raw in env.get("PATH", "").split(os.pathsep):
        if not raw:
            continue
        path = Path(raw)
        try:
            resolved = path.resolve()
            has_foreign_icu = (
                resolved not in system_dirs
                and ((resolved / "icuuc.dll").is_file()
                     or any(resolved.glob("icudt*.dll")))
            )
        except OSError:
            has_foreign_icu = False
        if has_foreign_icu:
            removed.append(raw)
        else:
            kept.append(raw)
    env["PATH"] = os.pathsep.join(kept)
    if removed:
        print("Build PATH: ignored incompatible third-party ICU directories:")
        for path in removed:
            print(f"  {path}")
    return env


def run(args: list) -> None:
    print(">> py " + " ".join(args))
    subprocess.check_call(
        [sys.executable, *args], cwd=str(ROOT), env=_build_environment()
    )


def main() -> None:
    run([*_COMMON, "--name", "多功能计算平台", "main.py"])
    run([*_COMMON, "--onefile", "--name", "多功能计算平台单文件版", "main.py"])
    print("打包完成：")
    print("  文件夹版：dist\\多功能计算平台\\多功能计算平台.exe")
    print("  单文件版：dist\\多功能计算平台单文件版.exe")


if __name__ == "__main__":
    main()
