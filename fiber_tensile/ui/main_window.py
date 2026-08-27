"""主窗口：左侧模块导航栏 + 堆叠页面。

模块结构：
    ├── 纤维拉伸强度（内部子页签：①数据录入 ②统计分析 ③历史记录）
    └── 表面能（OWRK/Wu/Fowkes/Zisman）

新增功能域（如 EMI）时在导航栏加一项、堆叠区加一页即可。
"""

import sqlite3

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QListWidget, QListWidgetItem, QMainWindow, QStackedWidget,
    QMessageBox, QTabWidget, QVBoxLayout, QWidget,
)

from ..composites.ui import CompositesTab
from ..config import APP_NAME, APP_VERSION, asset_path, default_db_path
from ..curve_analysis.ui import CurveAnalysisTab
from ..excel_merger.ui import ExcelMergerTab
from ..surface_energy.ui import SurfaceEnergyTab
from . import prefs
from .analysis_tab import AnalysisTab
from .background import BackgroundSettingsDialog, BackgroundWidget
from .entry_tab import EntryTab
from .history_tab import HistoryTab

def _nav_style(glass: bool) -> str:
    background = "rgba(247, 250, 253, 205)" if glass else "#F7FAFD"
    hover = "rgba(221, 235, 247, 225)" if glass else "#DDEBF7"
    return """
QListWidget {{
    border: 1px solid #C9D7E8; border-radius: 6px;
    background: {background}; font-size: 12pt; padding: 4px;
}}
QListWidget::item {{
    padding: 12px 8px; border-radius: 4px; color: #1F4E79;
    background: rgba(255, 255, 255, 72);
}}
QListWidget::item:selected {{
    background: rgba(31, 78, 121, 225); color: white;
}}
QListWidget::item:hover:!selected {{ background: {hover}; }}
""".format(background=background, hover=hover)


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setWindowIcon(QIcon(asset_path("app_icon.png")))
        self.resize(1180, 780)
        self.setMinimumSize(940, 640)
        geometry = prefs.load_geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)

        central = BackgroundWidget()
        self._background = central
        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ---- 左侧模块导航栏 ----
        self._nav = QListWidget()
        self._nav.setFixedWidth(190)
        self._nav.setWordWrap(True)          # 模块名过长时自动换行，保证完整显示
        self._nav.setUniformItemSizes(False)
        self._nav.setStyleSheet(_nav_style(prefs.background_enabled()))
        self._nav.addItem(QListWidgetItem("纤维拉伸强度分析模块"))
        self._nav.addItem(QListWidgetItem("接触角表面能模块"))
        self._nav.addItem(QListWidgetItem("复合材料基础计算模块"))
        self._nav.item(0).setToolTip("单丝/纺织纤维强度计算、统计与 Weibull 分析、曲线分析")
        self._nav.item(1).setToolTip("接触角法测量固体表面能：OWRK/Wu/Fowkes/Zisman 计算")
        self._nav.item(2).setToolTip("混合法则单层板常数、纤维体积分数与孔隙率")
        self._nav.addItem(QListWidgetItem("表格数据提取合并模块"))
        self._nav.item(3).setToolTip(
            "从多个文件夹及子文件夹提取 Excel、CSV、TXT、TSV 并按样品名排序")
        root.addWidget(self._nav)

        # ---- 右侧堆叠页面 ----
        self._stack = QStackedWidget()

        # 模块一：纤维拉伸强度（内部三个子页签）
        fiber_page = QWidget()
        f_layout = QVBoxLayout(fiber_page)
        f_layout.setContentsMargins(0, 0, 0, 0)
        fiber_tabs = QTabWidget()
        self.entry_tab = EntryTab(conn)
        self.analysis_tab = AnalysisTab(conn)
        self.history_tab = HistoryTab(conn)
        self.curve_tab = CurveAnalysisTab(conn)
        self.analysis_tab.set_entry_tab(self.entry_tab)
        fiber_tabs.addTab(self.entry_tab, "① 数据录入")
        fiber_tabs.addTab(self.analysis_tab, "② 统计分析")
        fiber_tabs.addTab(self.history_tab, "③ 历史记录")
        fiber_tabs.addTab(self.curve_tab, "④ 曲线分析")
        f_layout.addWidget(fiber_tabs)
        self._stack.addWidget(fiber_page)

        # 模块二：表面能
        self.surface_tab = SurfaceEnergyTab(conn)
        self._stack.addWidget(self.surface_tab)

        # 模块三：复合材料基础计算
        self.composites_tab = CompositesTab(conn)
        self._stack.addWidget(self.composites_tab)

        # 模块四：Excel 数据批量提取与合并（不使用数据库）
        self.excel_merger_tab = ExcelMergerTab()
        self._stack.addWidget(self.excel_merger_tab)

        root.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        # 导航切换 + 记忆上次使用的模块
        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        saved = prefs.last_module()
        self._nav.setCurrentRow(saved if 0 <= saved < self._nav.count() else 0)

        self._build_menu()
        self.statusBar().showMessage(f"数据库：{default_db_path()}")

        # Tab 间联动：数据变化后刷新分析与历史
        self.entry_tab.saved.connect(self._on_data_saved)
        self.entry_tab.data_changed.connect(self._on_data_changed)
        self.history_tab.data_changed.connect(self._on_data_changed)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件(&F)")
        act_quit = QAction("退出(&Q)", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        appearance_menu = self.menuBar().addMenu("界面(&V)")
        act_background = QAction("背景设置…", self)
        act_background.triggered.connect(self._show_background_settings)
        appearance_menu.addAction(act_background)

        help_menu = self.menuBar().addMenu("帮助(&H)")
        act_about = QAction("关于(&A)", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    def _show_background_settings(self) -> None:
        if BackgroundSettingsDialog(self).exec() == QDialog.Accepted:
            self._background.reload_background()
            self._nav.setStyleSheet(_nav_style(prefs.background_enabled()))

    def _show_about(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(
            self, "关于",
            f"<b>{APP_NAME} v{APP_VERSION}</b><br><br>"
            "功能模块：<br>"
            "· 纤维拉伸强度分析模块：σ = 4F/(πd²) 单丝模式（GB/T 31290）、"
            "断裂强度 = F/线密度 纺织模式（GB/T 14337）、Weibull 分析<br>"
            "· 接触角表面能模块：OWRK 双液法 / Wu 调和平均法 / Fowkes 法 / "
            "Zisman 法<br>"
            "· 复合材料基础计算模块：工程常数、体积分数与孔隙率<br>"
            "· 表格数据提取合并模块：Excel/CSV/TXT/TSV 扫描、样品排序与来源追踪<br><br>"
            "支持批量导入、Excel/PDF 报告导出。")

    def _on_data_saved(self, batch_id: int) -> None:
        self._refresh_analysis_and_history()

    def _on_data_changed(self) -> None:
        self._refresh_analysis_and_history()

    def _refresh_analysis_and_history(self) -> None:
        self.analysis_tab.refresh()
        self.history_tab.refresh()

    def closeEvent(self, event) -> None:
        if self.entry_tab.has_pending_data():
            answer = QMessageBox.question(
                self, "存在未保存数据",
                "纤维拉伸强度录入页仍有未保存数据，确定放弃并退出吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                event.ignore()
                return
        if not self.excel_merger_tab.shutdown():
            QMessageBox.warning(
                self, "暂时无法退出",
                "表格数据提取任务尚未安全停止，请稍后再关闭软件。")
            event.ignore()
            return
        prefs.save_geometry(self.saveGeometry())
        prefs.set_last_module(self._nav.currentRow())
        self._conn.close()
        super().closeEvent(event)
