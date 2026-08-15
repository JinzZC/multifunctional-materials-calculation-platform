"""Tab④ 表面能：方法选择（白话公式）、液体数据录入、计算保存、历史与报告。

页面纵向五步流：
    ① 计算方法（公式白话展示） → ② 样品信息 → ③ 液体数据（接触角列高亮）
    → ④ 计算结果 + 计算过程（并排，各占半宽） → ⑤ 历史记录

方法单选按钮由 core.METHODS 注册表动态生成；matplotlib 仅在 Zisman 图
首次绘制时加载。
"""

from __future__ import annotations

import logging
import os
import sqlite3

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..fileio.importer import ImportFileError
from ..ui import prefs
from .core import METHOD_LABELS, METHODS, get_method_spec, LiquidPoint
from .exporters import export_excel_report, export_pdf_report
from .importer import parse_measurement_file
from .repository import (
    add_liquid, create_measurement, delete_measurement, get_measurement,
    list_liquids, list_measurements,
)

logger = logging.getLogger(__name__)

# 表格列：接触角紧随液体名称、高亮显示，其余参数由液体库自动填充
COL_NAME, COL_ANGLE, COL_GAMMA, COL_GD, COL_GP = range(5)


class SurfaceEnergyTab(QWidget):
    """表面能计算页。"""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._canvas = None
        self._toolbar = None
        self._build_ui()
        self._connect_signals()
        self._on_method_changed()
        self.refresh_history()

    # ---- UI ----

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # ---- 第一行：① 计算方法（白话公式） + ② 样品信息 ----
        top_row = QHBoxLayout()

        method_box = QGroupBox("① 计算方法（公式如下）")
        m_layout = QVBoxLayout(method_box)
        radio_row = QHBoxLayout()
        self._radio_methods: dict[str, QRadioButton] = {}
        for i, (key, spec) in enumerate(METHODS.items()):
            radio = QRadioButton(spec.label)
            radio.setChecked(i == 0)
            self._radio_methods[key] = radio
            radio_row.addWidget(radio)
        m_layout.addLayout(radio_row)
        # 公式展示区：可上下滚动
        self._lbl_equations = QLabel()
        self._lbl_equations.setWordWrap(True)
        self._lbl_equations.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._lbl_equations.setStyleSheet(
            "font-size: 9pt; background: #FBFDFF; padding: 6px;")
        self._scroll_equations = QScrollArea()
        self._scroll_equations.setWidgetResizable(True)
        self._scroll_equations.setWidget(self._lbl_equations)
        self._scroll_equations.setStyleSheet(
            "QScrollArea { border: 1px solid #DDEBF7; border-radius: 4px;"
            "background: #FBFDFF; }")
        self._scroll_equations.setMinimumHeight(130)
        m_layout.addWidget(self._scroll_equations)
        self._lbl_hint = QLabel()
        self._lbl_hint.setWordWrap(True)
        self._lbl_hint.setStyleSheet("color: #1F4E79;")
        m_layout.addWidget(self._lbl_hint)
        top_row.addWidget(method_box, 2)

        info_box = QGroupBox("② 样品信息")
        form = QFormLayout(info_box)
        self._edit_sample_name = QLineEdit()
        self._edit_sample_name.setPlaceholderText("必填，如：PTFE 薄膜")
        self._edit_remark = QLineEdit()
        self._date_test = QDateEdit(QDate.currentDate())
        self._date_test.setCalendarPopup(True)
        self._date_test.setDisplayFormat("yyyy-MM-dd")
        form.addRow("样品名称：", self._edit_sample_name)
        form.addRow("备注：", self._edit_remark)
        form.addRow("测试日期：", self._date_test)
        top_row.addWidget(info_box, 1)
        root.addLayout(top_row)

        # ---- 操作按钮 ----
        btn_row = QHBoxLayout()
        self._btn_save = QPushButton("计算并保存")
        self._btn_save.setStyleSheet("font-weight: bold;")
        self._btn_import = QPushButton("批量导入…")
        self._btn_add_liquid = QPushButton("添加自定义液体…")
        self._btn_clear = QPushButton("清空表格")
        for b in (self._btn_save, self._btn_import, self._btn_add_liquid, self._btn_clear):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        # ---- ③ 液体数据录入（接触角列高亮）----
        liquid_header = QHBoxLayout()
        liquid_header.addWidget(QLabel(
            "③ 液体数据：选择液体后自动填充参数，只需填写蓝色【接触角(°)】列："))
        liquid_header.addStretch(1)
        self._btn_add_row = QPushButton("添加液体")
        self._btn_delete_row = QPushButton("删除选中行")
        liquid_header.addWidget(self._btn_add_row)
        liquid_header.addWidget(self._btn_delete_row)
        root.addLayout(liquid_header)
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["液体名称", "接触角 θ（度）", "γ_L（表面张力, mN/m）",
             "γ^d（色散分量, mN/m）", "γ^p（极性分量, mN/m）"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # 接触角列视觉突出
        angle_header = self._table.horizontalHeaderItem(COL_ANGLE)
        angle_header.setForeground(QColor("#1F4E79"))
        font = QFont()
        font.setBold(True)
        angle_header.setFont(font)
        self._table.setColumnWidth(COL_NAME, 140)
        self._table.setColumnWidth(COL_ANGLE, 110)
        self._table.setMinimumHeight(150)
        root.addWidget(self._table, 2)

        # ---- ④ 计算结果 + 计算过程（并排，各占半宽）----
        result_row = QHBoxLayout()

        result_box = QGroupBox("④ 计算结果")
        r_layout = QVBoxLayout(result_box)
        self._lbl_gd = QLabel("色散分量（γ^d）：—")
        self._lbl_gp = QLabel("极性分量（γ^p）：—")
        self._lbl_gt = QLabel("总表面能（γ_S）：—")
        self._lbl_gc = QLabel("临界表面张力（γ_c）：—")
        self._lbl_r2 = QLabel("拟合优度（R²）：—")
        for lbl in (self._lbl_gd, self._lbl_gp, self._lbl_gt, self._lbl_gc, self._lbl_r2):
            r_layout.addWidget(lbl)
        self._per_table = QTableWidget(0, 3)
        self._per_table.setHorizontalHeaderLabels(
            ["液体名称", "γ_SL（界面能, mN/m）", "W_A（粘附功, mN/m）"])
        self._per_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._per_table.verticalHeader().setVisible(False)
        self._per_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        r_layout.addWidget(self._per_table, 1)
        # Zisman 图（占位，首次绘制时才加载 matplotlib）
        self._figure_container = QWidget()
        f_layout = QVBoxLayout(self._figure_container)
        f_layout.setContentsMargins(0, 0, 0, 0)
        self._canvas_placeholder = QLabel("（Zisman 图在计算后显示）")
        self._canvas_placeholder.setAlignment(Qt.AlignCenter)
        self._canvas_placeholder.setStyleSheet("color: #888;")
        f_layout.addWidget(self._canvas_placeholder)
        self._figure_container.setVisible(False)
        r_layout.addWidget(self._figure_container)
        result_row.addWidget(result_box, 1)

        process_box = QGroupBox("计算过程")
        p_layout = QVBoxLayout(process_box)
        self._txt_process = QPlainTextEdit()
        self._txt_process.setReadOnly(True)
        self._txt_process.setPlaceholderText("点击「计算并保存」后，在此显示逐步计算过程")
        self._txt_process.setStyleSheet(
            "font-family: Consolas, 'Microsoft YaHei'; font-size: 9.5pt;")
        p_layout.addWidget(self._txt_process)
        result_row.addWidget(process_box, 1)
        root.addLayout(result_row, 2)

        # ---- ⑤ 历史记录 ----
        root.addWidget(QLabel("⑤ 历史记录："))
        self._history = QTableWidget(0, 8)
        self._history.setHorizontalHeaderLabels(
            ["样品名称", "方法", "γ^d（色散分量, mN/m）", "γ^p（极性分量, mN/m）",
             "γ_S（总表面能, mN/m）", "γ_c（临界表面张力, mN/m）", "R²（拟合优度）",
             "测试日期"])
        self._history.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._history.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._history.setSelectionMode(QAbstractItemView.SingleSelection)
        self._history.verticalHeader().setVisible(False)
        self._history.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._history.horizontalHeader().setStretchLastSection(True)
        self._history.setColumnWidth(0, 180)
        root.addWidget(self._history, 2)

        h_buttons = QHBoxLayout()
        self._btn_delete_hist = QPushButton("删除记录")
        self._btn_export_xlsx = QPushButton("导出 Excel 报告…")
        self._btn_export_pdf = QPushButton("导出 PDF 报告…")
        for b in (self._btn_delete_hist, self._btn_export_xlsx, self._btn_export_pdf):
            h_buttons.addWidget(b)
        h_buttons.addStretch(1)
        root.addLayout(h_buttons)

    def _connect_signals(self) -> None:
        for radio in self._radio_methods.values():
            radio.toggled.connect(self._on_method_changed)
        self._btn_add_row.clicked.connect(self._add_row)
        self._btn_delete_row.clicked.connect(self._delete_selected_rows)
        self._btn_clear.clicked.connect(self._clear_table)
        self._btn_save.clicked.connect(self._save)
        self._btn_import.clicked.connect(self._import_file)
        self._btn_add_liquid.clicked.connect(self._add_custom_liquid)
        self._btn_delete_hist.clicked.connect(self._delete_history)
        self._btn_export_xlsx.clicked.connect(lambda: self._export_selected("xlsx"))
        self._btn_export_pdf.clicked.connect(lambda: self._export_selected("pdf"))

    # ---- 方法 / 液体库 ----

    def _method(self) -> str:
        for key, radio in self._radio_methods.items():
            if radio.isChecked():
                return key
        return next(iter(METHODS))

    def _on_method_changed(self, *args) -> None:
        spec = get_method_spec(self._method())
        self._lbl_hint.setText(f"{spec.label}：{spec.hint}")
        self._lbl_equations.setText(spec.equations)
        self._figure_container.setVisible(self._method() == "zisman")

    def _liquid_library(self) -> list:
        return list_liquids(self._conn)

    def _refresh_row_combos(self) -> None:
        liquids = self._liquid_library()
        for row in range(self._table.rowCount()):
            combo = self._table.cellWidget(row, COL_NAME)
            if combo is not None:
                current = combo.currentText()
                combo.blockSignals(True)
                combo.clear()
                combo.addItems([l["name"] for l in liquids])
                if current:
                    combo.setEditText(current)
                combo.blockSignals(False)

    def _add_row(self) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems([l["name"] for l in self._liquid_library()])
        combo.currentTextChanged.connect(
            lambda text, row=r: self._fill_row_from_library(row, text))
        self._table.setCellWidget(r, COL_NAME, combo)
        for col in (COL_GAMMA, COL_GD, COL_GP, COL_ANGLE):
            self._table.setItem(r, col, QTableWidgetItem(""))
        # 默认选中第一个液体时也立即填充其参数
        self._fill_row_from_library(r, combo.currentText())

    def _fill_row_from_library(self, row: int, name: str) -> None:
        for liquid in self._liquid_library():
            if liquid["name"] == name:
                self._table.item(row, COL_GAMMA).setText(f"{liquid['gamma_total']:g}")
                self._table.item(row, COL_GD).setText(f"{liquid['gamma_d']:g}")
                self._table.item(row, COL_GP).setText(f"{liquid['gamma_p']:g}")
                return

    def _delete_selected_rows(self) -> None:
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._table.removeRow(r)

    def _clear_table(self) -> None:
        self._table.setRowCount(0)

    # ---- 收集 / 计算 / 保存 ----

    def _collect_points(self) -> list:
        """从表格收集液体点；行级错误抛出 ValueError。"""
        points: list = []
        errors: list = []
        for row in range(self._table.rowCount()):
            combo = self._table.cellWidget(row, COL_NAME)
            name = combo.currentText().strip() if combo is not None else ""

            def cell_text(col):
                item = self._table.item(row, col)
                return item.text().strip() if item is not None else ""

            def parse_float(text, label, required=True, allow_zero=False):
                if not text:
                    if required:
                        raise ValueError(f"第 {row + 1} 行 {label} 为空")
                    return None
                try:
                    value = float(text.replace(",", ""))
                except ValueError:
                    raise ValueError(f"第 {row + 1} 行 {label} 不是有效数字：{text!r}") from None
                if value < 0 or (value == 0 and not allow_zero):
                    raise ValueError(f"第 {row + 1} 行 {label} 必须为正数")
                return value

            if not name:
                errors.append(f"第 {row + 1} 行：液体名称为空")
                continue
            try:
                gamma_total = parse_float(cell_text(COL_GAMMA), "γ_L(mN/m)")
                gamma_d = parse_float(cell_text(COL_GD), "γ^d(mN/m)", required=False,
                                      allow_zero=True)
                gamma_p = parse_float(cell_text(COL_GP), "γ^p(mN/m)", required=False,
                                      allow_zero=True)
                angle = parse_float(cell_text(COL_ANGLE), "接触角(°)")
            except ValueError as e:
                errors.append(str(e))
                continue
            if not 0.0 < angle < 180.0:
                errors.append(f"第 {row + 1} 行：接触角必须在 0–180° 之间")
                continue
            points.append(LiquidPoint(liquid_name=name, gamma_total=gamma_total,
                                      angle_deg=angle, gamma_d=gamma_d, gamma_p=gamma_p))
        if errors:
            raise ValueError("表格数据有误：\n" + "\n".join(errors))
        return points

    def _show_result(self, result) -> None:
        self._lbl_gd.setText(
            f"色散分量（γ^d）：{result.gamma_d:.2f} mN/m" if result.gamma_d is not None
            else "色散分量（γ^d）：—")
        self._lbl_gp.setText(
            f"极性分量（γ^p）：{result.gamma_p:.2f} mN/m" if result.gamma_p is not None
            else "极性分量（γ^p）：—")
        self._lbl_gt.setText(
            f"总表面能（γ_S）：{result.gamma_total:.2f} mN/m" if result.gamma_total is not None
            else "总表面能（γ_S）：—")
        self._lbl_gc.setText(
            f"临界表面张力（γ_c）：{result.gamma_c:.2f} mN/m" if result.gamma_c is not None
            else "临界表面张力（γ_c）：—")
        self._lbl_r2.setText(
            f"拟合优度（R²）：{result.r2:.4f}" if result.r2 is not None else "拟合优度（R²）：—")
        per = result.per_liquid or []
        self._per_table.setRowCount(len(per))
        for r, (name, gamma_sl, wa) in enumerate(per):
            values = [name, f"{gamma_sl:.2f}" if gamma_sl is not None else "—", f"{wa:.2f}"]
            for c, v in enumerate(values):
                self._per_table.setItem(r, c, QTableWidgetItem(v))
        self._txt_process.setPlainText("\n".join(result.steps))
        if self._method() == "zisman":
            self._draw_zisman(result)

    def _ensure_canvas(self) -> None:
        if self._canvas is not None:
            return
        from .plotting import build_zisman_figure
        from ..ui.weibull_plot import ChineseNavigationToolbar, MplCanvas, localize_toolbar

        self._canvas = MplCanvas()
        self._toolbar = ChineseNavigationToolbar(self._canvas, self)
        localize_toolbar(self._toolbar)
        layout = self._figure_container.layout()
        idx = layout.indexOf(self._canvas_placeholder)
        layout.removeWidget(self._canvas_placeholder)
        self._canvas_placeholder.deleteLater()
        self._canvas_placeholder = None
        layout.insertWidget(idx, self._toolbar)
        layout.insertWidget(idx + 1, self._canvas, 1)
        self._build_zisman_figure = build_zisman_figure

    def _draw_zisman(self, result) -> None:
        self._ensure_canvas()
        # 使用最近一次成功计算的点数据
        self._build_zisman_figure(self._points_cache, result.gamma_c, result.r2,
                                  fig=self._canvas.fig)
        self._canvas.draw()

    def _save(self) -> None:
        sample_name = self._edit_sample_name.text().strip()
        if not sample_name:
            QMessageBox.warning(self, "无法保存", "请先填写样品名称。")
            return
        try:
            points = self._collect_points()
        except ValueError as e:
            QMessageBox.warning(self, "无法保存", str(e))
            return
        method = self._method()
        try:
            from .core import compute_surface_energy
            result = compute_surface_energy(method, points)
        except ValueError as e:
            QMessageBox.warning(self, "计算失败", str(e))
            return
        self._points_cache = points
        self._show_result(result)
        mid = create_measurement(
            self._conn, sample_name, method, points,
            remark=self._edit_remark.text().strip() or None,
            test_date=self._date_test.date().toString("yyyy-MM-dd"))
        logger.info(f"已保存表面能测量「{sample_name}」(id={mid}, {method})")
        self.refresh_history()
        self._table.setRowCount(0)
        QMessageBox.information(
            self, "保存成功",
            f"样品「{sample_name}」已保存。\n{result_summary(result)}")

    # ---- 导入 / 液体库 / 历史 ----

    def _import_file(self) -> None:
        start = prefs.last_dir()
        path, _ = QFileDialog.getOpenFileName(
            self, "选择数据文件", start or "",
            "数据文件 (*.xlsx *.xlsm *.csv *.txt);;所有文件 (*.*)")
        if not path:
            return
        prefs.set_last_dir(os.path.dirname(path))
        try:
            preview = parse_measurement_file(path)
        except ImportFileError as e:
            QMessageBox.critical(self, "导入失败", str(e))
            return
        if preview.errors:
            lines = "\n".join(f"第 {e.row_number} 行：{e.message}" for e in preview.errors)
            QMessageBox.warning(self, "部分数据有误", f"以下行未导入：\n{lines}")
        if not preview.points:
            return
        if preview.method:
            self._radio_methods[preview.method].setChecked(True)
        self._edit_sample_name.setText(preview.sample_name or "")
        self._edit_remark.setText(preview.remark or "")
        if preview.test_date:
            d = QDate.fromString(preview.test_date, "yyyy-MM-dd")
            if d.isValid():
                self._date_test.setDate(d)
        for p in preview.points:
            r = self._table.rowCount()
            self._table.insertRow(r)
            combo = QComboBox()
            combo.setEditable(True)
            combo.addItems([l["name"] for l in self._liquid_library()])
            combo.setEditText(p.liquid_name)
            combo.currentTextChanged.connect(
                lambda text, row=r: self._fill_row_from_library(row, text))
            self._table.setCellWidget(r, COL_NAME, combo)
            self._table.setItem(r, COL_GAMMA, QTableWidgetItem(f"{p.gamma_total:g}"))
            self._table.setItem(r, COL_GD,
                                QTableWidgetItem(f"{p.gamma_d:g}" if p.gamma_d is not None else ""))
            self._table.setItem(r, COL_GP,
                                QTableWidgetItem(f"{p.gamma_p:g}" if p.gamma_p is not None else ""))
            self._table.setItem(r, COL_ANGLE, QTableWidgetItem(f"{p.angle_deg:g}"))
        QMessageBox.information(self, "导入完成",
                                f"已导入 {len(preview.points)} 行液体数据，请检查后点「计算并保存」。")

    def _add_custom_liquid(self) -> None:
        dlg = CustomLiquidDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            add_liquid(self._conn, dlg.name(), dlg.gamma_total(),
                       dlg.gamma_d(), dlg.gamma_p())
        except ValueError as e:
            QMessageBox.warning(self, "无法添加", str(e))
            return
        self._refresh_row_combos()
        QMessageBox.information(self, "完成", "自定义液体已加入参数库。")

    def refresh_history(self) -> None:
        rows = list_measurements(self._conn)
        self._history.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [
                row["sample_name"], METHOD_LABELS[row["method"]],
                f"{row['gamma_d']:.2f}" if row["gamma_d"] is not None else "—",
                f"{row['gamma_p']:.2f}" if row["gamma_p"] is not None else "—",
                f"{row['gamma_total']:.2f}" if row["gamma_total"] is not None else "—",
                f"{row['gamma_c']:.2f}" if row["gamma_c"] is not None else "—",
                f"{row['r2']:.4f}" if row["r2"] is not None else "—",
                row["test_date"] or "—",
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c >= 2:
                    item.setTextAlignment(Qt.AlignCenter)
                self._history.setItem(r, c, item)
        self._history_rows = rows

    def _selected_history_id(self):
        indexes = self._history.selectedIndexes()
        if not indexes:
            return None
        return self._history_rows[indexes[0].row()]["id"]

    def _delete_history(self) -> None:
        mid = self._selected_history_id()
        if mid is None:
            QMessageBox.information(self, "提示", "请先在历史记录中选择一条记录。")
            return
        if QMessageBox.question(self, "确认删除", "确定删除选中的测量记录？") != QMessageBox.Yes:
            return
        delete_measurement(self._conn, mid)
        self.refresh_history()

    def _export_selected(self, kind: str) -> None:
        mid = self._selected_history_id()
        if mid is None:
            QMessageBox.information(self, "提示", "请先在历史记录中选择一条记录。")
            return
        try:
            row, points = get_measurement(self._conn, mid)
        except ValueError as e:
            QMessageBox.warning(self, "导出失败", str(e))
            return
        start = prefs.last_dir()
        default = os.path.join(start, f"{row['sample_name']}_表面能报告.{kind}") if start \
            else f"{row['sample_name']}_表面能报告.{kind}"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出报告", default, f"{kind.upper()} 文件 (*.{kind})")
        if not path:
            return
        prefs.set_last_dir(os.path.dirname(path))
        try:
            if kind == "xlsx":
                export_excel_report(path, row["sample_name"], row["method"], points,
                                    row["remark"], row["test_date"])
            else:
                export_pdf_report(path, row["sample_name"], row["method"], points,
                                  row["remark"], row["test_date"])
        except Exception as e:  # noqa: BLE001
            logger.warning(f"导出表面能报告失败：{e}")
            QMessageBox.critical(self, "导出失败", str(e))
            return
        logger.info(f"已导出表面能 {kind} 报告：{path}")
        QMessageBox.information(self, "导出成功", f"报告已保存到：\n{path}")


def result_summary(result) -> str:
    parts = []
    if result.gamma_d is not None:
        parts.append(f"γ^d = {result.gamma_d:.2f} mN/m")
    if result.gamma_p is not None:
        parts.append(f"γ^p = {result.gamma_p:.2f} mN/m")
    if result.gamma_total is not None:
        parts.append(f"γ_S = {result.gamma_total:.2f} mN/m")
    if result.gamma_c is not None:
        parts.append(f"γ_c = {result.gamma_c:.2f} mN/m")
    if result.r2 is not None:
        parts.append(f"R² = {result.r2:.4f}")
    return "，".join(parts)


class CustomLiquidDialog(QDialog):
    """添加自定义液体到参数库。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加自定义液体")
        form = QFormLayout(self)
        self._edit_name = QLineEdit()
        self._spin_total = QDoubleSpinBox()
        self._spin_total.setRange(0.001, 1000)
        self._spin_total.setDecimals(3)
        self._spin_d = QDoubleSpinBox()
        self._spin_d.setRange(0, 1000)
        self._spin_d.setDecimals(3)
        self._spin_p = QDoubleSpinBox()
        self._spin_p.setRange(0, 1000)
        self._spin_p.setDecimals(3)
        form.addRow("液体名称：", self._edit_name)
        form.addRow("总表面张力 γ_L(mN/m)：", self._spin_total)
        form.addRow("色散分量 γ^d(mN/m)：", self._spin_d)
        form.addRow("极性分量 γ^p(mN/m)：", self._spin_p)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def name(self) -> str:
        return self._edit_name.text().strip()

    def gamma_total(self) -> float:
        return self._spin_total.value()

    def gamma_d(self) -> float:
        return self._spin_d.value()

    def gamma_p(self) -> float:
        return self._spin_p.value()
