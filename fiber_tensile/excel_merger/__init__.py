"""多文件夹 Excel 数据提取与合并模块。"""

from .core import MergeOptions, MergeResult, discover_excel_files, merge_workbooks

__all__ = ["MergeOptions", "MergeResult", "discover_excel_files", "merge_workbooks"]
