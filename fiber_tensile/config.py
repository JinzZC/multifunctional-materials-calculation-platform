"""全局配置：应用信息、数据库路径、数值范围、matplotlib 中文配置。"""

import os

APP_NAME = "纤维拉伸强度分析工具"
APP_VERSION = "0.1.0"

# 数值合理范围（超出仅警告，不阻断录入）
RANGE_DIAMETER_UM = (0.1, 1000.0)          # 直径 μm
RANGE_FORCE_CN = (0.001, 100000.0)         # 断裂强力 cN
RANGE_LINEAR_DENSITY_DTEX = (0.05, 100000.0)  # 线密度 dtex
RANGE_DENSITY_GCM3 = (0.5, 3.5)            # 密度 g/cm³


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
