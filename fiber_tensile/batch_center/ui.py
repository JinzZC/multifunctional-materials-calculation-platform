"""统一批量计算中心界面。"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QListWidget,
    QMessageBox, QProgressBar, QPushButton, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..data.db import open_database
from ..surface_energy.core import METHODS
from ..ui import prefs
from .core import (
    BatchOptions, discover_data_files, export_results_csv, export_results_excel,
    process_files,
)


class _BatchWorker(QObject):
    progress = Signal(int, int, object)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, db_path: str, paths: list[str], options: BatchOptions):
        super().__init__()
        self._db_path = db_path
        self._paths = paths
        self._options = options

    @Slot()
    def run(self) -> None:
        conn = None
        try:
            conn = open_database(self._db_path)
            thread = QThread.currentThread()
            results = process_files(
                conn, self._paths, self._options,
                cancelled=thread.isInterruptionRequested,
                progress=lambda done, total, result:
                    self.progress.emit(done, total, result))
            self.finished.emit(results)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if conn is not None:
                conn.close()


class BatchCenterTab(QWidget):
    """文件扫描、统一计算、进度/错误审计与结果导出。"""

    data_changed = Signal()

    def __init__(self, db_path: str, parent=None):
        super().__init__(parent)
        self._db_path = db_path
        self._paths: list[Path] = []
        self._results = []
        self._thread: QThread | None = None
        self._worker: _BatchWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        title = QLabel("统一批量计算中心")
        title.setStyleSheet("font-size: 16pt; font-weight: bold; color: #1F4E79;")
        root.addWidget(title)
        subtitle = QLabel(
            "一次处理多个文件；每个文件独立校验、计算和保存，单个失败不会中断整批。")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #526579;")
        root.addWidget(subtitle)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)

        setup = QWidget()
        setup_layout = QVBoxLayout(setup)
        setup_layout.setContentsMargins(0, 0, 0, 0)
        options_box = QGroupBox("1. 计算与处理设置")
        form = QFormLayout(options_box)
        self._type = QComboBox()
        self._type.addItem("纤维拉伸强度", "fiber")
        self._type.addItem("接触角表面能", "surface")
        self._type.addItem("单丝拉伸曲线", "curve")
        self._duplicate = QComboBox()
        self._duplicate.addItem("自动重命名并保留", "rename")
        self._duplicate.addItem("跳过同名记录", "skip")
        self._duplicate.addItem("允许同名记录", "allow")
        self._recursive = QCheckBox("扫描所选文件夹的全部子文件夹")
        self._recursive.setChecked(True)
        form.addRow("数据类型：", self._type)
        form.addRow("同名记录：", self._duplicate)
        form.addRow("扫描范围：", self._recursive)

        self._option_stack = QStackedWidget()
        self._option_stack.addWidget(self._fiber_options())
        self._option_stack.addWidget(self._surface_options())
        self._option_stack.addWidget(self._curve_options())
        form.addRow(self._option_stack)
        setup_layout.addWidget(options_box)

        source_box = QGroupBox("2. 待处理文件")
        source_layout = QVBoxLayout(source_box)
        actions = QHBoxLayout()
        self._add_files = QPushButton("添加文件…")
        self._add_folder = QPushButton("添加文件夹…")
        self._remove = QPushButton("移除选中")
        self._clear = QPushButton("清空")
        for button in (self._add_files, self._add_folder, self._remove, self._clear):
            actions.addWidget(button)
        source_layout.addLayout(actions)
        self._file_list = QListWidget()
        self._file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        source_layout.addWidget(self._file_list, 1)
        self._file_count = QLabel("尚未添加文件")
        source_layout.addWidget(self._file_count)
        setup_layout.addWidget(source_box, 1)
        splitter.addWidget(setup)

        result_box = QGroupBox("3. 任务状态与结果")
        result_layout = QVBoxLayout(result_box)
        run_row = QHBoxLayout()
        self._run = QPushButton("开始批量计算")
        self._cancel = QPushButton("取消")
        self._cancel.setVisible(False)
        self._export = QPushButton("导出处理日志…")
        self._export.setEnabled(False)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        run_row.addWidget(self._run)
        run_row.addWidget(self._cancel)
        run_row.addWidget(self._export)
        run_row.addWidget(self._progress, 1)
        result_layout.addLayout(run_row)
        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels(
            ["状态", "文件", "记录名称", "输入行", "有效行", "警告",
             "结果摘要", "错误原因"])
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        header = self._table.horizontalHeader()
        for column in range(6):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        header.setSectionResizeMode(7, QHeaderView.Stretch)
        result_layout.addWidget(self._table)
        self._summary = QLabel("添加文件并选择计算类型后开始处理")
        self._summary.setWordWrap(True)
        result_layout.addWidget(self._summary)
        splitter.addWidget(result_box)
        splitter.setSizes([380, 760])
        root.addWidget(splitter, 1)

        self._type.currentIndexChanged.connect(self._option_stack.setCurrentIndex)
        self._type.currentIndexChanged.connect(self._clear_files)
        self._add_files.clicked.connect(self._choose_files)
        self._add_folder.clicked.connect(self._choose_folder)
        self._remove.clicked.connect(self._remove_selected)
        self._clear.clicked.connect(self._clear_files)
        self._run.clicked.connect(self._start)
        self._cancel.clicked.connect(self._cancel_task)
        self._export.clicked.connect(self._export_log)

    def _fiber_options(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._fiber_mode = QComboBox()
        self._fiber_mode.addItem("自动识别（推荐）", None)
        self._fiber_mode.addItem("单根纤维", "filament")
        self._fiber_mode.addItem("纺织纤维", "textile")
        form.addRow("计算模式：", self._fiber_mode)
        return page

    def _surface_options(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._surface_method = QComboBox()
        for key, spec in METHODS.items():
            self._surface_method.addItem(spec.label, key)
        form.addRow("文件未指定方法时：", self._surface_method)
        return page

    @staticmethod
    def _spin(lo: float, hi: float, value: float, decimals: int = 3) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(lo, hi)
        widget.setDecimals(decimals)
        widget.setValue(value)
        return widget

    def _curve_options(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self._diameter = self._spin(0.001, 10000, 5.4, 4)
        self._gauge = self._spin(0.001, 100000, 25.0, 3)
        self._fit_lo = self._spin(0.01, 0.98, 0.2, 2)
        self._fit_hi = self._spin(0.02, 0.99, 0.7, 2)
        self._disp_unit = QComboBox()
        self._disp_unit.addItem("mm", "mm")
        self._disp_unit.addItem("μm", "um")
        self._force_unit = QComboBox()
        for unit in ("N", "cN", "mN"):
            self._force_unit.addItem(unit, unit)
        form.addRow("纤维直径(μm)：", self._diameter)
        form.addRow("标距(mm)：", self._gauge)
        form.addRow("拟合下限：", self._fit_lo)
        form.addRow("拟合上限：", self._fit_hi)
        form.addRow("文件位移单位：", self._disp_unit)
        form.addRow("文件力单位：", self._force_unit)
        return page

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择批量计算文件", prefs.last_dir(),
            "数据文件 (*.xlsx *.xlsm *.csv *.txt *.tsv);;所有文件 (*.*)")
        if paths:
            prefs.set_last_dir(str(Path(paths[0]).parent))
            self._add_paths(discover_data_files(paths, False))

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "选择数据文件夹", prefs.last_dir())
        if folder:
            prefs.set_last_dir(folder)
            self._add_paths(discover_data_files([folder], self._recursive.isChecked()))

    def _add_paths(self, paths) -> None:
        existing = {str(path).casefold() for path in self._paths}
        for path in paths:
            if str(path).casefold() not in existing:
                self._paths.append(path)
                existing.add(str(path).casefold())
        self._paths.sort(key=lambda path: (path.name.casefold(), str(path).casefold()))
        self._refresh_files()

    def _refresh_files(self) -> None:
        self._file_list.clear()
        self._file_list.addItems([str(path) for path in self._paths])
        self._file_count.setText(f"共 {len(self._paths)} 个待处理文件")
        self._results = []
        self._table.setRowCount(0)
        self._export.setEnabled(False)

    def _remove_selected(self) -> None:
        selected = {item.text().casefold() for item in self._file_list.selectedItems()}
        self._paths = [path for path in self._paths if str(path).casefold() not in selected]
        self._refresh_files()

    def _clear_files(self, *_args) -> None:
        if self._thread and self._thread.isRunning():
            return
        self._paths.clear()
        self._refresh_files()

    def _options(self) -> BatchOptions:
        return BatchOptions(
            data_type=self._type.currentData(),
            recursive=self._recursive.isChecked(),
            duplicate_policy=self._duplicate.currentData(),
            fiber_mode=self._fiber_mode.currentData(),
            surface_method=self._surface_method.currentData(),
            curve_diameter_um=self._diameter.value(),
            curve_gauge_mm=self._gauge.value(),
            curve_fit_lo=self._fit_lo.value(), curve_fit_hi=self._fit_hi.value(),
            curve_disp_unit=self._disp_unit.currentData(),
            curve_force_unit=self._force_unit.currentData())

    def _start(self) -> None:
        if not self._paths:
            QMessageBox.warning(self, "没有文件", "请先添加至少一个待处理文件。")
            return
        try:
            options = self._options()
        except ValueError as exc:
            QMessageBox.warning(self, "设置有误", str(exc))
            return
        self._results = []
        self._table.setRowCount(0)
        self._set_busy(True)
        self._thread = QThread(self)
        self._worker = _BatchWorker(
            self._db_path, [str(path) for path in self._paths], options)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._thread_done)
        self._thread.start()

    @Slot(int, int, object)
    def _on_progress(self, done: int, total: int, result) -> None:
        self._results.append(result)
        row = self._table.rowCount()
        self._table.insertRow(row)
        values = [result.status, Path(result.source).name, result.record_name,
                  str(result.input_rows), str(result.valid_rows),
                  str(result.warning_count), result.summary, result.error]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column == 7 and result.warnings and not value:
                item.setToolTip("\n".join(result.warnings))
            self._table.setItem(row, column, item)
        self._progress.setRange(0, max(total, 1))
        self._progress.setValue(done)
        self._progress.setFormat(f"{done}/{total}  {Path(result.source).name}")

    @Slot(object)
    def _on_finished(self, results) -> None:
        # 正常情况下 progress 已逐项加入；保留赋值以覆盖取消前的最终结果。
        self._results = list(results)
        success = sum(result.status == "成功" for result in results)
        failed = sum(result.status == "失败" for result in results)
        skipped = sum(result.status == "跳过" for result in results)
        cancelled = len(results) < len(self._paths)
        suffix = "；任务已取消" if cancelled else ""
        self._summary.setText(
            f"处理 {len(results)}/{len(self._paths)} 个文件：成功 {success}，"
            f"失败 {failed}，跳过 {skipped}{suffix}")
        self._export.setEnabled(bool(results))
        if success:
            self.data_changed.emit()

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        QMessageBox.critical(self, "批量计算失败", message)

    @Slot()
    def _thread_done(self) -> None:
        self._worker = None
        self._thread = None
        self._set_busy(False)

    def _cancel_task(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.requestInterruption()
            self._cancel.setEnabled(False)
            self._cancel.setText("正在取消…")

    def _set_busy(self, busy: bool) -> None:
        self._progress.setVisible(busy)
        if busy:
            self._progress.setRange(0, 0)
        self._cancel.setVisible(busy)
        self._cancel.setEnabled(busy)
        self._cancel.setText("取消")
        for widget in (self._run, self._add_files, self._add_folder, self._remove,
                       self._clear, self._type, self._duplicate):
            widget.setEnabled(not busy)

    def _export_log(self) -> None:
        if not self._results:
            return
        path, selected = QFileDialog.getSaveFileName(
            self, "导出批量计算日志", os.path.join(prefs.last_dir(), "批量计算日志.xlsx"),
            "Excel 工作簿 (*.xlsx);;CSV 文件 (*.csv)")
        if not path:
            return
        prefs.set_last_dir(str(Path(path).parent))
        try:
            if "CSV" in selected or Path(path).suffix.lower() == ".csv":
                target = str(Path(path).with_suffix(".csv"))
                export_results_csv(target, self._results)
            else:
                target = str(Path(path).with_suffix(".xlsx"))
                export_results_excel(target, self._results)
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出完成", f"批量计算日志已保存：\n{target}")

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        thread = self._thread
        if thread is None or not thread.isRunning():
            return True
        thread.requestInterruption()
        thread.quit()
        return bool(thread.wait(timeout_ms))
