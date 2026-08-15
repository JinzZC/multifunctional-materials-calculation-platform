"""全局配置：应用信息、数据库路径、matplotlib 中文配置。

数值范围常量已移至 core/modes.py（计算模式注册表），此处仅再导出。
"""

import os

from .core.modes import (  # noqa: F401 — 兼容旧导入路径
    RANGE_DENSITY_GCM3,
    RANGE_DIAMETER_UM,
    RANGE_FORCE_CN,
    RANGE_LINEAR_DENSITY_DTEX,
)

APP_NAME = "多功能计算平台"
APP_VERSION = "0.2.0"


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
