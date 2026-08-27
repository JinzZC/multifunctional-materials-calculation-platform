"""可复用的工作表、表头与列映射设置对话框。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from ..fileio.importer import ImportFileError, list_sheet_names, read_table
from . import prefs


class ImportSettingsDialog(QDialog):
    """配置一个文件的工作表、表头行、字段映射和默认强力单位。"""

    def __init__(self, path, namespace: str, fields: list[tuple[str, str]],
                 header_aliases=(), show_force_unit: bool = False, parent=None):
        super().__init__(parent)
        self._path = Path(path)
        self._namespace = namespace
        self._fields = fields
        self._header_aliases = tuple(header_aliases)
        self._show_force_unit = show_force_unit
        self._combos: dict[str, QComboBox] = {}
        self.setWindowTitle("导入设置与字段映射")
        self.resize(680, 620)
        self._build_ui()
        self._apply_saved_rule(prefs.import_rule(namespace))
        self._reload_columns()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        file_label = QLabel(f"文件：{self._path.name}")
        file_label.setToolTip(str(self._path))
        root.addWidget(file_label)
        form = QFormLayout()
        self._sheet = QComboBox()
        sheets = list_sheet_names(self._path)
        if sheets:
            self._sheet.addItems(sheets)
        else:
            self._sheet.addItem("文本文件（无工作表）", None)
            self._sheet.setEnabled(False)
        form.addRow("工作表：", self._sheet)

        header_row = QHBoxLayout()
        self._auto_header = QCheckBox("自动识别")
        self._auto_header.setChecked(True)
        self._header_spin = QSpinBox()
        self._header_spin.setRange(1, 10000)
        self._header_spin.setValue(1)
        self._header_spin.setEnabled(False)
        header_row.addWidget(self._auto_header)
        header_row.addWidget(QLabel("手动行号："))
        header_row.addWidget(self._header_spin)
        header_row.addStretch(1)
        form.addRow("表头位置：", header_row)

        self._unit = QComboBox()
        self._unit.addItem("根据列名识别，无法识别时用 cN", None)
        for unit in ("cN", "N", "mN"):
            self._unit.addItem(unit, unit)
        if self._show_force_unit:
            form.addRow("默认强力单位：", self._unit)
        root.addLayout(form)

        tip = QLabel(
            "列映射留在“自动匹配”即可使用内置别名；只有仪器表头无法自动识别时才需指定。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #526579;")
        root.addWidget(tip)
        self._mapping = QTableWidget(len(self._fields), 2)
        self._mapping.setHorizontalHeaderLabels(["目标字段", "源文件列"])
        self._mapping.verticalHeader().setVisible(False)
        self._mapping.setEditTriggers(QTableWidget.NoEditTriggers)
        self._mapping.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._mapping.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for row, (key, label) in enumerate(self._fields):
            self._mapping.setItem(row, 0, QTableWidgetItem(label))
            combo = QComboBox()
            combo.addItem("自动匹配", "")
            self._mapping.setCellWidget(row, 1, combo)
            self._combos[key] = combo
        root.addWidget(self._mapping, 1)

        rule_row = QHBoxLayout()
        self._save_rule = QCheckBox("保存为此类文件的默认导入规则")
        clear = QPushButton("清除已保存规则")
        clear.clicked.connect(self._clear_saved)
        reload_button = QPushButton("按当前设置重新读取列")
        reload_button.clicked.connect(self._reload_columns)
        rule_row.addWidget(self._save_rule)
        rule_row.addStretch(1)
        rule_row.addWidget(clear)
        rule_row.addWidget(reload_button)
        root.addLayout(rule_row)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_checked)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._auto_header.toggled.connect(self._header_spin.setDisabled)
        self._sheet.currentIndexChanged.connect(self._reload_columns)

    def _current_sheet(self):
        return self._sheet.currentText() if self._sheet.isEnabled() else 0

    def _current_header(self):
        return "auto" if self._auto_header.isChecked() else self._header_spin.value()

    def _reload_columns(self, *_args) -> None:
        selected = {key: combo.currentData() for key, combo in self._combos.items()}
        try:
            frame = read_table(
                self._path, sheet_name=self._current_sheet(),
                header_row=self._current_header(), header_aliases=self._header_aliases)
        except Exception as exc:
            self._status.setText(f"读取失败：{exc}")
            self._status.setStyleSheet("color: #A61B1B;")
            return
        columns = [str(column) for column in frame.columns]
        for key, combo in self._combos.items():
            choice = selected.get(key, "")
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("自动匹配", "")
            for column in columns:
                combo.addItem(column, column)
            index = combo.findData(choice)
            combo.setCurrentIndex(max(index, 0))
            combo.blockSignals(False)
        self._status.setText(
            f"识别到表头位于第 {frame.attrs.get('header_row', 1)} 行，共 {len(columns)} 列；"
            f"数据预览 {min(len(frame), 20)} / {len(frame)} 行。")
        self._status.setStyleSheet("color: #1F6B45;")
        self._restore_pending_mapping()

    def _rule(self) -> dict:
        return {
            "sheet_name": self._current_sheet(),
            "header_row": self._current_header(),
            "column_mapping": {
                key: combo.currentData() for key, combo in self._combos.items()
                if combo.currentData()
            },
            "default_force_unit": self._unit.currentData() if self._show_force_unit else None,
        }

    def _apply_saved_rule(self, rule: dict) -> None:
        if not rule:
            return
        sheet = rule.get("sheet_name")
        index = self._sheet.findText(str(sheet))
        if index >= 0:
            self._sheet.setCurrentIndex(index)
        header = rule.get("header_row", "auto")
        self._auto_header.setChecked(header in (None, "auto"))
        if isinstance(header, int):
            self._header_spin.setValue(header)
        self._unit.setCurrentIndex(max(self._unit.findData(rule.get("default_force_unit")), 0))
        # 列选项在 _reload_columns 后才存在，暂存以便恢复。
        self._pending_mapping = dict(rule.get("column_mapping") or {})

    def _restore_pending_mapping(self) -> None:
        for key, source in getattr(self, "_pending_mapping", {}).items():
            combo = self._combos.get(key)
            if combo is not None:
                index = combo.findData(source)
                if index >= 0:
                    combo.setCurrentIndex(index)
        self._pending_mapping = {}

    def _accept_checked(self) -> None:
        self._restore_pending_mapping()
        rule = self._rule()
        # 同一源列映射给多个目标通常是误操作，提前阻止。
        mapped = list(rule["column_mapping"].values())
        if len(mapped) != len(set(mapped)):
            QMessageBox.warning(self, "映射冲突", "同一个源文件列不能同时映射给多个目标字段。")
            return
        if self._save_rule.isChecked():
            prefs.set_import_rule(self._namespace, rule)
        self.accept()

    def _clear_saved(self) -> None:
        prefs.clear_import_rule(self._namespace)
        self._save_rule.setChecked(False)
        QMessageBox.information(self, "已清除", "该数据类型保存的默认导入规则已清除。")

    def settings(self) -> dict:
        self._restore_pending_mapping()
        return self._rule()
