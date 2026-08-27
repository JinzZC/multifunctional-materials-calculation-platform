"""界面偏好持久化（QSettings）：窗口几何、上次目录、默认强力单位。"""

from PySide6.QtCore import QSettings

_ORG = "FiberTensile"
_APP = "FiberTensileAnalyzer"
_VALID_UNITS = ("cN", "N", "mN")
_VALID_WEIBULL_RANK_METHODS = ("hazen", "mean_rank", "benard", "blom")
_VALID_WEIBULL_FIT_METHODS = ("lsq", "mle", "mle3p")


def _settings() -> QSettings:
    return QSettings(_ORG, _APP)


def load_geometry():
    """返回保存的窗口几何（QByteArray），从未保存过返回 None。"""
    value = _settings().value("window/geometry")
    return value if value is not None else None


def save_geometry(geometry) -> None:
    _settings().setValue("window/geometry", geometry)


def last_dir() -> str:
    """上次使用的文件对话框目录，空字符串表示未记录。"""
    return str(_settings().value("paths/last_dir", "") or "")


def set_last_dir(path: str) -> None:
    if path:
        _settings().setValue("paths/last_dir", path)


def default_force_unit() -> str:
    """录入页默认强力单位（校验取值合法性）。"""
    unit = str(_settings().value("entry/default_force_unit", "cN"))
    return unit if unit in _VALID_UNITS else "cN"


def set_default_force_unit(unit: str) -> None:
    if unit in _VALID_UNITS:
        _settings().setValue("entry/default_force_unit", unit)


def last_module() -> int:
    """上次使用的功能模块索引（导航栏），默认 0（纤维拉伸强度）。"""
    try:
        return int(_settings().value("nav/module", 0))
    except (TypeError, ValueError):
        return 0


def set_last_module(index: int) -> None:
    _settings().setValue("nav/module", index)


def weibull_rank_method() -> str:
    """上次使用的 Weibull 排序概率方法。"""
    method = str(_settings().value("analysis/weibull_rank_method", "hazen"))
    return method if method in _VALID_WEIBULL_RANK_METHODS else "hazen"


def set_weibull_rank_method(method: str) -> None:
    if method in _VALID_WEIBULL_RANK_METHODS:
        _settings().setValue("analysis/weibull_rank_method", method)


def weibull_fit_method() -> str:
    """上次使用的 Weibull 参数拟合方法。"""
    method = str(_settings().value("analysis/weibull_fit_method", "lsq"))
    return method if method in _VALID_WEIBULL_FIT_METHODS else "lsq"


def set_weibull_fit_method(method: str) -> None:
    if method in _VALID_WEIBULL_FIT_METHODS:
        _settings().setValue("analysis/weibull_fit_method", method)


def background_enabled() -> bool:
    return str(_settings().value("appearance/background_enabled", "true")).lower() \
        not in {"false", "0", "no"}


def set_background_enabled(enabled: bool) -> None:
    _settings().setValue("appearance/background_enabled", bool(enabled))


def background_path() -> str:
    """自定义背景路径；空字符串表示使用软件内置背景。"""
    return str(_settings().value("appearance/background_path", "") or "")


def set_background_path(path: str) -> None:
    _settings().setValue("appearance/background_path", path or "")


def background_opacity() -> int:
    try:
        return max(5, min(100, int(_settings().value("appearance/background_opacity", 55))))
    except (TypeError, ValueError):
        return 55


def set_background_opacity(value: int) -> None:
    _settings().setValue("appearance/background_opacity", max(5, min(100, int(value))))


def background_mode() -> str:
    mode = str(_settings().value("appearance/background_mode", "cover"))
    return mode if mode in {"cover", "contain", "center", "tile"} else "cover"


def set_background_mode(mode: str) -> None:
    if mode in {"cover", "contain", "center", "tile"}:
        _settings().setValue("appearance/background_mode", mode)
