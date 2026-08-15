"""对话框：导入预览/错误报告向导、批次对比。"""

import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..core.models import MODE_FILAMENT, MODE_LABELS, MODE_TEXTILE, strength_unit_label
from ..data.repository import list_batches
from ..fileio.importer import ImportFileError, parse_file
from . import prefs

_PREVIEW_LIMIT = 20


class ImportWizardDialog(QDialog):
    """导入向导：选文件 → 解析校验 → 预览与目标批次选择 → 确认。

    run() 为静态入口，确认后返回
    dict(mode, batch_name, append_batch_id, samples, density)，取消返回 None。
    """

    @staticmethod
    def run(conn: sqlite3.Connection, parent: QWidget | None = None):
        path, _ = QFileDialog.getOpenFileName(
            parent, "选择导入文件", prefs.last_dir() or "",
            "数据文件 (*.xlsx *.xlsm *.csv *.txt);;所有文件 (*.*)")
        if not path:
            return None
        prefs.set_last_dir(str(Path(path).parent))
        # 解析：模式歧义（同时含直径与线密度列）时请用户指定
        mode = None
        while True:
            try:
                preview = parse_file(path, mode)
                break
            except ImportFileError as e:
                if mode is None and "同时包含" in str(e):
                    box = QMessageBox(parent)
                    box.setWindowTitle("请指定计算模式")
                    box.setText("文件同时包含「直径(μm)」与「线密度(dtex)」列，\n"
                                "请选择以哪个模式解析：")
                    btn_f = box.addButton("单丝模式（用直径）", QMessageBox.AcceptRole)
                    btn_t = box.addButton("纺织模式（用线密度）", QMessageBox.ActionRole)
                    box.addButton("取消", QMessageBox.RejectRole)
                    box.exec()
                    if box.clickedButton() is btn_f:
                        mode = MODE_FILAMENT
                        continue
                    if box.clickedButton() is btn_t:
                        mode = MODE_TEXTILE
                        continue
                    return None
                QMessageBox.critical(parent, "导入失败", str(e))
                return None
        dlg = ImportWizardDialog(conn, preview, Path(path).name, parent)
        if dlg.exec() != QDialog.Accepted:
            return None
        return dlg.result_payload()

    def __init__(self, conn: sqlite3.Connection, preview, filename: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._conn = conn
        self._preview = preview
        self.setWindowTitle("导入预览")
        self.resize(720, 560)
        self._batches = list_batches(conn, mode=preview.inferred_mode)  # 仅同模式可追加
        self._build_ui(filename)

    # ---- UI ----

    def _build_ui(self, filename: str) -> None:
        layout = QVBoxLayout(self)
        p = self._preview
        layout.addWidget(QLabel(
            f"文件：{filename}　　模式：{MODE_LABELS[p.inferred_mode]}　　"
            f"共 {p.total_rows} 行数据，有效 {p.valid_rows} 行，错误 {len(p.errors)} 行"))
        layout.addWidget(QLabel(f"警告 {len(p.warnings)} 条（非阻断，详见下方列表）"))

        # 目标批次
        row = QHBoxLayout()
        row.addWidget(QLabel("导入到："))
        self._combo_batch = QComboBox()
        default_name = p.batch_from_file or Path(filename).stem or "新批次"
        self._combo_batch.addItem(f"新建批次「{default_name}」")
        for b in self._batches:
            self._combo_batch.addItem(f"追加到现有批次「{b.batch_name}」（{b.sample_count} 条）")
        self._combo_batch.currentIndexChanged.connect(self._on_target_changed)
        row.addWidget(self._combo_batch, 1)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("批次名称："))
        self._edit_name = QLineEdit(default_name)
        row2.addWidget(self._edit_name, 1)
        layout.addLayout(row2)

        # 预览表
        layout.addWidget(QLabel(f"有效数据预览（前 {min(_PREVIEW_LIMIT, p.valid_rows)} 行）："))
        self._table = self._build_preview_table(p)
        layout.addWidget(self._table, 1)

        # 错误/警告明细
        layout.addWidget(QLabel("错误与警告明细："))
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(10000)
        self._log.setPlainText(self._build_log_text())
        layout.addWidget(self._log, 1)

        # 按钮
        buttons = QDialogButtonBox()
        self._btn_ok = buttons.addButton("仅导入有效行", QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._btn_ok.setEnabled(p.valid_rows > 0)
        layout.addWidget(buttons)

    def _build_preview_table(self, p) -> QTableWidget:
        if p.inferred_mode == MODE_FILAMENT:
            headers = ["编号", "断裂强力", "强力单位", "直径(μm)", "密度(g/cm³)", "备注", "测试日期"]
        else:
            headers = ["编号", "断裂强力", "强力单位", "线密度(dtex)", "密度(g/cm³)", "备注", "测试日期"]
        table = QTableWidget(min(_PREVIEW_LIMIT, p.valid_rows), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        for r, s in enumerate(p.samples[:_PREVIEW_LIMIT]):
            dim = s.diameter_um if p.inferred_mode == MODE_FILAMENT else s.linear_density_dtex
            values = [
                s.sample_no or "", f"{s.breaking_force:g}", s.force_unit,
                f"{dim:g}", f"{s.density_gcm3:g}" if s.density_gcm3 is not None else "",
                s.remark or "", s.test_date or "",
            ]
            for c, v in enumerate(values):
                table.setItem(r, c, QTableWidgetItem(v))
        return table

    def _build_log_text(self) -> str:
        p = self._preview
        lines = []
        for e in p.errors:
            col = f"（{e.column}）" if e.column else ""
            lines.append(f"第 {e.row_number} 行 {col} 错误：{e.message}（原值：{e.raw_value!r}）")
        for w in p.warnings:
            col = f"（{w.column}）" if w.column else ""
            lines.append(f"第 {w.row_number} 行 {col} 警告：{w.message}（原值：{w.raw_value!r}）")
        return "\n".join(lines) if lines else "（无错误与警告）"

    def _on_target_changed(self, index: int) -> None:
        self._edit_name.setEnabled(index == 0)

    # ---- 结果 ----

    def result_payload(self) -> dict:
        p = self._preview
        densities = {s.density_gcm3 for s in p.samples if s.density_gcm3 is not None}
        density = next(iter(densities)) if len(densities) == 1 else (
            min(densities) if densities else None)
        if self._combo_batch.currentIndex() == 0:
            name = self._edit_name.text().strip()
            if not name:
                name = p.batch_from_file or "新批次"
            return {"mode": p.inferred_mode, "batch_name": name,
                    "append_batch_id": None, "samples": p.samples, "density": density}
        batch = self._batches[self._combo_batch.currentIndex() - 1]
        return {"mode": p.inferred_mode, "batch_name": None,
                "append_batch_id": batch.id, "samples": p.samples, "density": density}


class CompareDialog(QDialog):
    """批次对比：统计指标对比表 + Weibull 多曲线叠加图。

    入参 payload：[(Batch, AnalysisResult, WeibullResult|None), ...]，模式必须一致。
    """

    def __init__(self, payload: list, parent: QWidget | None = None):
        # 延迟导入 matplotlib：只在打开对比窗口时加载
        from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

        from .weibull_plot import MplCanvas

        super().__init__(parent)
        self.setWindowTitle("批次对比")
        self.resize(920, 640)
        layout = QVBoxLayout(self)

        unit = strength_unit_label(payload[0][0].mode)
        headers = ["批次名称", "样本数 N", f"均值({unit})", f"标准差({unit})",
                   "变异系数 CV%", f"最小值({unit})", f"最大值({unit})"]
        table = QTableWidget(len(payload), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for r, (batch, stats, _) in enumerate(payload):
            values = [
                batch.batch_name, str(stats.n), f"{stats.mean:.2f}",
                f"{stats.std:.2f}" if stats.std is not None else "—",
                f"{stats.cv_percent:.2f}" if stats.cv_percent is not None else "—",
                f"{stats.min_val:.2f}", f"{stats.max_val:.2f}",
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(r, c, item)
        layout.addWidget(table)

        series = [w for _, _, w in payload if w is not None]
        labels = [b.batch_name for b, _, w in payload if w is not None]
        if series:
            canvas = MplCanvas()
            canvas.draw_weibull(series, labels=labels, title="Weibull 分布对比图",
                                sigma0_unit=unit)
            layout.addWidget(NavigationToolbar2QT(canvas, self))
            layout.addWidget(canvas, 1)
        else:
            layout.addWidget(QLabel("（所选批次数据量不足，无法绘制 Weibull 对比图）"))

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
