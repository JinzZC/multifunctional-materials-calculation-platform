"""纤维拉伸强度分析模块的第④子页签：单丝拉伸曲线分析（平台校正）。

流程：参数（直径/标距/拟合区间/单位）→ 导入位移-力曲线 → 自动平台校正分析
→ 结果（E、σ_b、校正后 ε_b、平台段）+ 曲线图 + 计算过程 → 保存/历史/报告。
"""

from __future__ import annotations

import logging
import os
import sqlite3

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateEdit, QDoubleSpinBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from ..fileio.importer import ImportFileError
from ..ui import prefs
from ..ui.richtext import to_rich
from .core import analyze_curve
from .exporters import export_excel_report, export_pdf_report
from .importer import parse_curve_file
from .repository import (
    create_curve_analysis, delete_curve_analysis, get_curve_analysis,
    list_curve_analyses,
)

logger = logging.getLogger(__name__)


class CurveAnalysisTab(QWidget):
    """单丝曲线分析页。"""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._canvas = None
        self._toolbar = None
        self._last = None      # (disp_mm, force_n, result, fit_lo, fit_hi)
        self._build_ui()
        self._connect_signals()
        self.refresh_history()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        param_box = QGroupBox("曲线分析参数")
        form = QFormLayout(param_box)
        self._edit_sample_name = QLineEdit()
        self._edit_sample_name.setPlaceholderText("必填，如：T300-1#")
        self._spin_diameter = QDoubleSpinBox()
        self._spin_diameter.setRange(0.1, 1000)
        self._spin_diameter.setDecimals(2)
        self._spin_diameter.setValue(5.4)
        self._spin_gauge = QDoubleSpinBox()
        self._spin_gauge.setRange(0.1, 500)
        self._spin_gauge.setDecimals(1)
        self._spin_gauge.setValue(25.0)
        self._spin_fit_lo = QDoubleSpinBox()
        self._spin_fit_lo.setRange(0.05, 0.5)
        self._spin_fit_lo.setDecimals(2)
        self._spin_fit_lo.setSingleStep(0.05)
        self._spin_fit_lo.setValue(0.2)
        self._spin_fit_hi = QDoubleSpinBox()
        self._spin_fit_hi.setRange(0.5, 0.95)
        self._spin_fit_hi.setDecimals(2)
        self._spin_fit_hi.setSingleStep(0.05)
        self._spin_fit_hi.setValue(0.7)
        fit_row = QHBoxLayout()
        fit_row.addWidget(QLabel("下限"))
        fit_row.addWidget(self._spin_fit_lo)
        fit_row.addWidget(QLabel("上限"))
        fit_row.addWidget(self._spin_fit_hi)
        self._combo_force_unit = QComboBox()
        self._combo_force_unit.addItems(["N", "cN", "mN"])
        self._combo_disp_unit = QComboBox()
        self._combo_disp_unit.addItems(["mm", "μm"])
        self._edit_remark = QLineEdit()
        self._date_test = QDateEdit(QDate.currentDate())
        self._date_test.setCalendarPopup(True)
        self._date_test.setDisplayFormat("yyyy-MM-dd")
        form.addRow("样品名称：", self._edit_sample_name)
        form.addRow("直径(μm)：", self._spin_diameter)
        form.addRow("标距(mm)：", self._spin_gauge)
        form.addRow("拟合区间（×F_max）：", fit_row)
        form.addRow("力单位：", self._combo_force_unit)
        form.addRow("位移单位：", self._combo_disp_unit)
        form.addRow("备注：", self._edit_remark)
        form.addRow("测试日期：", self._date_test)
        top.addWidget(param_box, 3)

        btn_col = QVBoxLayout()
        btn_col.addWidget(QLabel(
            "导入试验机导出的位移-力两列数据\n（起始段「只伸长不增力」的平台\n"
            "将自动校正，得到准确伸长率）"))
        self._btn_import = QPushButton("导入曲线文件…")
        self._btn_save = QPushButton("保存分析结果")
        self._btn_save.setStyleSheet("font-weight: bold;")
        btn_col.addWidget(self._btn_import)
        btn_col.addWidget(self._btn_save)
        btn_col.addStretch(1)
        top.addLayout(btn_col, 1)
        root.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)

        left_box = QGroupBox("分析结果与计算过程")
        l_layout = QVBoxLayout(left_box)
        self._lbl_e = QLabel("弹性模量 E：—")
        self._lbl_sigma = QLabel("断裂强度 σ_b：—")
        self._lbl_eps = QLabel("断裂伸长率（校正后）：—")
        self._lbl_toe = QLabel("平台段应变（已校正）：—")
        self._lbl_r2 = QLabel("拟合优度 R²：—")
        for lbl in (self._lbl_e, self._lbl_sigma, self._lbl_eps,
                    self._lbl_toe, self._lbl_r2):
            l_layout.addWidget(lbl)
        self._txt_process = QTextEdit()
        self._txt_process.setReadOnly(True)
        self._txt_process.setPlaceholderText("导入曲线后在此显示逐步计算过程")
        self._txt_process.setStyleSheet(
            "font-family: Consolas, 'Microsoft YaHei'; font-size: 9.5pt;")
        l_layout.addWidget(self._txt_process, 1)
        split.addWidget(left_box)

        right_box = QGroupBox("拉伸曲线图")
        r_layout = QVBoxLayout(right_box)
        self._canvas_placeholder = QLabel("（导入曲线后显示）")
        self._canvas_placeholder.setAlignment(Qt.AlignCenter)
        self._canvas_placeholder.setStyleSheet("color: #888;")
        r_layout.addWidget(self._canvas_placeholder)
        self._figure_layout = r_layout
        split.addWidget(right_box)
        split.setSizes([520, 560])
        root.addWidget(split, 2)

        root.addWidget(QLabel("历史记录："))
        self._history = QTableWidget(0, 9)
        self._history.setHorizontalHeaderLabels(
            ["样品名称", "直径(μm)", "标距(mm)", "E(GPa)", "σ_b(MPa)",
             "ε_b(%)", "平台(%)", "R²", "测试日期"])
        self._history.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._history.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._history.setSelectionMode(QAbstractItemView.SingleSelection)
        self._history.verticalHeader().setVisible(False)
        self._history.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._history.horizontalHeader().setStretchLastSection(True)
        self._history.setColumnWidth(0, 150)
        root.addWidget(self._history, 2)

        h_buttons = QHBoxLayout()
        self._btn_delete = QPushButton("删除记录")
        self._btn_export_xlsx = QPushButton("导出 Excel 报告…")
        self._btn_export_pdf = QPushButton("导出 PDF 报告…")
        for b in (self._btn_delete, self._btn_export_xlsx, self._btn_export_pdf):
            h_buttons.addWidget(b)
        h_buttons.addStretch(1)
        root.addLayout(h_buttons)

    def _connect_signals(self) -> None:
        self._btn_import.clicked.connect(self._import_curve)
        self._btn_save.clicked.connect(self._save)
        self._btn_delete.clicked.connect(self._delete_history)
        self._btn_export_xlsx.clicked.connect(lambda: self._export_selected("xlsx"))
        self._btn_export_pdf.clicked.connect(lambda: self._export_selected("pdf"))
        self._spin_diameter.valueChanged.connect(self._reanalyze)
        self._spin_gauge.valueChanged.connect(self._reanalyze)
        self._spin_fit_lo.valueChanged.connect(self._reanalyze)
        self._spin_fit_hi.valueChanged.connect(self._reanalyze)

    # ---- 导入与分析 ----

    def _import_curve(self) -> None:
        start = prefs.last_dir()
        path, _ = QFileDialog.getOpenFileName(
            self, "选择曲线文件", start or "",
            "数据文件 (*.csv *.txt *.xlsx *.xlsm);;所有文件 (*.*)")
        if not path:
            return
        prefs.set_last_dir(os.path.dirname(path))
        try:
            disp_raw, force_raw = parse_curve_file(path)
        except (ImportFileError, ValueError) as e:
            QMessageBox.warning(self, "导入失败", str(e))
            return
        # 单位换算：力→N，位移→mm
        f_scale = {"N": 1.0, "cN": 0.01, "mN": 0.001}[self._combo_force_unit.currentText()]
        d_scale = {"mm": 1.0, "μm": 0.001}[self._combo_disp_unit.currentText()]
        disp = [d * d_scale for d in disp_raw]
        force = [f * f_scale for f in force_raw]
        self._analyze(disp, force)

    def _analyze(self, disp_mm, force_n) -> None:
        try:
            result = analyze_curve(
                disp_mm, force_n, self._spin_diameter.value(),
                self._spin_gauge.value(),
                fit_lo=self._spin_fit_lo.value(), fit_hi=self._spin_fit_hi.value())
        except ValueError as e:
            QMessageBox.warning(self, "分析失败", str(e))
            return
        self._last = (disp_mm, force_n, result,
                      self._spin_fit_lo.value(), self._spin_fit_hi.value())
        self._show_result(result)

    def _reanalyze(self, *args) -> None:
        """参数调整后自动重算（已有曲线时）。"""
        if self._last is None:
            return
        disp, force, _, _, _ = self._last
        self._analyze(disp, force)

    def _show_result(self, result) -> None:
        self._lbl_e.setText(f"弹性模量 E = {result.e_gpa:.2f} GPa")
        self._lbl_sigma.setText(f"断裂强度 σ_b = {result.strength_mpa:.2f} MPa")
        self._lbl_eps.setText(f"断裂伸长率（校正后）ε_b = {result.elongation_pct:.3f}%")
        self._lbl_toe.setText(
            f"平台段应变（已校正）ε₀ = {result.toe_eps_pct:.3f}%"
            f"（位移₀ = {result.toe_disp_mm:.3f} mm）")
        self._lbl_r2.setText(f"拟合优度 R² = {result.r2:.4f}")
        self._txt_process.setHtml("<br>".join(to_rich(s) for s in result.steps))
        self._draw_curve(result)

    def _ensure_canvas(self) -> None:
        if self._canvas is not None:
            return
        from .plotting import build_curve_figure
        from ..ui.weibull_plot import ChineseNavigationToolbar, MplCanvas, localize_toolbar

        self._canvas = MplCanvas()
        self._toolbar = ChineseNavigationToolbar(self._canvas, self)
        localize_toolbar(self._toolbar)
        layout = self._figure_layout
        idx = layout.indexOf(self._canvas_placeholder)
        layout.removeWidget(self._canvas_placeholder)
        self._canvas_placeholder.deleteLater()
        self._canvas_placeholder = None
        layout.insertWidget(idx, self._toolbar)
        layout.insertWidget(idx + 1, self._canvas, 1)
        self._build_curve_figure = build_curve_figure

    def _draw_curve(self, result) -> None:
        self._ensure_canvas()
        disp, force, _, _, _ = self._last
        self._build_curve_figure(disp, force, result, fig=self._canvas.fig)
        self._canvas.draw()

    # ---- 保存 / 历史 / 导出 ----

    def _save(self) -> None:
        if self._last is None:
            QMessageBox.information(self, "提示", "请先导入曲线文件。")
            return
        sample_name = self._edit_sample_name.text().strip()
        if not sample_name:
            QMessageBox.warning(self, "无法保存", "请先填写样品名称。")
            return
        disp, force, result, fit_lo, fit_hi = self._last
        mid = create_curve_analysis(
            self._conn, sample_name, self._spin_diameter.value(),
            self._spin_gauge.value(), result, disp, force,
            fit_lo=fit_lo, fit_hi=fit_hi,
            remark=self._edit_remark.text().strip() or None,
            test_date=self._date_test.date().toString("yyyy-MM-dd"))
        logger.info(f"已保存曲线分析「{sample_name}」(id={mid})")
        self.refresh_history()
        QMessageBox.information(
            self, "保存成功",
            f"样品「{sample_name}」已保存。\nE = {result.e_gpa:.2f} GPa，"
            f"ε_b = {result.elongation_pct:.3f}%（校正后）")

    def refresh_history(self) -> None:
        rows = list_curve_analyses(self._conn)
        self._history.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [
                row["sample_name"], f"{row['diameter_um']:g}",
                f"{row['gauge_length_mm']:g}",
                f"{row['e_gpa']:.2f}" if row["e_gpa"] is not None else "—",
                f"{row['strength_mpa']:.2f}" if row["strength_mpa"] is not None else "—",
                f"{row['elongation_pct']:.3f}" if row["elongation_pct"] is not None else "—",
                f"{row['toe_eps_pct']:.3f}" if row["toe_eps_pct"] is not None else "—",
                f"{row['r2']:.4f}" if row["r2"] is not None else "—",
                row["test_date"] or "—",
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if 3 <= c <= 7:
                    item.setTextAlignment(Qt.AlignCenter)
                self._history.setItem(r, c, item)
        self._history_rows = rows

    def _selected_id(self):
        indexes = self._history.selectedIndexes()
        if not indexes:
            return None
        return self._history_rows[indexes[0].row()]["id"]

    def _delete_history(self) -> None:
        cid = self._selected_id()
        if cid is None:
            QMessageBox.information(self, "提示", "请先在历史记录中选择一条记录。")
            return
        if QMessageBox.question(self, "确认删除", "确定删除选中的曲线分析记录？") \
                != QMessageBox.Yes:
            return
        delete_curve_analysis(self._conn, cid)
        self.refresh_history()

    def _export_selected(self, kind: str) -> None:
        cid = self._selected_id()
        if cid is None:
            QMessageBox.information(self, "提示", "请先在历史记录中选择一条记录。")
            return
        try:
            row, points = get_curve_analysis(self._conn, cid)
        except ValueError as e:
            QMessageBox.warning(self, "导出失败", str(e))
            return
        disp = [p[0] for p in points]
        force = [p[1] for p in points]
        try:
            result = analyze_curve(
                disp, force, row["diameter_um"], row["gauge_length_mm"],
                fit_lo=row["fit_lo"] or 0.2, fit_hi=row["fit_hi"] or 0.7)
        except ValueError as e:
            QMessageBox.warning(self, "导出失败", str(e))
            return
        start = prefs.last_dir()
        default = os.path.join(start, f"{row['sample_name']}_曲线分析报告.{kind}") \
            if start else f"{row['sample_name']}_曲线分析报告.{kind}"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出报告", default, f"{kind.upper()} 文件 (*.{kind})")
        if not path:
            return
        prefs.set_last_dir(os.path.dirname(path))
        try:
            if kind == "xlsx":
                export_excel_report(path, row["sample_name"], row["diameter_um"],
                                    row["gauge_length_mm"], result, disp, force,
                                    row["remark"], row["test_date"])
            else:
                export_pdf_report(path, row["sample_name"], row["diameter_um"],
                                  row["gauge_length_mm"], result, disp, force,
                                  row["remark"], row["test_date"])
        except Exception as e:  # noqa: BLE001
            logger.warning(f"导出曲线报告失败：{e}")
            QMessageBox.critical(self, "导出失败", str(e))
            return
        logger.info(f"已导出曲线分析 {kind} 报告：{path}")
        QMessageBox.information(self, "导出成功", f"报告已保存到：\n{path}")
