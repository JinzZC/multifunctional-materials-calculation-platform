"""多文件夹 Excel 数据提取与合并界面。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMessageBox,
    QProgressBar, QPushButton, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .core import (MergeOptions, MergeResult, discover_excel_files,
                   export_merged_workbook, merge_workbooks)

PREVIEW_LIMIT = 500


class _MergeWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, paths, options, folders):
        super().__init__()
        self.paths = paths
        self.options = options
        self.folders = folders

    @Slot()
    def run(self):
        try:
            self.finished.emit(merge_workbooks(self.paths, self.options, self.folders))
        except Exception as exc:
            self.failed.emit(str(exc))


class ExcelMergerTab(QWidget):
    """扫描、预览并导出多个目录中的 Excel 表格。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result: MergeResult | None = None
        self._thread: QThread | None = None
        self._worker: _MergeWorker | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        title = QLabel("表格数据批量提取与合并模块")
        title.setStyleSheet("font-size: 16pt; font-weight: bold; color: #1F4E79;")
        subtitle = QLabel(
            "从多个文件夹及子文件夹提取 Excel、CSV、TXT、TSV 数据，按样品名排序并生成可追溯总表。")
        subtitle.setStyleSheet("color: #526579;")
        root.addWidget(title)
        root.addWidget(subtitle)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        setup = QWidget()
        setup_layout = QHBoxLayout(setup)
        setup_layout.setContentsMargins(0, 0, 0, 0)

        folder_group = QGroupBox("1. 数据文件夹")
        folder_layout = QVBoxLayout(folder_group)
        self._folders = QListWidget()
        self._folders.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._folders.setMinimumHeight(110)
        folder_layout.addWidget(self._folders)
        folder_buttons = QHBoxLayout()
        self._btn_add_folder = QPushButton("添加文件夹")
        self._btn_remove_folder = QPushButton("移除选中")
        self._btn_clear_folders = QPushButton("全部清空")
        folder_buttons.addWidget(self._btn_add_folder)
        folder_buttons.addWidget(self._btn_remove_folder)
        folder_buttons.addWidget(self._btn_clear_folders)
        folder_layout.addLayout(folder_buttons)
        setup_layout.addWidget(folder_group, 3)

        option_group = QGroupBox("2. 提取设置")
        form = QFormLayout(option_group)
        self._spin_header = QSpinBox()
        self._spin_header.setRange(1, 1000)
        self._spin_header.setValue(1)
        self._spin_header.setToolTip("Excel 中作为列名的行号，从 1 开始")
        self._edit_filename_filter = QLineEdit()
        self._edit_filename_filter.setPlaceholderText("留空扫描全部；例如：拉伸")
        self._edit_filename_filter.setToolTip(
            "只扫描文件名中包含该文字的表格文件，忽略英文字母大小写和全角/半角差异")
        self._combo_sheet_mode = QComboBox()
        self._combo_sheet_mode.addItems([
            "提取所有工作表",
            "仅提取名称完全相同的工作表",
            "提取名称中包含指定字符的工作表",
        ])
        self._edit_sheet = QLineEdit()
        self._edit_sheet.setPlaceholderText("例如：测试数据；仅对 Excel 文件生效")
        self._edit_sheet.setToolTip(
            "包含匹配忽略英文字母大小写和全角/半角差异；CSV/TXT/TSV 不受工作表筛选影响")
        self._edit_sheet.setEnabled(False)
        self._combo_columns = QComboBox()
        self._combo_columns.addItem("保留所有列（推荐）", "union")
        self._combo_columns.addItem("仅保留共同列", "intersection")
        self._check_recursive = QCheckBox("包含子文件夹")
        self._check_recursive.setChecked(True)
        self._check_source = QCheckBox("添加来源追踪列")
        self._check_source.setChecked(True)
        self._check_empty = QCheckBox("忽略完全空白的数据行")
        self._check_empty.setChecked(True)
        self._check_sort_sample = QCheckBox("按样品名自然排序")
        self._check_sort_sample.setChecked(True)
        self._edit_sample_column = QLineEdit()
        self._edit_sample_column.setPlaceholderText("留空则自动识别样品名/样品名称等")
        form.addRow("表头所在行：", self._spin_header)
        form.addRow("文件名包含：", self._edit_filename_filter)
        form.addRow("工作表范围：", self._combo_sheet_mode)
        form.addRow("工作表名称：", self._edit_sheet)
        form.addRow("列合并方式：", self._combo_columns)
        form.addRow("扫描范围：", self._check_recursive)
        form.addRow("结果追踪：", self._check_source)
        form.addRow("空行处理：", self._check_empty)
        form.addRow("结果排序：", self._check_sort_sample)
        form.addRow("样品名列：", self._edit_sample_column)
        setup_layout.addWidget(option_group, 2)
        splitter.addWidget(setup)

        files_group = QGroupBox("3. 扫描到的表格文件（取消勾选可排除文件）")
        files_layout = QVBoxLayout(files_group)
        file_actions = QHBoxLayout()
        self._btn_scan = QPushButton("扫描文件")
        self._btn_all = QPushButton("全部选择")
        self._btn_none = QPushButton("全部取消")
        self._lbl_file_count = QLabel("尚未扫描")
        file_actions.addWidget(self._btn_scan)
        file_actions.addWidget(self._btn_all)
        file_actions.addWidget(self._btn_none)
        file_actions.addStretch()
        file_actions.addWidget(self._lbl_file_count)
        files_layout.addLayout(file_actions)
        self._files = QTableWidget(0, 4)
        self._files.setHorizontalHeaderLabels(["使用", "文件名", "所在文件夹", "完整路径"])
        self._files.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._files.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._files.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._files.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._files.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._files.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._files.setMinimumHeight(130)
        files_layout.addWidget(self._files)
        splitter.addWidget(files_group)

        result_group = QGroupBox("4. 合并预览与导出")
        result_layout = QVBoxLayout(result_group)
        result_actions = QHBoxLayout()
        self._btn_preview = QPushButton("提取并预览")
        self._btn_export = QPushButton("导出总 Excel")
        self._btn_export.setEnabled(False)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._lbl_summary = QLabel("请先添加文件夹并扫描")
        result_actions.addWidget(self._btn_preview)
        result_actions.addWidget(self._btn_export)
        result_actions.addWidget(self._progress)
        result_actions.addStretch()
        result_actions.addWidget(self._lbl_summary)
        result_layout.addLayout(result_actions)
        self._preview = QTableWidget()
        self._preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._preview.setAlternatingRowColors(True)
        self._preview.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._preview.verticalHeader().setVisible(False)
        result_layout.addWidget(self._preview)
        self._lbl_log = QLabel("")
        self._lbl_log.setWordWrap(True)
        self._lbl_log.setStyleSheet("color: #8A4B08;")
        result_layout.addWidget(self._lbl_log)
        splitter.addWidget(result_group)
        splitter.setSizes([230, 220, 330])

        self._btn_add_folder.clicked.connect(self._add_folder)
        self._btn_remove_folder.clicked.connect(self._remove_folders)
        self._btn_clear_folders.clicked.connect(self._clear_folders)
        self._btn_scan.clicked.connect(self._scan)
        self._btn_all.clicked.connect(lambda: self._set_all_checked(True))
        self._btn_none.clicked.connect(lambda: self._set_all_checked(False))
        self._btn_preview.clicked.connect(self._start_preview)
        self._btn_export.clicked.connect(self._export)
        self._combo_sheet_mode.currentIndexChanged.connect(self._sheet_mode_changed)
        self._check_sort_sample.toggled.connect(self._edit_sample_column.setEnabled)
        self._edit_filename_filter.textChanged.connect(self._filename_filter_changed)
        self._check_recursive.toggled.connect(self._filename_filter_changed)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择包含 Excel 文件的文件夹")
        if not folder:
            return
        existing = {self._folders.item(i).text().casefold()
                    for i in range(self._folders.count())}
        if folder.casefold() not in existing:
            self._folders.addItem(folder)
        self._invalidate()

    def _remove_folders(self):
        for item in self._folders.selectedItems():
            self._folders.takeItem(self._folders.row(item))
        self._files.setRowCount(0)
        self._lbl_file_count.setText("请重新扫描")
        self._invalidate()

    def _clear_folders(self):
        self._folders.clear()
        self._files.setRowCount(0)
        self._lbl_file_count.setText("尚未扫描")
        self._invalidate()

    def _folder_paths(self):
        return [self._folders.item(i).text() for i in range(self._folders.count())]

    def _scan(self):
        folders = self._folder_paths()
        if not folders:
            QMessageBox.warning(self, "缺少文件夹", "请先添加至少一个数据文件夹。")
            return
        filename_filter = self._edit_filename_filter.text().strip() or None
        files = discover_excel_files(
            folders, self._check_recursive.isChecked(), filename_contains=filename_filter)
        self._files.setRowCount(len(files))
        for row, path in enumerate(files):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Checked)
            self._files.setItem(row, 0, check)
            self._files.setItem(row, 1, QTableWidgetItem(path.name))
            self._files.setItem(row, 2, QTableWidgetItem(str(path.parent)))
            self._files.setItem(row, 3, QTableWidgetItem(str(path)))
        filter_note = f"（文件名包含“{filename_filter}”）" if filename_filter else ""
        self._lbl_file_count.setText(f"共找到 {len(files)} 个文件{filter_note}")
        self._invalidate()
        if not files:
            QMessageBox.information(
                self, "扫描完成",
                "所选文件夹及子文件夹中没有找到符合文件名条件的 "
                ".xlsx、.xlsm、.csv、.txt 或 .tsv 文件。")

    def _filename_filter_changed(self, *_args):
        if self._files.rowCount():
            self._files.setRowCount(0)
            self._lbl_file_count.setText("扫描条件已修改，请重新扫描")
        self._invalidate()

    def _set_all_checked(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self._files.rowCount()):
            self._files.item(row, 0).setCheckState(state)

    def _selected_files(self):
        return [self._files.item(row, 3).text() for row in range(self._files.rowCount())
                if self._files.item(row, 0).checkState() == Qt.CheckState.Checked]

    def _options(self):
        sheet = None
        sheet_mode_index = self._combo_sheet_mode.currentIndex()
        if sheet_mode_index in (1, 2):
            sheet = self._edit_sheet.text().strip()
            if not sheet:
                raise ValueError("选择工作表名称筛选后，必须填写名称或包含的字符")
        return MergeOptions(
            header_row=self._spin_header.value(), sheet_name=sheet,
            sheet_match_mode="contains" if sheet_mode_index == 2 else "exact",
            recursive=self._check_recursive.isChecked(),
            include_source=self._check_source.isChecked(),
            column_mode=self._combo_columns.currentData(),
            skip_empty_rows=self._check_empty.isChecked(),
            sort_by_sample=self._check_sort_sample.isChecked(),
            sample_column=self._edit_sample_column.text().strip() or None)

    def _sheet_mode_changed(self, index):
        self._edit_sheet.setEnabled(index in (1, 2))
        if index == 2:
            self._edit_sheet.setPlaceholderText("输入工作表名称中必须包含的字符")
        else:
            self._edit_sheet.setPlaceholderText("例如：测试数据；仅对 Excel 文件生效")

    def _start_preview(self):
        paths = self._selected_files()
        if not paths:
            QMessageBox.warning(self, "没有文件", "请扫描文件并至少勾选一个 Excel 文件。")
            return
        try:
            options = self._options()
        except ValueError as exc:
            QMessageBox.warning(self, "设置不完整", str(exc))
            return
        self._set_busy(True)
        self._thread = QThread(self)
        self._worker = _MergeWorker(paths, options, self._folder_paths())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._preview_ready)
        self._worker.failed.connect(self._preview_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._task_finished)
        self._thread.start()

    @Slot(object)
    def _preview_ready(self, result):
        self._set_busy(False)
        self._result = result
        self._show_result(result)

    @Slot(str)
    def _preview_failed(self, message):
        self._set_busy(False)
        QMessageBox.critical(self, "提取失败", message)

    @Slot()
    def _task_finished(self):
        self._worker = None
        self._thread = None

    def _show_result(self, result: MergeResult):
        shown = min(len(result.rows), PREVIEW_LIMIT)
        self._preview.clear()
        self._preview.setColumnCount(len(result.headers))
        self._preview.setHorizontalHeaderLabels(result.headers)
        self._preview.setRowCount(shown)
        for row in range(shown):
            for column, value in enumerate(result.rows[row]):
                self._preview.setItem(row, column, QTableWidgetItem(
                    "" if value is None else str(value)))
        self._btn_export.setEnabled(bool(result.rows))
        self._lbl_summary.setText(
            f"合并 {len(result.rows):,} 行、{len(result.headers)} 列；"
            f"成功 {result.successful_sheets} 个数据表，异常 {result.failed_sheets} 个")
        details = []
        if len(result.rows) > PREVIEW_LIMIT:
            details.append(f"预览仅显示前 {PREVIEW_LIMIT} 行，导出包含全部数据。")
        if result.warnings:
            details.append(f"有 {len(result.warnings)} 条表头警告，完整内容将写入“合并日志”。")
        failures = [s for s in result.statuses if s.status != "成功"]
        if failures:
            details.append(f"有 {len(failures)} 个数据表未成功提取，请在导出文件的“合并日志”中检查。")
        self._lbl_log.setText(" ".join(details))

    def _export(self):
        if not self._result or not self._result.rows:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出合并总表", "Excel数据合并总表.xlsx", "Excel 工作簿 (*.xlsx)")
        if not path:
            return
        try:
            source_paths = {str(Path(p).resolve()).casefold() for p in self._selected_files()}
            target = str(Path(path).with_suffix(".xlsx").resolve()).casefold()
            if target in source_paths:
                raise ValueError("导出文件不能覆盖任何源 Excel 文件，请选择新的文件名。")
            export_merged_workbook(path, self._result)
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出完成", f"总表已保存：\n{Path(path).with_suffix('.xlsx')}")

    def _set_busy(self, busy):
        self._progress.setVisible(busy)
        self._btn_preview.setEnabled(not busy)
        self._btn_scan.setEnabled(not busy)
        self._btn_export.setEnabled(not busy and bool(self._result and self._result.rows))
        self._lbl_summary.setText("正在读取并校验 Excel 文件……" if busy else self._lbl_summary.text())

    def _invalidate(self):
        self._result = None
        self._btn_export.setEnabled(False)
        self._preview.clear()
        self._preview.setRowCount(0)
        self._preview.setColumnCount(0)
