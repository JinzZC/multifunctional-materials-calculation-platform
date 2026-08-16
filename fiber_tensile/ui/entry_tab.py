"""Tab1 数据录入：参数录入、强度实时预览、当前批次表格、保存入库。

模式单选按钮与维度输入框（直径/线密度）由计算模式注册表（core/modes.py）动态生成，
新增模式无需改本页代码。
"""

from __future__ import annotations

import logging
import os
import sqlite3

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateEdit, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QRadioButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.models import Batch, Sample
from ..core.modes import MODES, get_mode_spec
from ..core.units import force_to_cn
from ..data.repository import add_samples, create_batch
from ..fileio.template import generate_template
from . import prefs
from .dialogs import ImportWizardDialog
from .widgets import DateEditWithToday

logger = logging.getLogger(__name__)


class EntryTab(QWidget):
    """数据录入页。saved 在保存成功后发出批次 id；data_changed 在未保存数据变化时发出。"""

    saved = Signal(int)
    data_changed = Signal()

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._pending: list[Sample] = []
        self._counter = 1                 # 自动编号
        self._build_ui()
        self._connect_signals()
        self._on_mode_changed()

    # ---- UI 构建 ----

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ===== 左侧参数区 =====
        left_widget = QWidget()
        left = QVBoxLayout(left_widget)
        left.setContentsMargins(0, 0, 0, 0)

        mode_box = QGroupBox("计算模式")
        mode_layout = QHBoxLayout(mode_box)
        self._radio_modes: dict[str, QRadioButton] = {}
        for i, (key, spec) in enumerate(MODES.items()):
            radio = QRadioButton(spec.label)
            radio.setChecked(i == 0)
            self._radio_modes[key] = radio
            mode_layout.addWidget(radio)
        left.addWidget(mode_box)

        batch_box = QGroupBox("批次信息")
        form = QFormLayout(batch_box)
        self._edit_batch_name = QLineEdit()
        self._edit_batch_name.setPlaceholderText("必填，如：碳纤维-A-20260814")
        self._edit_fiber_type = QLineEdit()
        self._edit_fiber_type.setPlaceholderText("如：T300 碳纤维")
        self._spin_density = QDoubleSpinBox()
        self._spin_density.setRange(0, 10.0)
        self._spin_density.setDecimals(4)
        self._spin_density.setSpecialValueText("不填")
        self._edit_remark = QLineEdit()
        form.addRow("批次名称：", self._edit_batch_name)
        form.addRow("纤维类型：", self._edit_fiber_type)
        form.addRow("密度(g/cm³)：", self._spin_density)
        form.addRow("备注：", self._edit_remark)
        left.addWidget(batch_box)

        sample_box = QGroupBox("试样参数（单根纤维）")
        form2 = QFormLayout(sample_box)
        self._spin_force = QDoubleSpinBox()
        self._spin_force.setRange(0.0001, 1e6)
        self._spin_force.setDecimals(4)
        self._spin_force.setValue(10.0)
        self._combo_unit = QComboBox()
        self._combo_unit.addItems(["cN", "N", "mN"])
        self._combo_unit.setCurrentText(prefs.default_force_unit())
        force_row = QHBoxLayout()
        force_row.addWidget(self._spin_force, 1)
        force_row.addWidget(self._combo_unit)
        # 维度输入框：标签与默认值随模式变化（由注册表驱动）
        self._lbl_dim = QLabel()
        self._spin_dim = QDoubleSpinBox()
        self._spin_dim.setRange(0.0001, 1e6)
        self._spin_dim.setDecimals(4)
        self._date_test = DateEditWithToday()
        form2.addRow("断裂强力：", force_row)
        form2.addRow(self._lbl_dim, self._spin_dim)
        form2.addRow("测试日期：", self._date_test)
        left.addWidget(sample_box)

        self._lbl_preview = QLabel()
        self._lbl_preview.setWordWrap(True)
        self._lbl_preview.setAlignment(Qt.AlignCenter)
        self._lbl_preview.setStyleSheet(
            "font-weight: bold; color: #1F4E79; padding: 8px;"
            "background: #F2F6FB; border: 1px solid #C9D7E8; border-radius: 4px;")
        left.addWidget(self._lbl_preview)

        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("添加数据")
        self._btn_import = QPushButton("批量导入…")
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_import)
        left.addLayout(btn_row)
        btn_row2 = QHBoxLayout()
        self._btn_template = QPushButton("下载导入模板")
        self._btn_clear = QPushButton("清空表格")
        btn_row2.addWidget(self._btn_template)
        btn_row2.addWidget(self._btn_clear)
        left.addLayout(btn_row2)
        left.addStretch(1)

        splitter.addWidget(left_widget)

        # ===== 右侧表格区 =====
        right_widget = QWidget()
        right = QVBoxLayout(right_widget)
        right.setContentsMargins(0, 0, 0, 0)
        right.addWidget(QLabel("当前批次数据（未保存）"))
        self._table = QTableWidget(0, 7)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        right.addWidget(self._table, 1)
        bottom = QHBoxLayout()
        self._btn_delete_row = QPushButton("删除选中行")
        self._btn_save = QPushButton("保存到数据库")
        self._btn_save.setStyleSheet("font-weight: bold;")
        self._btn_save.setToolTip("保存到数据库（Ctrl+S）")
        bottom.addWidget(self._btn_delete_row)
        bottom.addStretch(1)
        bottom.addWidget(self._btn_save)
        right.addLayout(bottom)
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([430, 700])
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(splitter)

    def _connect_signals(self) -> None:
        for radio in self._radio_modes.values():
            radio.toggled.connect(self._on_mode_changed)
        self._spin_force.valueChanged.connect(self._update_preview)
        self._combo_unit.currentTextChanged.connect(self._update_preview)
        self._combo_unit.currentTextChanged.connect(prefs.set_default_force_unit)
        self._spin_dim.valueChanged.connect(self._update_preview)
        self._spin_density.valueChanged.connect(self._update_preview)
        self._btn_add.clicked.connect(self._add_sample)
        self._btn_import.clicked.connect(self._import_file)
        self._btn_template.clicked.connect(self._download_template)
        self._btn_clear.clicked.connect(self._clear_table)
        self._btn_delete_row.clicked.connect(self._delete_selected_rows)
        self._btn_save.clicked.connect(self._save)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._save)

    # ---- 模式与预览 ----

    def _mode(self) -> str:
        for key, radio in self._radio_modes.items():
            if radio.isChecked():
                return key
        return next(iter(MODES))

    def _spec(self):
        return get_mode_spec(self._mode())

    def _on_mode_changed(self, *args) -> None:   # toggled 信号带 bool 参数，此处忽略
        spec = self._spec()
        self._lbl_dim.setText(f"{spec.dim_label}：")
        # 仅当当前值是上一模式的默认值时切换到新模式默认值，
        # 保留用户手动输入的数值不被模式切换重置
        if not hasattr(self, "_last_dim_default"):
            self._last_dim_default = spec.dim_default
        if abs(self._spin_dim.value() - self._last_dim_default) < 1e-9:
            self._spin_dim.setValue(spec.dim_default)
        self._last_dim_default = spec.dim_default
        self._update_table_headers()
        self._update_preview()

    def _preview_payload(self) -> tuple:
        """返回 (spec, force_cn, dim, density)。"""
        spec = self._spec()
        force_cn = force_to_cn(self._spin_force.value(), self._combo_unit.currentText())
        dim = self._spin_dim.value()
        density = self._spin_density.value() or None
        return spec, force_cn, dim, density

    def _update_preview(self) -> None:
        try:
            spec, force_cn, dim, density = self._preview_payload()
            strength, strength_mpa = spec.compute(force_cn, dim, density)
        except ValueError:
            self._lbl_preview.setText("输入无效，请检查数值")
            return
        if not spec.uses_density:
            text = f"σ = {strength:,.2f} {spec.strength_unit}（{strength / 1000:.4f} GPa）"
        else:
            text = f"断裂强度 = {strength:,.4f} {spec.strength_unit}"
            if strength_mpa is not None:
                text += f"（≈ {strength_mpa:,.2f} MPa）"
        self._lbl_preview.setText(text)

    def _update_table_headers(self) -> None:
        spec = self._spec()
        headers = ["编号", "断裂强力", spec.dim_label,
                   "密度(g/cm³)", f"强度({spec.strength_unit})", "备注", "测试日期"]
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setColumnWidth(0, 60)
        self._table.setColumnWidth(1, 90)
        self._table.setColumnWidth(2, 100)
        self._table.setColumnWidth(3, 90)
        self._table.setColumnWidth(4, 110)

    # ---- 表格操作 ----

    def _append_table_row(self, sample: Sample, density: float | None) -> None:
        spec = self._spec()
        r = self._table.rowCount()
        self._table.insertRow(r)
        dim = getattr(sample, spec.dim_field)
        values = [
            sample.sample_no or "",
            f"{sample.breaking_force:g} {sample.force_unit}",
            f"{dim:g}",
            f"{density:g}" if density is not None else "—",
            f"{sample.strength:,.2f}" if sample.strength is not None else "—",
            sample.remark or "",
            sample.test_date or "",
        ]
        for c, v in enumerate(values):
            item = QTableWidgetItem(v)
            if c in (1, 2, 3, 4):
                item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(r, c, item)

    def _delete_selected_rows(self) -> None:
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._table.removeRow(r)
            del self._pending[r]
        if rows:
            self.data_changed.emit()

    def _clear_table(self) -> None:
        if self._table.rowCount() == 0:
            return
        if QMessageBox.question(self, "确认", f"确定清空当前未保存的 {self._table.rowCount()} 条数据？") \
                != QMessageBox.Yes:
            return
        self._table.setRowCount(0)
        self._pending.clear()
        self.data_changed.emit()

    # ---- 添加 / 导入 / 保存 ----

    def _add_sample(self) -> None:
        spec, force_cn, dim, density = self._preview_payload()
        try:
            strength, strength_mpa = spec.compute(force_cn, dim, density)
        except ValueError as e:
            QMessageBox.warning(self, "无法添加", str(e))
            return
        sample = Sample(
            breaking_force=self._spin_force.value(),
            force_unit=self._combo_unit.currentText(),
            sample_no=str(self._counter),
            remark=self._edit_remark.text().strip() or None,
            test_date=self._date_test.date().toString("yyyy-MM-dd"),
            strength=strength,
            strength_mpa=strength_mpa,
            **{spec.dim_field: dim},
        )
        self._pending.append(sample)
        self._counter += 1
        self._append_table_row(sample, density)
        self.data_changed.emit()
        self._spin_force.setFocus()    # 焦点回到强力输入，便于连续录入

    def _import_file(self) -> None:
        result = ImportWizardDialog.run(self._conn, self)
        if result is None:
            return
        try:
            if result["append_batch_id"] is not None:
                n = add_samples(self._conn, result["append_batch_id"], result["samples"])
                logger.info(f"导入追加 {n} 条数据到批次 id={result['append_batch_id']}")
                QMessageBox.information(self, "导入完成", f"已追加 {n} 条数据到现有批次。")
            else:
                batch = Batch(
                    batch_name=result["batch_name"],
                    mode=result["mode"],
                    density=result["density"],
                )
                bid = create_batch(self._conn, batch)
                n = add_samples(self._conn, bid, result["samples"])
                self.saved.emit(bid)
                logger.info(f"导入新建批次「{batch.batch_name}」(id={bid})，{n} 条数据")
                QMessageBox.information(
                    self, "导入完成", f"已新建批次「{batch.batch_name}」并导入 {n} 条数据。")
        except ValueError as e:
            logger.warning(f"导入失败：{e}")
            QMessageBox.warning(self, "导入失败", str(e))
            return
        self.data_changed.emit()

    def _save(self) -> None:
        name = self._edit_batch_name.text().strip()
        if not name:
            QMessageBox.warning(self, "无法保存", "请先填写批次名称。")
            return
        if not self._pending:
            QMessageBox.warning(self, "无法保存", "当前没有数据，请先添加或导入数据。")
            return
        density = self._spin_density.value() or None
        batch = Batch(
            batch_name=name,
            mode=self._mode(),
            fiber_type=self._edit_fiber_type.text().strip() or None,
            density=density,
            remark=self._edit_remark.text().strip() or None,
        )
        try:
            bid = create_batch(self._conn, batch)
            n = add_samples(self._conn, bid, self._pending)
        except ValueError as e:
            logger.warning(f"保存失败：{e}")
            QMessageBox.warning(self, "保存失败", str(e))
            return
        self._table.setRowCount(0)
        self._pending.clear()
        self.saved.emit(bid)
        self.data_changed.emit()
        logger.info(f"已保存 {n} 条数据到批次「{name}」(id={bid})")
        QMessageBox.information(self, "保存成功", f"已保存 {n} 条数据到批次「{name}」。")

    def _download_template(self) -> None:
        start = prefs.last_dir()
        default_path = os.path.join(start, "纤维强度导入模板.xlsx") if start \
            else "纤维强度导入模板.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存导入模板", default_path, "Excel 文件 (*.xlsx)")
        if not path:
            return
        prefs.set_last_dir(os.path.dirname(path))
        generate_template(path)
        QMessageBox.information(self, "完成", f"模板已保存到：\n{path}")

    # ---- 供其他 Tab 使用 ----

    def current_unsaved(self) -> tuple:
        """返回未保存数据的 (mode, density, samples)。"""
        return self._mode(), (self._spin_density.value() or None), list(self._pending)
