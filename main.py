"""多功能计算平台 — 应用入口。

运行方式（注意：本机 PATH 中 python 被 Windows 商店存根遮蔽，一律使用 py 启动器）：
    py -3 main.py
"""

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from fiber_tensile.config import APP_NAME, APP_VERSION, apply_matplotlib_chinese, default_db_path
from fiber_tensile.data.db import open_database
from fiber_tensile.logging_setup import install_excepthook, setup_logging
from fiber_tensile.ui.main_window import MainWindow


def _crash_dialog(exc_value) -> None:
    """未捕获异常时弹窗提示（日志已由钩子写入）。"""
    if QApplication.instance() is not None:
        QMessageBox.critical(
            None, "程序出错",
            f"发生未预期的错误：\n{exc_value}\n\n"
            "详细信息已记录到日志文件 app.log，可连同日志反馈问题。")


def main() -> int:
    db_path = default_db_path()
    log_path = setup_logging(db_path)
    logger = logging.getLogger("app")
    install_excepthook(logger, on_crash=_crash_dialog)

    apply_matplotlib_chinese()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    logger.info(f"启动 {APP_NAME} v{APP_VERSION}（数据库：{db_path}，日志：{log_path}）")

    conn = open_database(db_path)
    win = MainWindow(conn)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
