"""Tab3 历史记录：筛选查询、批次表、样本明细、批次对比、删除/重算/导出。"""

from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.models import MODE_FILAMENT, MODE_LABELS, MODE_TEXTILE, strength_unit_label
from ..core.statistics import batch_statistics
from ..core.weibull import weibull_fit
from ..data.repository import (
    delete_batch, get_batch, get_strengths, list_batches, recalculate_batch,
)
from .analysis_tab import export_batch_report
from .csv_export import save_csv_dialog
from .dialogs import CompareDialog


logger = logging.getLogger(__name__)


class HistoryTab(QWidget):
    """历史记录页。data_changed 在删除批次等库内容变化时发出。"""

    data_changed = Signal()

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._batches: list = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # 筛选行
        filters = QHBoxLayout()
        filters.addWidget(QLabel("批次名称："))
        self._edit_keyword = QLineEdit()
        self._edit_keyword.setMaximumWidth(160)
        filters.addWidget(self._edit_keyword)
        filters.addWidget(QLabel("模式："))
        self._combo_mode = QComboBox()
        self._combo_mode.addItem("全部模式", None)
        self._combo_mode.addItem(MODE_LABELS[MODE_FILAMENT], MODE_FILAMENT)
        self._combo_mode.addItem(MODE_LABELS[MODE_TEXTILE], MODE_TEXTILE)
        filters.addWidget(self._combo_mode)
        self._chk_date = QCheckBox("按创建日期筛选")
        filters.addWidget(self._chk_date)
        self._date_from = QDateEdit(QDate.currentDate().addMonths(-1))
        self._date_to = QDateEdit(QDate.currentDate())
        for d in (self._date_from, self._date_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("yyyy-MM-dd")
            d.setEnabled(False)
        self._chk_date.toggled.connect(
            lambda on: (self._date_from.setEnabled(on), self._date_to.setEnabled(on)))
        filters.addWidget(self._date_from)
        filters.addWidget(QLabel("至"))
        filters.addWidget(self._date_to)
        self._btn_query = QPushButton("查询")
        self._btn_query.clicked.connect(self.refresh)
        filters.addWidget(self._btn_query)
        self._btn_reset = QPushButton("重置")
        self._btn_reset.clicked.connect(self._reset_filters)
        filters.addWidget(self._btn_reset)
        filters.addStretch(1)
        root.addLayout(filters)

        # 批次表
        root.addWidget(QLabel("批次列表（双击或单击查看明细，按住 Ctrl 多选对比）："))
        self._batch_table = QTableWidget(0, 6)
        self._batch_table.setHorizontalHeaderLabels(
            ["批次名称", "模式", "纤维类型", "样本数", "创建时间", "备注"])
        self._batch_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._batch_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._batch_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._batch_table.verticalHeader().setVisible(False)
        self._batch_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._batch_table.horizontalHeader().setStretchLastSection(True)
        self._batch_table.setColumnWidth(0, 200)
        self._batch_table.setColumnWidth(1, 110)
        self._batch_table.setColumnWidth(2, 130)
        self._batch_table.setColumnWidth(3, 70)
        self._batch_table.setColumnWidth(4, 150)
        self._batch_table.itemSelectionChanged.connect(self._on_selection_changed)

        # 批次列表与样本明细用可拖拽分隔条
        splitter = QSplitter(Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        batch_widget = QWidget()
        bw_layout = QVBoxLayout(batch_widget)
        bw_layout.setContentsMargins(0, 0, 0, 0)
        bw_layout.addWidget(self._batch_table)
        splitter.addWidget(batch_widget)

        detail_widget = QWidget()
        dw_layout = QVBoxLayout(detail_widget)
        dw_layout.setContentsMargins(0, 0, 0, 0)
        dw_layout.addWidget(QLabel("样本明细："))
        self._detail_table = QTableWidget(0, 8)
        self._detail_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._detail_table.verticalHeader().setVisible(False)
        self._detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._detail_table.horizontalHeader().setStretchLastSection(True)
        dw_layout.addWidget(self._detail_table)
        splitter.addWidget(detail_widget)
        splitter.setSizes([320, 240])
        root.addWidget(splitter, 3)

        buttons = QHBoxLayout()
        self._btn_compare = QPushButton("对比批次（≥2 个同模式）")
        self._btn_delete = QPushButton("删除批次")
        self._btn_recalc = QPushButton("重新计算强度")
        self._btn_export_xlsx = QPushButton("导出 Excel 报告…")
        self._btn_export_pdf = QPushButton("导出 PDF 报告…")
        self._btn_export_csv = QPushButton("导出 CSV 数据…")
        self._btn_compare.clicked.connect(self._compare)
        self._btn_delete.clicked.connect(self._delete_selected)
        self._btn_recalc.clicked.connect(self._recalculate)
        self._btn_export_xlsx.clicked.connect(lambda: self._export_selected("xlsx"))
        self._btn_export_pdf.clicked.connect(lambda: self._export_selected("pdf"))
        self._btn_export_csv.clicked.connect(self._export_csv)
        for b in (self._btn_compare, self._btn_delete, self._btn_recalc,
                  self._btn_export_xlsx, self._btn_export_pdf, self._btn_export_csv):
            buttons.addWidget(b)
        buttons.addStretch(1)
        root.addLayout(buttons)

        self._update_button_states()

    # ---- 查询与刷新 ----

    def _reset_filters(self) -> None:
        self._edit_keyword.clear()
        self._combo_mode.setCurrentIndex(0)
        self._chk_date.setChecked(False)
        self.refresh()

    def refresh(self) -> None:
        keyword = self._edit_keyword.text().strip() or None
        mode = self._combo_mode.currentData()
        date_from = date_to = None
        if self._chk_date.isChecked():
            date_from = self._date_from.date().toString("yyyy-MM-dd")
            date_to = self._date_to.date().toString("yyyy-MM-dd")
        self._batches = list_batches(self._conn, keyword=keyword, mode=mode,
                                     date_from=date_from, date_to=date_to)
        self._batch_table.setRowCount(len(self._batches))
        for r, b in enumerate(self._batches):
            values = [b.batch_name, MODE_LABELS[b.mode], b.fiber_type or "—",
                      str(b.sample_count), b.created_at or "—", b.remark or ""]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c in (1, 3):
                    item.setTextAlignment(Qt.AlignCenter)
                self._batch_table.setItem(r, c, item)
        self._detail_table.setRowCount(0)
        # 刷新后清除选中，避免行号错位导致误删/误导出
        self._batch_table.clearSelection()
        self._update_button_states()

    # ---- 选中与明细 ----

    def _selected_batches(self) -> list:
        return [self._batches[i.row()] for i in self._batch_table.selectedIndexes()
                if i.column() == 0]

    def _on_selection_changed(self) -> None:
        selected = self._selected_batches()
        self._detail_table.setRowCount(0)
        if len(selected) == 1:
            self._load_detail(selected[0])
        self._update_button_states()

    def _load_detail(self, batch) -> None:
        b = get_batch(self._conn, batch.id)
        mode = b.mode
        unit = strength_unit_label(mode)
        headers = ["编号", "断裂强力", "单位",
                   "直径(μm)" if mode == MODE_FILAMENT else "线密度(dtex)",
                   "密度(g/cm³)", f"强度({unit})", "强度(MPa)", "备注", "测试日期"]
        self._detail_table.setHorizontalHeaderLabels(headers)
        self._detail_table.setColumnCount(len(headers))
        self._detail_table.setRowCount(len(b.samples))
        for r, s in enumerate(b.samples):
            dim = s.diameter_um if mode == MODE_FILAMENT else s.linear_density_dtex
            values = [
                s.sample_no or "—", f"{s.breaking_force:g}", s.force_unit, f"{dim:g}",
                f"{b.density:g}" if b.density is not None else "—",
                f"{s.strength:,.2f}" if s.strength is not None else "—",
                f"{s.strength_mpa:,.2f}" if s.strength_mpa is not None else "—",
                s.remark or "", s.test_date or "",
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c in (1, 2, 3, 4, 5, 6):
                    item.setTextAlignment(Qt.AlignCenter)
                self._detail_table.setItem(r, c, item)
        for i, w in enumerate([70, 90, 50, 110, 95, 110, 110, 160, 100]):
            self._detail_table.setColumnWidth(i, w)

    def _update_button_states(self) -> None:
        n = len(self._selected_batches())
        same_mode = len({b.mode for b in self._selected_batches()}) <= 1
        self._btn_compare.setEnabled(n >= 2 and same_mode)
        self._btn_delete.setEnabled(n >= 1)
        self._btn_recalc.setEnabled(n == 1)
        self._btn_export_xlsx.setEnabled(n == 1)
        self._btn_export_pdf.setEnabled(n == 1)
        self._btn_export_csv.setEnabled(n == 1)

    # ---- 操作 ----

    def _compare(self) -> None:
        selected = self._selected_batches()
        if len({b.mode for b in selected}) > 1:
            QMessageBox.warning(self, "无法对比", "请选择相同模式的批次进行对比。")
            return
        payload = []
        for b in selected:
            batch = get_batch(self._conn, b.id)
            strengths = get_strengths(self._conn, b.id)
            # 单丝模式按 GPa 拟合（与分析页横轴一致）
            fit_strengths = ([s / 1000.0 for s in strengths]
                             if batch.mode == MODE_FILAMENT else strengths)
            try:
                stats = batch_statistics(strengths)
                weibull = weibull_fit(fit_strengths)
            except ValueError:
                continue
            payload.append((batch, stats, weibull))
        if len(payload) < 2:
            QMessageBox.warning(self, "无法对比", "所选批次数据不足，无法对比。")
            return
        sigma0_unit = ("GPa" if payload[0][0].mode == MODE_FILAMENT
                       else strength_unit_label(payload[0][0].mode))
        CompareDialog(payload, self, sigma0_unit=sigma0_unit).exec()

    def _delete_selected(self) -> None:
        selected = self._selected_batches()
        if not selected:
            return
        names = "、".join(b.batch_name for b in selected)
        if QMessageBox.question(
                self, "确认删除",
                f"确定删除 {len(selected)} 个批次（{names}）及其全部样本数据？此操作不可恢复。") \
                != QMessageBox.Yes:
            return
        for b in selected:
            delete_batch(self._conn, b.id)
            logger.info(f"已删除批次「{b.batch_name}」(id={b.id})")
        self.refresh()
        self.data_changed.emit()

    def _recalculate(self) -> None:
        selected = self._selected_batches()
        if len(selected) != 1:
            return
        try:
            n = recalculate_batch(self._conn, selected[0].id)
        except ValueError as e:
            logger.warning(f"重新计算失败：{e}")
            QMessageBox.warning(self, "重新计算失败", str(e))
            return
        self._load_detail(selected[0])
        logger.info(f"已重新计算批次「{selected[0].batch_name}」的 {n} 条数据")
        QMessageBox.information(self, "完成", f"已重新计算 {n} 条数据的强度。")

    def _export_selected(self, kind: str) -> None:
        selected = self._selected_batches()
        if len(selected) != 1:
            return
        batch = get_batch(self._conn, selected[0].id)
        strengths = get_strengths(self._conn, selected[0].id)
        export_batch_report(self, batch, strengths, kind)

    def _export_csv(self) -> None:
        """把选中批次的样本明细导出为 CSV。"""
        selected = self._selected_batches()
        if len(selected) != 1:
            return
        batch = get_batch(self._conn, selected[0].id)
        mode = batch.mode
        unit = strength_unit_label(mode)
        headers = ["编号", "断裂强力", "强力单位",
                   "直径(μm)" if mode == MODE_FILAMENT else "线密度(dtex)",
                   "密度(g/cm³)", f"强度({unit})", "强度(MPa)", "备注", "测试日期"]
        rows = []
        for s in batch.samples:
            dim = s.diameter_um if mode == MODE_FILAMENT else s.linear_density_dtex
            rows.append([
                s.sample_no or "", f"{s.breaking_force:g}", s.force_unit, f"{dim:g}",
                f"{batch.density:g}" if batch.density is not None else "",
                f"{s.strength:.6g}" if s.strength is not None else "",
                f"{s.strength_mpa:.6g}" if s.strength_mpa is not None else "",
                s.remark or "", s.test_date or "",
            ])
        save_csv_dialog(self, f"{batch.batch_name}_数据", headers, rows)
