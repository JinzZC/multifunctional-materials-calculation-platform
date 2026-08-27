"""Excel 安全写入工具：外部文本永远作为文本，不作为公式执行。"""

from __future__ import annotations


_FORMULA_PREFIXES = ("=", "+", "-", "@")


def spreadsheet_safe_text(value):
    """供 CSV 等文本表格使用：用撇号阻止 Excel 把外部文本解释为公式。"""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def set_cell_value(cell, value):
    """设置单元格值，并把可能触发公式解释的字符串强制标记为文本。

    openpyxl 会自动把 ``=...`` 识别成公式。来自 CSV/TXT 或用户输入的内容
    必须保持原样；显式设置 ``data_type='s'`` 不会在显示内容前增加撇号。
    ``+/-/@`` 当前通常会被 openpyxl 当作普通字符串，但一并固定为文本，避免
    不同 Excel 版本或后续导出链路重新解释。
    """
    cell.value = value
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        cell.data_type = "s"
    return cell


def append_safe_row(ws, values):
    """追加一行，并对其中的外部文本应用安全写入规则。"""
    values = list(values)
    ws.append(values)
    row_number = ws.max_row
    for column, value in enumerate(values, 1):
        set_cell_value(ws.cell(row_number, column), value)
    return row_number
