"""全局配置：应用信息、数据库路径、matplotlib 中文配置。

数值范围常量已移至 core/modes.py（计算模式注册表），此处仅再导出。
"""

import os
import sys
from pathlib import Path

from .core.modes import (  # noqa: F401 — 兼容旧导入路径
    RANGE_DENSITY_GCM3,
    RANGE_DIAMETER_UM,
    RANGE_FORCE_CN,
    RANGE_LINEAR_DENSITY_DTEX,
)

APP_NAME = "多功能计算平台"
APP_VERSION = "0.5.0"

# 文件名非法字符（Windows）：报告默认文件名需清理，避免导出失败
_INVALID_FILENAME_CHARS = set('\\/:*?"<>|')


def asset_path(filename: str) -> str:
    """返回源码运行或 PyInstaller 打包后的内置资源绝对路径。"""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return str(root / "fiber_tensile" / "assets" / filename)


def sanitize_filename(name: str, fallback: str = "报告") -> str:
    """把样品/批次名中的文件系统非法字符替换为下划线，空名用 fallback。"""
    cleaned = "".join("_" if ch in _INVALID_FILENAME_CHARS else ch
                      for ch in (name or "").strip())
    return cleaned or fallback


def default_db_path() -> str:
    """数据库文件路径：%LOCALAPPDATA%\\FiberTensile\\fiber_tensile.db。

    可用环境变量 FT_DB_PATH 覆盖（测试与便携使用）。
    """
    override = os.environ.get("FT_DB_PATH")
    if override:
        return override
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "FiberTensile", "fiber_tensile.db")


def apply_matplotlib_chinese() -> None:
    """matplotlib 中文显示配置，须在创建任何 Figure 之前调用一次。

    Windows 11 必装微软雅黑（Microsoft YaHei），无需随包分发字体文件。
    """
    import matplotlib

    matplotlib.rcParams["font.sans-serif"] = [
        "Microsoft YaHei", "SimHei", "SimSun", "Arial Unicode MS",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False
