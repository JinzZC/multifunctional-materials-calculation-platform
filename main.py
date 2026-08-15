"""纤维拉伸强度分析工具 — 应用入口。

运行方式（注意：本机 PATH 中 python 被 Windows 商店存根遮蔽，一律使用 py 启动器）：
    py -3 main.py
"""

import sys

from PySide6.QtWidgets import QApplication

from fiber_tensile.config import APP_NAME, apply_matplotlib_chinese, default_db_path
from fiber_tensile.data.db import open_database
from fiber_tensile.ui.main_window import MainWindow


def main() -> int:
    apply_matplotlib_chinese()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    conn = open_database(default_db_path())
    win = MainWindow(conn)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
