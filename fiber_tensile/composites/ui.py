"""复合材料基础计算模块页：单层板工程常数（混合法则）+ 纤维体积分数/孔隙率。"""

from __future__ import annotations

import logging
import os
import sqlite3

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QDateEdit, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QRadioButton, QScrollArea, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from ..ui import prefs
from ..ui.richtext import HtmlHeaderView, equation_line_html, to_rich
from .core import compute_rom, compute_vf_acid, compute_vf_density
from .exporters import export_excel_report, export_pdf_report
from .repository import (
    create_rom, create_vf, delete_cm_calc, get_cm_calc, list_cm_calcs,
)

logger = logging.getLogger(__name__)

_TYPE_LABELS = {"rom": "混合法则", "volume_fraction": "体积分数"}

_ROM_EQUATIONS = (
    "E_1 = E_f×V_f + E_m×(1−V_f)\n"
    "E_2 = ⟨E_f×E_m|V_f×E_m + (1−V_f)×E_f⟩\n"
    "G_12 = ⟨G_f×G_m|V_f×G_m + (1−V_f)×G_f⟩\n"
    "ν_12 = ν_f×V_f + ν_m×(1−V_f)\n"
    "ρ_c = ρ_f×V_f + ρ_m×(1−V_f)")
_ROM_LEGEND = ('<span style="color:#888; font-size:8.5pt;">符号说明：下标 f＝纤维、'
               "m＝基体（树脂）、c＝复合材料；E₁ 纵向模量、E₂ 横向模量、G₁₂ 剪切模量、"
               "ν₁₂ 主泊松比；V_f 纤维体积分数；ρ 密度(g/cm³)；E、G 单位 GPa</span>")

_VF_EQUATIONS = {
    "density": ("V_f = ⟨ρ_c − ρ_m|ρ_f − ρ_m⟩\n"
                "V_m = 1 − V_f"),
    "acid": ("V_f = ⟨w_f/ρ_f|w_f/ρ_f + w_m/ρ_m⟩\n"
             "V_v = 1 − ρ_c×(w_f/ρ_f + w_m/ρ_m)\n"
             "V_m = 1 − V_f − V_v"),
}
_VF_LEGEND = ('<span style="color:#888; font-size:8.5pt;">符号说明：V_f 纤维体积分数、'
              "V_m 基体体积分数、V_v 孔隙率；ρ 密度(g/cm³)，下标 f/m/c 同左；"
              "w_f、w_m 为纤维/树脂质量分数（酸解法）</span>")


def _spin(lo, hi, value, decimals=3):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setValue(value)
    return s


class CompositesTab(QWidget):
    """复合材料基础计算模块页。"""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._build_ui()
        self._connect_signals()
        self._on_vf_method_changed()
        self.refresh_history()

    # ---- UI ----

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_rom_tab(), "单层板工程常数（混合法则）")
        tabs.addTab(self._build_vf_tab(), "纤维体积分数 / 孔隙率")
        root.addWidget(tabs, 3)

        root.addWidget(QLabel("历史记录："))
        self._history = QTableWidget(0, 11)
        # 两行式表头：中文含义 + 符号，列宽紧凑，全部列无需横向滚动即可见
        self._history.setHorizontalHeaderLabels(
            [to_rich(h) for h in (
                "类型", "样品名称", "纵向模量<br>E_1(GPa)", "横向模量<br>E_2(GPa)",
                "剪切模量<br>G_12(GPa)", "主泊松比<br>ν_12", "复合材料密度<br>ρ_c(g/cm³)",
                "纤维体积分数<br>V_f", "基体体积分数<br>V_m", "孔隙率<br>V_v",
                "测试日期")])
        self._history.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._history.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._history.setSelectionMode(QAbstractItemView.SingleSelection)
        self._history.verticalHeader().setVisible(False)
        self._history.setHorizontalHeader(HtmlHeaderView(Qt.Horizontal, self._history))
        hh = self._history.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        self._history.setColumnWidth(0, 100)
        self._history.setColumnWidth(1, 160)
        hh.resizeSections(QHeaderView.ResizeToContents)   # 列宽按表头内容自适应
        root.addWidget(self._history, 2)

        h_buttons = QHBoxLayout()
        self._btn_delete = QPushButton("删除记录")
        self._btn_export_xlsx = QPushButton("导出 Excel 报告…")
        self._btn_export_pdf = QPushButton("导出 PDF 报告…")
        for b in (self._btn_delete, self._btn_export_xlsx, self._btn_export_pdf):
            h_buttons.addWidget(b)
        h_buttons.addStretch(1)
        root.addLayout(h_buttons)

    def _build_rom_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)

        left = QWidget()
        l = QVBoxLayout(left)
        l.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("输入参数")
        form = QFormLayout(box)
        self._rom_ef = _spin(1, 2000, 230.0)
        self._rom_em = _spin(0.1, 100, 3.5)
        self._rom_gf = _spin(1, 1000, 20.0)
        self._rom_gm = _spin(0.05, 50, 1.3)
        self._rom_nuf = _spin(0.01, 0.49, 0.20, 4)
        self._rom_num = _spin(0.01, 0.49, 0.35, 4)
        self._rom_rhof = _spin(0.1, 10, 1.76)
        self._rom_rhom = _spin(0.1, 10, 1.20)
        self._rom_vf = _spin(0.01, 0.99, 0.60, 4)
        self._edit_sample_name = QLineEdit()
        self._edit_sample_name.setPlaceholderText("必填，如：T300/环氧-0.6")
        self._edit_remark = QLineEdit()
        self._date_test = QDateEdit(QDate.currentDate())
        self._date_test.setCalendarPopup(True)
        self._date_test.setDisplayFormat("yyyy-MM-dd")
        form.addRow("样品名称：", self._edit_sample_name)
        form.addRow("纤维模量 E_f(GPa)：", self._rom_ef)
        form.addRow("树脂模量 E_m(GPa)：", self._rom_em)
        form.addRow("纤维剪切模量 G_f(GPa)：", self._rom_gf)
        form.addRow("树脂剪切模量 G_m(GPa)：", self._rom_gm)
        form.addRow("纤维泊松比 ν_f：", self._rom_nuf)
        form.addRow("树脂泊松比 ν_m：", self._rom_num)
        form.addRow("纤维密度 ρ_f(g/cm³)：", self._rom_rhof)
        form.addRow("树脂密度 ρ_m(g/cm³)：", self._rom_rhom)
        form.addRow("纤维体积分数 V_f：", self._rom_vf)
        form.addRow("备注：", self._edit_remark)
        form.addRow("测试日期：", self._date_test)
        l.addWidget(box)
        l.addStretch(1)
        self._btn_save_rom = QPushButton("计算并保存")
        self._btn_save_rom.setStyleSheet("font-weight: bold;")
        l.addWidget(self._btn_save_rom)
        split.addWidget(left)

        right = QWidget()
        r = QVBoxLayout(right)
        r.setContentsMargins(0, 0, 0, 0)
        eq_box = QGroupBox("计算公式")
        eq_lay = QVBoxLayout(eq_box)
        self._rom_equations = QLabel()
        self._rom_equations.setWordWrap(True)
        self._rom_equations.setText(
            "<br>".join(equation_line_html(line) for line in _ROM_EQUATIONS.split("\n"))
            + "<br>" + _ROM_LEGEND)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._rom_equations)
        scroll.setMinimumHeight(150)
        eq_lay.addWidget(scroll)
        r.addWidget(eq_box)
        res_box = QGroupBox("计算结果")
        res_lay = QVBoxLayout(res_box)
        self._rom_lbl = QLabel("点击「计算并保存」后显示结果")
        self._rom_lbl.setWordWrap(True)
        res_lay.addWidget(self._rom_lbl)
        self._txt_process = QTextEdit()
        self._txt_process.setReadOnly(True)
        self._txt_process.setPlaceholderText("在此显示逐步计算过程")
        self._txt_process.setStyleSheet(
            "font-family: Consolas, 'Microsoft YaHei'; font-size: 9.5pt;")
        res_lay.addWidget(self._txt_process, 1)
        r.addWidget(res_box, 1)
        split.addWidget(right)
        split.setSizes([420, 640])
        lay.addWidget(split)
        return page

    def _build_vf_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)

        left = QWidget()
        l = QVBoxLayout(left)
        l.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("输入参数")
        form = QFormLayout(box)
        self._vf_radio_density = QRadioButton("密度法（测复合材料密度）")
        self._vf_radio_acid = QRadioButton("酸解法（测纤维质量分数）")
        self._vf_radio_density.setChecked(True)
        method_row = QHBoxLayout()
        method_row.addWidget(self._vf_radio_density)
        method_row.addWidget(self._vf_radio_acid)
        form.addRow("计算方法：", method_row)
        self._vf_sample = QLineEdit()
        self._vf_sample.setPlaceholderText("必填，如：CFRP-板1#")
        self._vf_rhoc = _spin(0.1, 10, 1.55)
        self._vf_rhof = _spin(0.1, 10, 1.76)
        self._vf_rhom = _spin(0.1, 10, 1.20)
        self._vf_wf = _spin(0.01, 0.99, 0.65, 4)
        self._vf_remark = QLineEdit()
        self._vf_date = QDateEdit(QDate.currentDate())
        self._vf_date.setCalendarPopup(True)
        self._vf_date.setDisplayFormat("yyyy-MM-dd")
        form.addRow("样品名称：", self._vf_sample)
        self._lbl_rhoc = QLabel("复合材料密度 ρ_c(g/cm³)：")
        form.addRow(self._lbl_rhoc, self._vf_rhoc)
        form.addRow("纤维密度 ρ_f(g/cm³)：", self._vf_rhof)
        form.addRow("树脂密度 ρ_m(g/cm³)：", self._vf_rhom)
        self._lbl_wf = QLabel("纤维质量分数 w_f：")
        form.addRow(self._lbl_wf, self._vf_wf)
        form.addRow("备注：", self._vf_remark)
        form.addRow("测试日期：", self._vf_date)
        l.addWidget(box)
        l.addStretch(1)
        self._btn_save_vf = QPushButton("计算并保存")
        self._btn_save_vf.setStyleSheet("font-weight: bold;")
        l.addWidget(self._btn_save_vf)
        split.addWidget(left)

        right = QWidget()
        r = QVBoxLayout(right)
        r.setContentsMargins(0, 0, 0, 0)
        eq_box = QGroupBox("计算公式")
        eq_lay = QVBoxLayout(eq_box)
        self._vf_equations = QLabel()
        self._vf_equations.setWordWrap(True)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._vf_equations)
        scroll.setMinimumHeight(130)
        eq_lay.addWidget(scroll)
        r.addWidget(eq_box)
        res_box = QGroupBox("计算结果")
        res_lay = QVBoxLayout(res_box)
        self._vf_lbl = QLabel("点击「计算并保存」后显示结果")
        self._vf_lbl.setWordWrap(True)
        res_lay.addWidget(self._vf_lbl)
        self._txt_process_vf = QTextEdit()
        self._txt_process_vf.setReadOnly(True)
        self._txt_process_vf.setPlaceholderText("在此显示逐步计算过程")
        self._txt_process_vf.setStyleSheet(
            "font-family: Consolas, 'Microsoft YaHei'; font-size: 9.5pt;")
        res_lay.addWidget(self._txt_process_vf, 1)
        r.addWidget(res_box, 1)
        split.addWidget(right)
        split.setSizes([420, 640])
        lay.addWidget(split)
        return page

    def _connect_signals(self) -> None:
        self._btn_save_rom.clicked.connect(self._save_rom)
        self._btn_save_vf.clicked.connect(self._save_vf)
        self._vf_radio_density.toggled.connect(self._on_vf_method_changed)
        self._btn_delete.clicked.connect(self._delete_history)
        self._btn_export_xlsx.clicked.connect(lambda: self._export_selected("xlsx"))
        self._btn_export_pdf.clicked.connect(lambda: self._export_selected("pdf"))

    def _on_vf_method_changed(self, *args) -> None:
        is_density = self._vf_radio_density.isChecked()
        # 质量分数仅酸解法需要；复合材料密度两种方法都需要
        self._lbl_wf.setVisible(not is_density)
        self._vf_wf.setVisible(not is_density)
        eq = _VF_EQUATIONS["density" if is_density else "acid"]
        self._vf_equations.setText(
            "<br>".join(equation_line_html(line) for line in eq.split("\n"))
            + "<br>" + _VF_LEGEND)

    # ---- 计算保存 ----

    def _save_rom(self) -> None:
        name = self._edit_sample_name.text().strip()
        if not name:
            QMessageBox.warning(self, "无法保存", "请先填写样品名称。")
            return
        inputs = {"E_f(GPa)": self._rom_ef.value(), "E_m(GPa)": self._rom_em.value(),
                  "G_f(GPa)": self._rom_gf.value(), "G_m(GPa)": self._rom_gm.value(),
                  "ν_f": self._rom_nuf.value(), "ν_m": self._rom_num.value(),
                  "ρ_f(g/cm³)": self._rom_rhof.value(), "ρ_m(g/cm³)": self._rom_rhom.value(),
                  "V_f": self._rom_vf.value()}
        try:
            result = compute_rom(inputs["E_f(GPa)"], inputs["E_m(GPa)"],
                                 inputs["G_f(GPa)"], inputs["G_m(GPa)"],
                                 inputs["ν_f"], inputs["ν_m"],
                                 inputs["ρ_f(g/cm³)"], inputs["ρ_m(g/cm³)"],
                                 inputs["V_f"])
        except ValueError as e:
            QMessageBox.warning(self, "计算失败", str(e))
            return
        self._rom_lbl.setText(to_rich(
            f"纵向模量 E_1 = {result.e1_gpa:.2f} GPa　"
            f"横向模量 E_2 = {result.e2_gpa:.2f} GPa　"
            f"剪切模量 G_12 = {result.g12_gpa:.2f} GPa　"
            f"主泊松比 ν_12 = {result.nu12:.4f}　"
            f"复合材料密度 ρ_c = {result.rho_gcm3:.3f} g/cm³"))
        self._txt_process.setHtml("<br>".join(result.steps))
        mid = create_rom(self._conn, name, inputs, result,
                         remark=self._edit_remark.text().strip() or None,
                         test_date=self._date_test.date().toString("yyyy-MM-dd"))
        logger.info(f"已保存混合法则计算「{name}」(id={mid})")
        self.refresh_history()
        QMessageBox.information(self, "保存成功",
                                f"样品「{name}」已保存。\nE₁ = {result.e1_gpa:.2f} GPa，"
                                f"E₂ = {result.e2_gpa:.2f} GPa")

    def _save_vf(self) -> None:
        name = self._vf_sample.text().strip()
        if not name:
            QMessageBox.warning(self, "无法保存", "请先填写样品名称。")
            return
        if self._vf_radio_density.isChecked():
            inputs = {"ρ_c(g/cm³)": self._vf_rhoc.value(),
                      "ρ_f(g/cm³)": self._vf_rhof.value(),
                      "ρ_m(g/cm³)": self._vf_rhom.value()}
            try:
                result = compute_vf_density(inputs["ρ_c(g/cm³)"],
                                            inputs["ρ_f(g/cm³)"],
                                            inputs["ρ_m(g/cm³)"])
            except ValueError as e:
                QMessageBox.warning(self, "计算失败", str(e))
                return
            self._vf_lbl.setText(to_rich(
                f"纤维体积分数 V_f = {result.vf:.4f}　"
                f"基体体积分数 V_m = {result.vm:.4f}"))
            self._txt_process_vf.setHtml("<br>".join(result.steps))
            mid = create_vf(self._conn, name, inputs, result,
                            remark=self._vf_remark.text().strip() or None,
                            test_date=self._vf_date.date().toString("yyyy-MM-dd"))
        else:
            inputs = {"w_f": self._vf_wf.value(),
                      "ρ_f(g/cm³)": self._vf_rhof.value(),
                      "ρ_m(g/cm³)": self._vf_rhom.value(),
                      "ρ_c(g/cm³)": self._vf_rhoc.value()}
            try:
                result = compute_vf_acid(inputs["w_f"], inputs["ρ_f(g/cm³)"],
                                         inputs["ρ_m(g/cm³)"],
                                         inputs["ρ_c(g/cm³)"])
            except ValueError as e:
                QMessageBox.warning(self, "计算失败", str(e))
                return
            # 孔隙率突出显示：百分比 + 红色加粗
            self._vf_lbl.setText(to_rich(
                f"纤维体积分数 V_f = {result.vf:.4f}　"
                f"基体体积分数 V_m = {result.vm:.4f}　"
                f"孔隙率 V_v = <span style=\"color:#C0504D; font-weight:bold;\">"
                f"{result.vv * 100:.2f}%</span>"))
            self._txt_process_vf.setHtml("<br>".join(result.steps))
            mid = create_vf(self._conn, name, inputs, result,
                            remark=self._vf_remark.text().strip() or None,
                            test_date=self._vf_date.date().toString("yyyy-MM-dd"))
        logger.info(f"已保存体积分数计算「{name}」(id={mid})")
        self.refresh_history()
        QMessageBox.information(self, "保存成功", f"样品「{name}」已保存。\n{self._vf_lbl.text()}")

    # ---- 历史 / 导出 ----

    def refresh_history(self) -> None:
        rows = list_cm_calcs(self._conn)
        self._history.setRowCount(len(rows))
        for r, row in enumerate(rows):
            vv = row["vv"]
            values = [
                _TYPE_LABELS[row["calc_type"]], row["sample_name"],
                f"{row['e1_gpa']:.2f}" if row["e1_gpa"] is not None else "—",
                f"{row['e2_gpa']:.2f}" if row["e2_gpa"] is not None else "—",
                f"{row['g12_gpa']:.2f}" if row["g12_gpa"] is not None else "—",
                f"{row['nu12']:.4f}" if row["nu12"] is not None else "—",
                f"{row['rho_gcm3']:.3f}" if row["rho_gcm3"] is not None else "—",
                f"{row['vf']:.4f}" if row["vf"] is not None else "—",
                f"{row['vm']:.4f}" if row["vm"] is not None else "—",
                # 孔隙率以百分比明确显示；非零时红色突出
                f"{vv * 100:.2f}%" if vv is not None else "—",
                row["test_date"] or "—",
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c >= 2:
                    item.setTextAlignment(Qt.AlignCenter)
                if c == 9 and vv is not None and vv > 0.0005:
                    item.setForeground(QColor("#C0504D"))
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
        if QMessageBox.question(self, "确认删除", "确定删除选中的计算记录？") \
                != QMessageBox.Yes:
            return
        delete_cm_calc(self._conn, cid)
        self.refresh_history()

    def _export_selected(self, kind: str) -> None:
        cid = self._selected_id()
        if cid is None:
            QMessageBox.information(self, "提示", "请先在历史记录中选择一条记录。")
            return
        try:
            row = get_cm_calc(self._conn, cid)
        except ValueError as e:
            QMessageBox.warning(self, "导出失败", str(e))
            return
        if row["calc_type"] == "rom":
            result = compute_rom(row["inputs"]["E_f(GPa)"], row["inputs"]["E_m(GPa)"],
                                 row["inputs"]["G_f(GPa)"], row["inputs"]["G_m(GPa)"],
                                 row["inputs"]["ν_f"], row["inputs"]["ν_m"],
                                 row["inputs"]["ρ_f(g/cm³)"], row["inputs"]["ρ_m(g/cm³)"],
                                 row["inputs"]["V_f"])
            pairs = [("纵向模量 E₁(GPa)", f"{result.e1_gpa:.2f}"),
                     ("横向模量 E₂(GPa)", f"{result.e2_gpa:.2f}"),
                     ("剪切模量 G₁₂(GPa)", f"{result.g12_gpa:.2f}"),
                     ("主泊松比 ν₁₂", f"{result.nu12:.4f}"),
                     ("密度 ρ_c(g/cm³)", f"{result.rho_gcm3:.3f}")]
        else:
            i = row["inputs"]
            if "w_f" in i:
                result = compute_vf_acid(i["w_f"], i["ρ_f(g/cm³)"],
                                         i["ρ_m(g/cm³)"], i["ρ_c(g/cm³)"])
            else:
                result = compute_vf_density(i["ρ_c(g/cm³)"], i["ρ_f(g/cm³)"],
                                            i["ρ_m(g/cm³)"])
            pairs = [("纤维体积分数 V_f", f"{result.vf:.4f}"),
                     ("基体体积分数 V_m", f"{result.vm:.4f}"),
                     ("孔隙率 V_v", f"{result.vv * 100:.3f}%"
                      if result.vv is not None else "—")]
        start = prefs.last_dir()
        default = os.path.join(start, f"{row['sample_name']}_复合材料计算.{kind}") \
            if start else f"{row['sample_name']}_复合材料计算.{kind}"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出报告", default, f"{kind.upper()} 文件 (*.{kind})")
        if not path:
            return
        prefs.set_last_dir(os.path.dirname(path))
        try:
            export_excel_report(path, row["calc_type"], row["sample_name"],
                                row["inputs"], pairs, result.steps,
                                row["remark"], row["test_date"]) \
                if kind == "xlsx" else \
                export_pdf_report(path, row["calc_type"], row["sample_name"],
                                  row["inputs"], pairs, result.steps,
                                  row["remark"], row["test_date"])
        except Exception as e:  # noqa: BLE001
            logger.warning(f"导出复合材料报告失败：{e}")
            QMessageBox.critical(self, "导出失败", str(e))
            return
        logger.info(f"已导出复合材料 {kind} 报告：{path}")
        QMessageBox.information(self, "导出成功", f"报告已保存到：\n{path}")
