"""主窗口：菜单栏、状态栏与三个功能 Tab 的装配。"""

import sqlite3

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QTabWidget

from ..config import APP_NAME, APP_VERSION, default_db_path
from . import prefs
from .analysis_tab import AnalysisTab
from .entry_tab import EntryTab
from .history_tab import HistoryTab


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1100, 760)
        geometry = prefs.load_geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)

        self._tabs = QTabWidget()
        self.entry_tab = EntryTab(conn)
        self.analysis_tab = AnalysisTab(conn)
        self.history_tab = HistoryTab(conn)
        self.analysis_tab.set_entry_tab(self.entry_tab)
        self._tabs.addTab(self.entry_tab, "① 数据录入")
        self._tabs.addTab(self.analysis_tab, "② 统计分析")
        self._tabs.addTab(self.history_tab, "③ 历史记录")
        self.setCentralWidget(self._tabs)

        self._build_menu()
        self.statusBar().showMessage(f"数据库：{default_db_path()}")

        # Tab 间联动：数据变化后刷新分析与历史
        self.entry_tab.saved.connect(self._on_data_saved)
        self.entry_tab.data_changed.connect(self._on_data_changed)
        self.history_tab.data_changed.connect(self._on_data_changed)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件(&F)")
        act_quit = QAction("退出(&Q)", self)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        help_menu = self.menuBar().addMenu("帮助(&H)")
        act_about = QAction("关于(&A)", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _show_about(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(
            self, "关于",
            f"<b>{APP_NAME} v{APP_VERSION}</b><br><br>"
            "计算单根纤维的最大拉伸强度：<br>"
            "· 单丝模式：σ = 4F/(πd²)（GB/T 31290）<br>"
            "· 纺织模式：断裂强度 = F/线密度（GB/T 14337）<br><br>"
            "支持批量统计、Weibull 分布分析、Excel/PDF 报告导出。")

    def _on_data_saved(self, batch_id: int) -> None:
        self._refresh_analysis_and_history()

    def _on_data_changed(self) -> None:
        self._refresh_analysis_and_history()

    def _refresh_analysis_and_history(self) -> None:
        self.analysis_tab.refresh()
        self.history_tab.refresh()

    def closeEvent(self, event) -> None:
        prefs.save_geometry(self.saveGeometry())
        super().closeEvent(event)
