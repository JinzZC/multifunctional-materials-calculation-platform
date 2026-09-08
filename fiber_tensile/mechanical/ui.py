"""Sixth navigation module: batch import, adjustable fits, comparison and history."""

import json
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from ..ui import prefs
from ..ui.import_settings import ImportSettingsDialog
from ..ui.widgets import DateEditWithToday
from .core import MODES, SOURCES, Spec, analyze
from .importer import ALIASES, FIELDS, FORCE_UNITS, read_curve
from .repository import save_entries, list_entries, load_entry, delete_entries


class ImportWorker(QThread):
    item = Signal(object)
    progress = Signal(int, str)

    def __init__(self, paths, spec, options, metadata, parent=None):
        super().__init__(parent)
        self.paths, self.spec, self.options, self.metadata = paths, spec, options, metadata

    def run(self):
        for i, path in enumerate(self.paths):
            if self.isInterruptionRequested():
                break
            try:
                x, force, origin = read_curve(path, source=self.spec.source, **self.options)
                result = analyze(x, force, self.spec)
                self.item.emit({"name": self.metadata.get("name") or Path(path).stem,
                                "x": x, "force": force, "spec": self.spec, "result": result,
                                "import": origin, "remark": self.metadata["remark"],
                                "test_date": self.metadata["test_date"]})
                status = f"成功：{Path(path).name}（{len(x)} 点）"
            except Exception as exc:
                status = f"失败：{Path(path).name} — {exc}"
            self.progress.emit(i + 1, status)


class MechanicalTab(QWidget):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._entries = []
        self._thread = None
        self._canvas = None
        self._toolbar = None
        self._loading = False
        self._dirty = False
        self._build_ui()
        self.refresh_history()

    def _build_ui(self):
        root = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        root.addWidget(split)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(270)
        scroll.setMaximumWidth(370)
        self._parameters = QWidget()
        left = QVBoxLayout(self._parameters)
        self._source = QComboBox()
        for key, name in SOURCES.items():
            self._source.addItem(name, key)
        self._section = QComboBox()
        for key, name in (("rectangle", "矩形"), ("circle", "圆形"), ("area", "直接输入面积")):
            self._section.addItem(name, key)
        self._name = QLineEdit()
        self._name.setPlaceholderText("留空使用文件名；多文件各用文件名")
        self._remark = QLineEdit()
        self._date = DateEditWithToday()
        box = QGroupBox("试样与测量方式")
        form = QFormLayout(box)
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.addRow("试验", QLabel("拉伸"))
        form.addRow("变形来源", self._source)
        form.addRow("截面", self._section)
        form.addRow("样品", self._name)
        form.addRow("日期", self._date)
        form.addRow("备注", self._remark)
        self._dims = {}
        self._dim_form = form
        defaults = Spec()
        for key, label in (("width_mm", "宽度 b (mm)"), ("thickness_mm", "厚度 h (mm)"),
                           ("diameter_mm", "直径 d (mm)"), ("area_mm2", "截面积 A (mm²)"),
                           ("gauge_mm", "标距 L₀ (mm)")):
            spin = self._spin(getattr(defaults, key), .000001, 1e6, 6)
            self._dims[key] = spin
            form.addRow(label, spin)
        left.addWidget(box)
        fit_box = QGroupBox("拟合与指定应变")
        fit = QFormLayout(fit_box)
        fit.setRowWrapPolicy(QFormLayout.WrapAllRows)
        self._fit_mode = QComboBox()
        self._fit_mode.addItem("工程应变区间 (%)", "strain")
        self._fit_mode.addItem("峰值力比例 (%)", "force")
        self._lo = self._spin(.05, 0, 100000, 5)
        self._hi = self._spin(.25, 0, 100000, 5)
        self._target = self._spin(1, 0, 100000, 5)
        fit.addRow("区间依据", self._fit_mode)
        fit.addRow("下限", self._lo)
        fit.addRow("上限", self._hi)
        fit.addRow("指定应变 (%)", self._target)
        self._fracture = QSpinBox()
        self._fracture.setRange(0, 100_000_000)
        self._fracture.setSpecialValueText("未指定")
        self._fracture.setToolTip("从1开始的原始数据点号，需人工确认；0为未指定，不自动把峰值当断裂。")
        fit.addRow("人工确认断裂点号", self._fracture)
        left.addWidget(fit_box)
        unit_box = QGroupBox("导入单位（仅影响新文件）")
        units = QFormLayout(unit_box)
        units.setRowWrapPolicy(QFormLayout.WrapAllRows)
        self._x_unit = QComboBox()
        self._force_unit = QComboBox()
        self._force_unit.addItems(list(FORCE_UNITS))
        units.addRow("变形", self._x_unit)
        units.addRow("总力", self._force_unit)
        self._decimal = QComboBox()
        self._decimal.addItem("小数点 .（无千分位）", ".")
        self._decimal.addItem("小数逗号 ,（无千分位）", ",")
        units.addRow("文本数字", self._decimal)
        left.addWidget(unit_box)
        self._hint = QLabel()
        self._hint.setWordWrap(True)
        left.addWidget(self._hint)
        self._import_button = QPushButton("批量导入文件…")
        self._mapping_button = QPushButton("自定义映射导入…")
        self._recalc_button = QPushButton("将参数应用到所选曲线")
        left.addStretch()
        scroll.setWidget(self._parameters)
        left_panel = QWidget()
        left_panel_layout = QVBoxLayout(left_panel)
        left_panel_layout.setContentsMargins(0, 0, 0, 0)
        left_panel_layout.addWidget(scroll, 1)
        for button in (self._import_button, self._mapping_button, self._recalc_button):
            left_panel_layout.addWidget(button)
        split.addWidget(left_panel)

        right = QWidget()
        layout = QVBoxLayout(right)
        self._status = QLabel("导入力–应变或力–变形数据。按 Ctrl / Shift 多选曲线进行对比。")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)
        current = QWidget()
        current_layout = QVBoxLayout(current)
        self._table = self._table_widget(["样品", "试验 / 测量", "模量(GPa)", "峰值(MPa)", "峰值应变(%)", "R²", "保存状态"])
        current_layout.addWidget(self._table)
        actions = QHBoxLayout()
        self._save_button = QPushButton("保存所选")
        self._remove_button = QPushButton("移出所选")
        self._export_buttons = []
        for button in (self._save_button, self._remove_button):
            actions.addWidget(button)
        for label, kind in (("Excel 报告…", "xlsx"), ("CSV 汇总…", "csv"), ("PDF 报告…", "pdf")):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, k=kind: self._export(k))
            actions.addWidget(button)
            self._export_buttons.append(button)
        current_layout.addLayout(actions)
        self._tabs.addTab(current, "当前曲线")
        history = QWidget()
        history_layout = QVBoxLayout(history)
        search = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("按样品或备注筛选")
        search.addWidget(self._search)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh_history)
        search.addWidget(refresh)
        history_layout.addLayout(search)
        self._history = self._table_widget(["样品", "试验", "模量(GPa)", "峰值(MPa)", "日期", "保存版本"])
        history_layout.addWidget(self._history)
        history_actions = QHBoxLayout()
        load = QPushButton("载入所选并重算 / 对比")
        delete = QPushButton("删除所选历史")
        load.clicked.connect(self._load_history)
        delete.clicked.connect(self._delete_history)
        history_actions.addWidget(load)
        history_actions.addWidget(delete)
        history_layout.addLayout(history_actions)
        self._tabs.addTab(history, "历史记录")

        bottom = QTabWidget()
        layout.addWidget(bottom, 2)
        plot = QWidget()
        self._plot_layout = QVBoxLayout(plot)
        self._placeholder = QLabel("选择曲线后显示应力–应变图和拟合区间")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._plot_layout.addWidget(self._placeholder)
        bottom.addTab(plot, "曲线与拟合")
        self._details = QTextEdit()
        self._details.setReadOnly(True)
        bottom.addTab(self._details, "计算过程与分组统计")
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        bottom.addTab(self._log, "导入日志")
        progress_row = QHBoxLayout()
        self._progress = QProgressBar()
        self._progress.setValue(0)
        self._cancel = QPushButton("取消导入")
        self._cancel.setEnabled(False)
        self._cancel.clicked.connect(self._cancel_import)
        progress_row.addWidget(self._progress)
        progress_row.addWidget(self._cancel)
        layout.addLayout(progress_row)
        split.addWidget(right)
        split.setSizes([300, 850])

        self._source.currentIndexChanged.connect(self._source_changed)
        self._section.currentIndexChanged.connect(self._visibility)
        self._fit_mode.currentIndexChanged.connect(self._fit_changed)
        for widget in (*self._dims.values(), self._lo, self._hi, self._target, self._fracture):
            widget.valueChanged.connect(self._mark_dirty)
        for widget in (self._source, self._section, self._fit_mode):
            widget.currentIndexChanged.connect(self._mark_dirty)
        self._name.textChanged.connect(self._mark_dirty)
        self._remark.textChanged.connect(self._mark_dirty)
        self._date.date_edit.dateChanged.connect(self._mark_dirty)
        self._table.itemSelectionChanged.connect(self._selection_changed)
        self._search.textChanged.connect(self.refresh_history)
        self._import_button.clicked.connect(lambda: self._choose_files(False))
        self._mapping_button.clicked.connect(lambda: self._choose_files(True))
        self._recalc_button.clicked.connect(self._recalculate)
        self._save_button.clicked.connect(self._save)
        self._remove_button.clicked.connect(self._remove)
        self._source_changed()
        self._buttons()

    @staticmethod
    def _spin(value, minimum, maximum, decimals):
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setValue(value)
        return spin

    @staticmethod
    def _table_widget(headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setMinimumHeight(140)
        return table

    def _source_changed(self, *_):
        self._x_unit.clear()
        self._x_unit.addItems(["%", "mm/mm"] if self._source.currentData() == "strain" else ["mm", "μm"])
        self._visibility()
        if self._source.currentData() == "crosshead":
            text = "横梁位移包含机架和夹持变形，结果标记为表观值。优先使用标距内实测伸长或应变。"
        else:
            text = "数据按采集顺序分析，不自动平滑、排序或平移零点。峰值不自动视为断裂点。"
        self._hint.setText(text)

    def _visibility(self, *_):
        section = self._section.currentData()
        visible = {"width_mm": section == "rectangle", "thickness_mm": section == "rectangle",
                   "diameter_mm": section == "circle", "area_mm2": section == "area",
                   "gauge_mm": self._source.currentData() != "strain"}
        for key, value in visible.items():
            self._dim_form.setRowVisible(self._dims[key], value)

    def _fit_changed(self, *_):
        if not self._loading:
            self._lo.setValue(20 if self._fit_mode.currentData() == "force" else .05)
            self._hi.setValue(60 if self._fit_mode.currentData() == "force" else .25)

    def _spec(self):
        return Spec(source=self._source.currentData(),
                    section=self._section.currentData(), **{k: w.value() for k, w in self._dims.items()},
                    fit_mode=self._fit_mode.currentData(), fit_lo=self._lo.value(), fit_hi=self._hi.value(),
                    target_pct=self._target.value(), fracture_point=self._fracture.value())

    def _mark_dirty(self, *_):
        if self._loading:
            return
        self._dirty = bool(self._selected())
        if self._dirty:
            self._status.setText("参数已修改。请点击“将参数应用到所选曲线”；图和表仍显示上次分析结果。")
        self._buttons()

    def _selected(self):
        return sorted({index.row() for index in self._table.selectionModel().selectedRows()})

    def _buttons(self):
        busy = self._thread is not None
        selected = bool(self._selected())
        self._parameters.setEnabled(not busy)
        self._import_button.setEnabled(not busy)
        self._mapping_button.setEnabled(not busy)
        self._table.setEnabled(not busy)
        self._tabs.setEnabled(not busy)
        for button in [self._save_button, *self._export_buttons]:
            button.setEnabled(selected and not self._dirty and not busy)
        self._remove_button.setEnabled(selected and not busy)
        self._recalc_button.setEnabled(selected and not busy)
        self._cancel.setEnabled(busy)

    def _choose_files(self, advanced):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择曲线文件", prefs.last_dir(),
                                               "曲线数据 (*.xlsx *.xlsm *.csv *.txt *.tsv)")
        if not paths:
            return
        prefs.set_last_dir(str(Path(paths[0]).parent))
        rule = prefs.import_rule("mechanical")
        if advanced:
            try:
                dialog = ImportSettingsDialog(paths[0], "mechanical", list(FIELDS), ALIASES, parent=self)
                if not dialog.exec():
                    return
                rule = dialog.settings()
            except Exception as exc:
                QMessageBox.warning(self, "导入设置失败", str(exc))
                return
        options = {key: rule[key] for key in ("sheet_name", "header_row", "column_mapping") if key in rule}
        options.update(x_unit=self._x_unit.currentText(), force_unit=self._force_unit.currentText(),
                       decimal_separator=self._decimal.currentData())
        self.start_import(paths, options)

    def start_import(self, paths, options):
        """Start one batch with an immutable parameter snapshot (also used by smoke tests)."""
        if self._thread is not None:
            return
        if len(paths) > 1 and self._fracture.value():
            QMessageBox.warning(self, "请逐条指定断裂点", "批量导入前请将断裂点设为“未指定”，导入后逐条确认。")
            return
        metadata = {"name": self._name.text().strip() if len(paths) == 1 else "",
                    "remark": self._remark.text(), "test_date": self._date.date().toString("yyyy-MM-dd")}
        self._progress.setRange(0, len(paths))
        self._progress.setValue(0)
        self._thread = ImportWorker(paths, self._spec(), dict(options), metadata, self)
        self._thread.item.connect(self._add_entry)
        self._thread.progress.connect(self._progress_update)
        self._thread.finished.connect(self._finished)
        self._buttons()
        self._status.setText("正在导入；单个文件失败不会中断后续文件。")
        self._thread.start()

    def _progress_update(self, count, message):
        self._progress.setValue(count)
        self._log.append(message.replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br>"))

    def _add_entry(self, entry):
        self._entries.append(entry)
        self._render_table()

    def _finished(self):
        thread = self._thread
        cancelled = thread.isInterruptionRequested() if thread else False
        self._thread = None
        if thread:
            thread.deleteLater()
        self._status.setText("导入已取消，已完成结果保留。" if cancelled else "导入完成，失败原因见导入日志。")
        self._buttons()
        if self._entries:
            self._table.selectRow(len(self._entries) - 1)

    def _cancel_import(self):
        if self._thread:
            self._thread.requestInterruption()
            self._status.setText("将在当前文件处理完成后取消。")

    def _render_table(self):
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._entries))
        for i, e in enumerate(self._entries):
            r = e["result"]
            source_label = {"strain": "实测应变", "extension": "实测伸长", "crosshead": "表观"}[e["spec"].source]
            values = [e["name"], f"{MODES[e['spec'].mode]} · {source_label}", f"{r.modulus_gpa:.6g}",
                      f"{r.strength_mpa:.6g}", f"{r.peak_strain_pct:.6g}", f"{r.r2:.5f}",
                      "已保存" if e.get("saved_id") else "未保存"]
            for j, value in enumerate(values):
                self._table.setItem(i, j, QTableWidgetItem(value))
        self._table.blockSignals(False)

    def _selection_changed(self):
        indices = self._selected()
        self._dirty = False
        if len(indices) == 1:
            e = self._entries[indices[0]]
            self._loading = True
            s = e["spec"]
            self._source.setCurrentIndex(self._source.findData(s.source))
            self._section.setCurrentIndex(self._section.findData(s.section))
            for key, widget in self._dims.items():
                widget.setValue(getattr(s, key))
            self._fit_mode.setCurrentIndex(self._fit_mode.findData(s.fit_mode))
            self._lo.setValue(s.fit_lo)
            self._hi.setValue(s.fit_hi)
            self._target.setValue(s.target_pct)
            self._fracture.setValue(s.fracture_point)
            self._name.setText(e["name"])
            self._remark.setText(e.get("remark", ""))
            from PySide6.QtCore import QDate
            date = QDate.fromString(e.get("test_date", ""), "yyyy-MM-dd")
            if date.isValid():
                self._date.setDate(date)
            self._loading = False
        self._buttons()
        self._show_results([self._entries[i] for i in indices])

    def _show_results(self, entries):
        from .exporters import grouped_statistics
        self._status.setText(f"已选 {len(entries)} 条曲线。图最多显示前20条；完整数据保留用于导出。")
        if len(entries) == 1:
            self._status.setText("单条曲线：阴影为拟合区间。可在曲线上双击选取断裂点，再点击应用参数确认。")
        lines = []
        for e in entries:
            lines.extend([e["name"], *e["result"].steps, *e["result"].warnings, ""])
        for key, values in grouped_statistics(entries):
            lines.append(f"分组统计：{MODES[key[0]]} / {SOURCES[key[1]]} / 拟合 {key[2]} {key[3]:g}–{key[4]:g}")
            for field, v in values.items():
                label = {"modulus_gpa": "模量(GPa)", "strength_mpa": "峰值应力(MPa)", "peak_strain_pct": "峰值应变(%)"}[field]
                lines.append(f"{label}：n={v['n']}，均值={v['mean']:.6g}，样本标准差={v['sd'] if v['sd'] is not None else '—'}，CV%={v['cv_pct'] if v['cv_pct'] is not None else '—'}")
        self._details.setPlainText("\n".join(lines))
        if not entries:
            if self._canvas:
                self._canvas.hide()
                self._toolbar.hide()
            self._placeholder.show()
            return
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from ..ui.weibull_plot import ChineseNavigationToolbar
        from .plotting import build_figure
        if self._canvas:
            self._canvas.hide()
            self._toolbar.hide()
            self._plot_layout.removeWidget(self._canvas)
            self._plot_layout.removeWidget(self._toolbar)
            self._canvas.deleteLater()
            self._toolbar.deleteLater()
        self._placeholder.hide()
        self._canvas = FigureCanvasQTAgg(build_figure(entries))
        self._toolbar = ChineseNavigationToolbar(self._canvas, self)
        self._plot_layout.addWidget(self._toolbar)
        self._plot_layout.addWidget(self._canvas, 1)
        self._canvas.mpl_connect("button_press_event", self._pick_fracture_point)
        self._canvas.draw_idle()

    def _pick_fracture_point(self, event):
        if not event.dblclick or event.inaxes is None or len(self._selected()) != 1 or self._toolbar.mode:
            return
        import numpy as np
        result = self._entries[self._selected()[0]]["result"]
        coordinates = np.column_stack((np.asarray(result.strain) * 100, result.stress_mpa))
        pixels = event.inaxes.transData.transform(coordinates)
        distance = np.sum((pixels - [event.x, event.y]) ** 2, axis=1)
        index = int(np.argmin(distance))
        if distance[index] > 20 ** 2:
            self._status.setText("请在曲线附近双击以选择原始数据点。")
            return
        self._fracture.setValue(index + 1)
        self._status.setText(f"已选第 {index + 1} 点作为待确认断裂点；请点击“将参数应用到所选曲线”。")

    def _recalculate(self):
        spec = self._spec()
        indices = self._selected()
        try:
            replacements = []
            if len(indices) > 1 and spec.fracture_point:
                raise ValueError("请逐条确认断裂点，不能将同一点号批量套用到不同曲线。")
            for i in indices:
                old = self._entries[i]
                if old["spec"].source != spec.source:
                    raise ValueError("变形来源已改变，请重新导入文件并确认单位；不能直接重新解释已有数据。")
                updated = {**old, "spec": spec, "result": analyze(old["x"], old["force"], spec),
                           "remark": self._remark.text(), "test_date": self._date.date().toString("yyyy-MM-dd")}
                if len(indices) == 1:
                    updated["name"] = self._name.text().strip() or old["name"]
                updated.pop("saved_id", None)
                updated.pop("saved_app_version", None)
                updated.pop("saved_algorithm_version", None)
                replacements.append((i, updated))
            for i, updated in replacements:
                self._entries[i] = updated
        except Exception as exc:
            QMessageBox.warning(self, "未应用参数", str(exc))
            return
        self._dirty = False
        self._render_table()
        self._buttons()
        self._show_results([self._entries[i] for i in indices])

    def _save(self):
        entries = [self._entries[i] for i in self._selected() if not self._entries[i].get("saved_id")]
        if not entries or self._dirty:
            return
        try:
            for e, record_id in zip(entries, save_entries(self._conn, entries)):
                e["saved_id"] = record_id
            self._render_table()
            self.refresh_history()
            self._status.setText(f"已保存 {len(entries)} 条曲线及原始输入、拟合参数。")
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))

    def _remove(self):
        indices = self._selected()
        if any(not self._entries[i].get("saved_id") for i in indices):
            if QMessageBox.question(self, "移出曲线", "所选包含未保存结果，确定移出？") != QMessageBox.Yes:
                return
        for i in reversed(indices):
            self._entries.pop(i)
        self._table.clearSelection()
        self._render_table()
        self._selection_changed()

    def refresh_history(self, *_):
        self._history_rows = list_entries(self._conn, self._search.text())
        self._history.setRowCount(len(self._history_rows))
        for i, row in enumerate(self._history_rows):
            r = json.loads(row["result_json"])
            mode_label = MODES[row["mode"]] + ("（表观）" if row["source"] == "crosshead" else "")
            values = [row["sample_name"], mode_label, f"{r['modulus_gpa']:.6g}",
                      f"{r['strength_mpa']:.6g}", row["test_date"], row["app_version"]]
            for j, value in enumerate(values):
                self._history.setItem(i, j, QTableWidgetItem(str(value)))

    def _load_history(self):
        try:
            for index in self._history.selectionModel().selectedRows():
                record_id = self._history_rows[index.row()]["id"]
                if not any(e.get("saved_id") == record_id for e in self._entries):
                    self._add_entry(load_entry(self._conn, record_id))
            self._tabs.setCurrentIndex(0)
            if self._entries:
                self._table.selectRow(len(self._entries) - 1)
        except Exception as exc:
            QMessageBox.warning(self, "读取失败", str(exc))

    def _delete_history(self):
        ids = [self._history_rows[i.row()]["id"] for i in self._history.selectionModel().selectedRows()]
        if not ids or QMessageBox.question(self, "删除历史", f"永久删除所选 {len(ids)} 条历史记录？") != QMessageBox.Yes:
            return
        try:
            delete_entries(self._conn, ids)
            for e in self._entries:
                if e.get("saved_id") in ids:
                    e.pop("saved_id")
            self.refresh_history()
            self._render_table()
        except Exception as exc:
            QMessageBox.warning(self, "删除失败", str(exc))

    def _export(self, kind):
        from .exporters import export_excel, export_csv, export_pdf
        entries = [self._entries[i] for i in self._selected()]
        if not entries or self._dirty:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出所选曲线", str(Path(prefs.last_dir()) / f"通用力学报告.{kind}"), f"报告 (*.{kind})")
        if not path:
            return
        source_paths = {Path(e["import"]["file"]).resolve() for e in self._entries if e.get("import", {}).get("file")}
        if Path(path).resolve() in source_paths:
            QMessageBox.warning(self, "不能覆盖源文件", "请选择新的报告文件名。")
            return
        try:
            {"xlsx": export_excel, "csv": export_csv, "pdf": export_pdf}[kind](path, entries)
            prefs.set_last_dir(str(Path(path).parent))
            self._status.setText(f"已导出：{path}")
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", str(exc))

    def has_unsaved(self):
        return any(not e.get("saved_id") for e in self._entries)

    def shutdown(self):
        if self._thread and self._thread.isRunning():
            self._thread.requestInterruption()
            return self._thread.wait(3000)
        return True
