"""Tab2 统计分析：批次选择、统计结果、Weibull 参数与拟合图、报告导出。"""

from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.models import MODE_LABELS, Batch
from ..core.modes import get_mode_spec, strength_unit_label
from ..core.statistics import batch_statistics
from ..core.weibull import weibull_fit
from ..data.repository import get_batch, get_strengths, list_batches
from . import prefs

UNSAVED = -1   # 批次组合框「当前未保存数据」的哨兵值

logger = logging.getLogger(__name__)


def export_batch_report(parent: QWidget, batch: Batch, strengths: list, kind: str) -> None:
    """导出一个批次（或未保存数据）的 Excel/PDF 报告。kind: 'xlsx' | 'pdf'。"""
    import os

    from ..fileio.exporter_excel import export_excel_report
    from ..fileio.exporter_pdf import export_pdf_report

    if not strengths:
        QMessageBox.warning(parent, "无法导出", "当前没有数据可导出。")
        return
    try:
        stats = batch_statistics(strengths)
    except ValueError as e:
        QMessageBox.warning(parent, "无法导出", str(e))
        return
    try:
        weibull = weibull_fit(strengths)
    except ValueError:
        weibull = None
    ext = kind
    start = prefs.last_dir()
    default = os.path.join(start, f"{batch.batch_name}_报告.{ext}") if start \
        else f"{batch.batch_name}_报告.{ext}"
    path, _ = QFileDialog.getSaveFileName(
        parent, "导出报告", default, f"{ext.upper()} 文件 (*.{ext})")
    if not path:
        return
    prefs.set_last_dir(os.path.dirname(path))
    try:
        if kind == "xlsx":
            export_excel_report(path, batch, stats, weibull)
        else:
            export_pdf_report(path, batch, stats, weibull)
    except Exception as e:  # noqa: BLE001 — 导出异常一律提示给用户
        logger.warning(f"导出 {kind} 报告失败：{e}")
        QMessageBox.critical(parent, "导出失败", str(e))
        return
    logger.info(f"已导出 {kind} 报告：{path}（批次「{batch.batch_name}」）")
    QMessageBox.information(parent, "导出成功", f"报告已保存到：\n{path}")


class AnalysisTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._entry_tab = None
        self._build_ui()
        self.refresh()

    def set_entry_tab(self, tab) -> None:
        self._entry_tab = tab

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("选择批次："))
        self._combo = QComboBox()
        self._combo.setMinimumWidth(380)
        self._combo.currentIndexChanged.connect(self._on_batch_selected)
        top.addWidget(self._combo)
        self._btn_refresh = QPushButton("刷新")
        self._btn_refresh.clicked.connect(self.refresh)
        top.addWidget(self._btn_refresh)
        top.addStretch(1)
        root.addLayout(top)

        middle = QHBoxLayout()

        stats_group = QGroupBox("统计结果")
        stats_layout = QVBoxLayout(stats_group)
        self._stats_table = QTableWidget(0, 2)
        self._stats_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._stats_table.verticalHeader().setVisible(False)
        self._stats_table.horizontalHeader().setVisible(False)
        self._stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        stats_layout.addWidget(self._stats_table, 1)
        middle.addWidget(stats_group, 2)

        weibull_group = QGroupBox("Weibull 分布分析")
        w_layout = QVBoxLayout(weibull_group)
        self._lbl_m = QLabel("Weibull 模数 m：—")
        self._lbl_sigma0 = QLabel("特征强度 σ₀：—")
        self._lbl_r2 = QLabel("拟合优度 R²：—")
        for lbl in (self._lbl_m, self._lbl_sigma0, self._lbl_r2):
            w_layout.addWidget(lbl)
        # 画布延迟创建：matplotlib 只在首次绘制时加载，加快应用启动
        self._canvas = None
        self._toolbar = None
        self._weibull_layout = w_layout
        self._canvas_placeholder = QLabel("（图表组件在首次分析时加载）")
        self._canvas_placeholder.setAlignment(Qt.AlignCenter)
        self._canvas_placeholder.setStyleSheet("color: #888;")
        w_layout.addWidget(self._canvas_placeholder, 1)
        middle.addWidget(weibull_group, 3)

        root.addLayout(middle, 1)

        bottom = QHBoxLayout()
        self._btn_excel = QPushButton("导出 Excel 报告…")
        self._btn_pdf = QPushButton("导出 PDF 报告…")
        self._btn_excel.clicked.connect(lambda: self._export("xlsx"))
        self._btn_pdf.clicked.connect(lambda: self._export("pdf"))
        bottom.addStretch(1)
        bottom.addWidget(self._btn_excel)
        bottom.addWidget(self._btn_pdf)
        root.addLayout(bottom)

    # ---- 数据装载 ----

    def refresh(self) -> None:
        current = self._combo.currentData()
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItem("当前未保存数据", UNSAVED)
        for b in list_batches(self._conn):
            self._combo.addItem(
                f"{b.batch_name}（{MODE_LABELS[b.mode]}，{b.sample_count} 条）", b.id)
        self._combo.blockSignals(False)
        if current is not None:
            idx = self._combo.findData(current)
            self._combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._on_batch_selected()

    def _current_payload(self) -> tuple | None:
        """返回 (mode, density, batch_name, batch, strengths)。"""
        data = self._combo.currentData()
        if data == UNSAVED:
            if self._entry_tab is None:
                return None
            mode, density, samples = self._entry_tab.current_unsaved()
            batch = Batch(batch_name="未保存数据", mode=mode, density=density,
                          samples=list(samples), sample_count=len(samples))
            strengths = [s.strength for s in samples if s.strength is not None]
            return mode, density, "未保存数据", batch, strengths
        batch = get_batch(self._conn, data)
        return (batch.mode, batch.density, batch.batch_name, batch,
                get_strengths(self._conn, data))

    def _ensure_canvas(self) -> None:
        """首次需要绘图时才创建 matplotlib 画布（延迟加载 matplotlib）。"""
        if self._canvas is not None:
            return
        from .weibull_plot import ChineseNavigationToolbar, MplCanvas, localize_toolbar

        self._canvas = MplCanvas()
        self._toolbar = ChineseNavigationToolbar(self._canvas, self)
        localize_toolbar(self._toolbar)
        idx = self._weibull_layout.indexOf(self._canvas_placeholder)
        self._weibull_layout.removeWidget(self._canvas_placeholder)
        self._canvas_placeholder.deleteLater()
        self._canvas_placeholder = None
        self._weibull_layout.insertWidget(idx, self._canvas, 1)
        self._weibull_layout.insertWidget(idx + 1, self._toolbar)

    def _on_batch_selected(self) -> None:
        payload = self._current_payload()
        if payload is None:
            return
        mode, density, name, batch, strengths = payload
        unit = strength_unit_label(mode)

        try:
            stats = batch_statistics(strengths)
        except ValueError:
            stats = None
        rows = []
        if stats is not None:
            rows = [
                ("样本数 N", str(stats.n)),
                (f"均值({unit})", f"{stats.mean:.2f}"),
                (f"标准差({unit})", f"{stats.std:.2f}" if stats.std is not None else "—"),
                ("变异系数 CV%", f"{stats.cv_percent:.2f}" if stats.cv_percent is not None else "—"),
                (f"最小值({unit})", f"{stats.min_val:.2f}"),
                (f"最大值({unit})", f"{stats.max_val:.2f}"),
            ]
        self._stats_table.setRowCount(len(rows))
        for r, (k, v) in enumerate(rows):
            self._stats_table.setItem(r, 0, QTableWidgetItem(k))
            self._stats_table.setItem(r, 1, QTableWidgetItem(v))

        try:
            w = weibull_fit(strengths)
        except ValueError as e:
            self._lbl_m.setText("Weibull 模数 m：—")
            self._lbl_sigma0.setText("特征强度 σ₀：—")
            self._lbl_r2.setText("拟合优度 R²：—")
            if self._canvas is not None:
                self._canvas.fig.clf()
                self._canvas.draw()
            self._weibull_error = str(e)
            return
        self._ensure_canvas()
        self._weibull_error = None
        self._lbl_m.setText(f"Weibull 模数 m = {w.m:.4f}")
        sigma0_text = f"特征强度 σ₀ = {w.sigma0:.2f} {unit}"
        if get_mode_spec(mode).uses_density and density is not None:
            sigma0_text += f"（≈ {w.sigma0 * density * 100:.2f} MPa）"
        self._lbl_sigma0.setText(sigma0_text)
        self._lbl_r2.setText(f"拟合优度 R² = {w.r2:.4f}")
        self._canvas.draw_weibull([w], labels=[name], sigma0_unit=unit)

    def _export(self, kind: str) -> None:
        payload = self._current_payload()
        if payload is None:
            return
        _, _, _, batch, strengths = payload
        export_batch_report(self, batch, strengths, kind)
