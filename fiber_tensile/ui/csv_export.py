"""历史/明细数据导出为 CSV（UTF-8 BOM，Excel 直接打开不乱码）。"""

import csv
import os

from PySide6.QtWidgets import QFileDialog, QMessageBox

from ..config import sanitize_filename
from . import prefs


def export_csv(path: str, headers: list, rows: list) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def save_csv_dialog(parent, default_name: str, headers: list, rows: list) -> bool:
    """文件对话框 + 导出 CSV + 完成提示。返回是否成功导出。"""
    if not rows:
        QMessageBox.information(parent, "提示", "当前没有可导出的数据。")
        return False
    start = prefs.last_dir()
    safe_name = sanitize_filename(default_name)
    default = os.path.join(start, f"{safe_name}.csv") if start else f"{safe_name}.csv"
    path, _ = QFileDialog.getSaveFileName(parent, "导出 CSV 数据", default,
                                          "CSV 文件 (*.csv)")
    if not path:
        return False
    prefs.set_last_dir(os.path.dirname(path))
    try:
        export_csv(path, headers, rows)
    except OSError as e:
        QMessageBox.critical(parent, "导出失败", str(e))
        return False
    QMessageBox.information(parent, "导出成功", f"数据已保存到：\n{path}")
    return True
