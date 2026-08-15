"""日志配置：旋转文件日志 + 未捕获异常钩子。

日志文件 app.log 与数据库同目录（跟随 FT_DB_PATH），便于用户反馈问题时远程定位。
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging(db_path: str) -> str:
    """配置根日志器（幂等，重复调用不重复挂 handler），返回日志文件路径。"""
    log_dir = os.path.dirname(db_path) or os.getcwd()
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "app.log")
    root = logging.getLogger()
    if not root.handlers:
        handler = RotatingFileHandler(
            log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        root.addHandler(handler)
        root.setLevel(logging.INFO)
    return log_path


def install_excepthook(logger: logging.Logger, on_crash=None) -> None:
    """未捕获异常：先记入日志，再执行可选回调（如弹窗提示），最后走默认处理。"""

    def hook(exc_type, exc_value, exc_tb):
        logger.critical("未捕获异常", exc_info=(exc_type, exc_value, exc_tb))
        if on_crash is not None:
            try:
                on_crash(exc_value)
            except Exception:  # noqa: BLE001 — 崩溃回调本身失败不能再抛
                pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = hook
