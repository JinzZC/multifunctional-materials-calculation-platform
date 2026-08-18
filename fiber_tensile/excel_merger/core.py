"""Excel 批量提取与合并的纯文件处理层。

列按规范化后的表头名称对齐，首个出现的原始表头作为输出名称。每一行都可附带
来源文件夹、文件、工作表和原始行号，保证合并结果可以回溯到原始数据。
"""

from __future__ import annotations

import os
import csv
import io
import re
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

SUPPORTED_SUFFIXES = {".xlsx", ".xlsm", ".csv", ".txt", ".tsv"}
DELIMITED_SUFFIXES = {".csv", ".txt", ".tsv"}
SOURCE_HEADERS = ("来源文件夹", "来源文件", "来源工作表", "原始行号")
EXCEL_MAX_ROWS = 1_048_576
SAMPLE_NAME_ALIASES = {
    "样品", "样品名", "样品名称", "试样", "试样名", "试样名称", "样本名", "样本名称",
    "sample", "samplename", "sample_name", "specimen", "specimenname",
    "specimen_name",
}


@dataclass(frozen=True)
class MergeOptions:
    header_row: int = 1
    sheet_name: str | None = None       # None 表示全部工作表
    sheet_match_mode: str = "exact"     # exact / contains；仅 Excel 有工作表
    recursive: bool = True
    include_source: bool = True
    column_mode: str = "union"          # union / intersection
    skip_empty_rows: bool = True
    sort_by_sample: bool = False
    sample_column: str | None = None     # None 表示按常见别名自动识别


@dataclass
class FileStatus:
    path: str
    sheet: str
    rows: int = 0
    columns: int = 0
    status: str = "成功"
    message: str = ""


@dataclass
class MergeResult:
    headers: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    statuses: list[FileStatus] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def successful_sheets(self) -> int:
        return sum(s.status == "成功" for s in self.statuses)

    @property
    def failed_sheets(self) -> int:
        return sum(s.status != "成功" for s in self.statuses)


def discover_excel_files(folders: Iterable[str | os.PathLike], recursive: bool = True,
                         excluded_paths: Iterable[str | os.PathLike] = (),
                         filename_contains: str | None = None) -> list[Path]:
    """递归扫描并去重表格文件，可按文件名包含文字筛选。"""
    excluded = {_resolved(p) for p in excluded_paths}
    filename_filter = (_normalise_filename_text(filename_contains)
                       if filename_contains and filename_contains.strip() else None)
    found: dict[str, Path] = {}
    for folder in folders:
        root = Path(folder)
        if not root.is_dir():
            continue
        iterator = root.rglob("*") if recursive else root.glob("*")
        for path in iterator:
            if (path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
                    and not path.name.startswith("~$") and _resolved(path) not in excluded
                    and (filename_filter is None
                         or filename_filter in _normalise_filename_text(path.name))):
                found.setdefault(_resolved(path), path.resolve())
    return sorted(found.values(), key=lambda p: str(p).casefold())


def merge_workbooks(paths: Iterable[str | os.PathLike], options: MergeOptions | None = None,
                    base_folders: Iterable[str | os.PathLike] = ()) -> MergeResult:
    """读取 Excel/CSV/TXT 并按表头合并；单个损坏文件不会中断整个任务。"""
    from openpyxl import load_workbook

    opts = options or MergeOptions()
    if opts.header_row < 1:
        raise ValueError("表头行必须大于或等于 1")
    if opts.column_mode not in {"union", "intersection"}:
        raise ValueError("列合并方式必须是 union 或 intersection")
    if opts.sheet_match_mode not in {"exact", "contains"}:
        raise ValueError("工作表匹配方式必须是 exact 或 contains")

    result = MergeResult()
    records: list[tuple[dict[str, object], list[object]]] = []
    display_names: dict[str, str] = {}
    key_orders: list[list[str]] = []
    # 保留该参数用于后续支持相对路径显示；当前始终记录完整目录，避免同名目录混淆。
    _ = base_folders

    for raw_path in paths:
        path = Path(raw_path).resolve()
        if path.suffix.lower() in DELIMITED_SUFFIXES:
            try:
                _extract_delimited(path, opts, result, records, display_names, key_orders)
            except Exception as exc:
                result.statuses.append(FileStatus(
                    str(path), "分隔文本", status="失败", message=f"读取失败：{exc}"))
            continue
        try:
            wb = load_workbook(path, read_only=True, data_only=True)
        except Exception as exc:
            result.statuses.append(FileStatus(str(path), "—", status="失败",
                                              message=f"无法打开：{exc}"))
            continue
        try:
            if opts.sheet_name is None:
                sheet_names = wb.sheetnames
            elif opts.sheet_match_mode == "contains":
                needle = _normalise_sheet_text(opts.sheet_name)
                sheet_names = [name for name in wb.sheetnames
                               if needle in _normalise_sheet_text(name)]
                if not sheet_names:
                    result.statuses.append(FileStatus(
                        str(path), f"名称包含：{opts.sheet_name}", status="跳过",
                        message="没有名称包含指定字符的工作表"))
                    continue
            else:
                sheet_names = [opts.sheet_name]
            for sheet_name in sheet_names:
                if sheet_name not in wb.sheetnames:
                    result.statuses.append(FileStatus(
                        str(path), sheet_name, status="跳过", message="工作表不存在"))
                    continue
                ws = wb[sheet_name]
                try:
                    _extract_sheet(path, ws, opts, result, records,
                                   display_names, key_orders)
                except Exception as exc:
                    result.statuses.append(FileStatus(
                        str(path), sheet_name, status="失败", message=f"读取失败：{exc}"))
        finally:
            wb.close()

    if not records:
        return result

    if opts.column_mode == "intersection":
        common = set(key_orders[0])
        for keys in key_orders[1:]:
            common.intersection_update(keys)
        data_keys = [key for key in key_orders[0] if key in common]
    else:
        data_keys = list(display_names)

    result.headers = (list(SOURCE_HEADERS) if opts.include_source else []) + [
        display_names[key] for key in data_keys
    ]
    for source, values in records:
        row = ([source[h] for h in SOURCE_HEADERS] if opts.include_source else [])
        value_map = source["__values__"]
        row.extend(value_map.get(key) for key in data_keys)
        result.rows.append(row)
    if opts.sort_by_sample:
        sort_key = _resolve_sample_key(data_keys, display_names, opts.sample_column)
        offset = len(SOURCE_HEADERS) if opts.include_source else 0
        column_index = offset + data_keys.index(sort_key)
        result.rows.sort(key=lambda row: _natural_sort_key(row[column_index]))
        result.warnings.append(f"合并结果已按“{display_names[sort_key]}”自然排序")
    return result


def _extract_delimited(path, opts, result, records, display_names, key_orders) -> None:
    text, encoding = _decode_delimited(path.read_bytes())
    sample = text[:65536]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel if path.suffix.lower() == ".csv" else csv.excel_tab
    delimiter = dialect.delimiter
    # StringIO 保留引号字段中的换行，避免用 splitlines 破坏合法 CSV 记录。
    rows = list(csv.reader(io.StringIO(text, newline=""), dialect=dialect))
    if len(rows) < opts.header_row:
        result.statuses.append(FileStatus(
            str(path), "分隔文本", status="跳过",
            message=f"文件不足 {opts.header_row} 行，无法读取表头"))
        return
    header_values = rows[opts.header_row - 1]
    if not any(not _blank(value) for value in header_values):
        result.statuses.append(FileStatus(
            str(path), "分隔文本", status="跳过",
            message=f"第 {opts.header_row} 行没有表头"))
        return
    max_columns = max([len(header_values)] + [len(row) for row in rows[opts.header_row:]])
    raw_headers = list(header_values) + [None] * (max_columns - len(header_values))
    keys, names, header_warnings = _prepare_headers(raw_headers)
    for warning in header_warnings:
        result.warnings.append(f"{path.name} / 分隔文本：{warning}")
    for key, name in zip(keys, names):
        display_names.setdefault(key, name)
    key_orders.append(keys)

    count = 0
    for row_number, raw in enumerate(rows[opts.header_row:], start=opts.header_row + 1):
        values = list(raw) + [None] * (max_columns - len(raw))
        if opts.skip_empty_rows and all(_blank(value) for value in values):
            continue
        source = {
            "来源文件夹": str(path.parent),
            "来源文件": path.name,
            "来源工作表": "分隔文本",
            "原始行号": row_number,
            "__values__": {key: value for key, value in zip(keys, values)},
        }
        records.append((source, values))
        count += 1
    delimiter_name = {",": "逗号", "\t": "制表符", ";": "分号", "|": "竖线"}.get(
        delimiter, repr(delimiter))
    result.statuses.append(FileStatus(
        str(path), "分隔文本", rows=count, columns=len(keys),
        message=f"编码 {encoding}，{delimiter_name}分隔"))


def _decode_delimited(data: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return data.decode(encoding), encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError("无法识别文本编码（支持 UTF-8、UTF-16、GB18030）")


def _resolve_sample_key(data_keys, display_names, requested):
    if requested:
        wanted = _normalise_header(requested)
        for key in data_keys:
            if key == wanted or _normalise_header(display_names[key]) == wanted:
                return key
        raise ValueError(f"未找到指定的样品名列“{requested}”，请检查表头名称")
    aliases = {_normalise_header(name) for name in SAMPLE_NAME_ALIASES}
    for key in data_keys:
        if _normalise_header(display_names[key]) in aliases:
            return key
    raise ValueError(
        "未自动识别到样品名列；请在提取设置中填写实际列名，例如“样品名称”")


def _natural_sort_key(value):
    if _blank(value):
        return (1, ())
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (0, ((0, float(value)),))
    text = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    tokens = tuple((0, int(part)) if part.isdigit() else (1, part)
                   for part in re.split(r"(\d+)", text) if part)
    return (0, tokens)


def _extract_sheet(path, ws, opts, result, records, display_names, key_orders) -> None:
    header_values = next(ws.iter_rows(min_row=opts.header_row, max_row=opts.header_row,
                                      values_only=True), None)
    if not header_values or not any(not _blank(v) for v in header_values):
        result.statuses.append(FileStatus(str(path), ws.title, status="跳过",
                                          message=f"第 {opts.header_row} 行没有表头"))
        return

    last = max(i for i, value in enumerate(header_values) if not _blank(value)) + 1
    raw_headers = list(header_values[:last])
    keys, names, header_warnings = _prepare_headers(raw_headers)
    for warning in header_warnings:
        result.warnings.append(f"{path.name} / {ws.title}：{warning}")
    for key, name in zip(keys, names):
        display_names.setdefault(key, name)
    key_orders.append(keys)

    count = 0
    folder_label = str(path.parent)
    for row_number, raw in enumerate(
            ws.iter_rows(min_row=opts.header_row + 1, max_col=last, values_only=True),
            start=opts.header_row + 1):
        values = list(raw)
        if opts.skip_empty_rows and all(_blank(v) for v in values):
            continue
        value_map = {key: value for key, value in zip(keys, values)}
        source = {
            "来源文件夹": folder_label,
            "来源文件": path.name,
            "来源工作表": ws.title,
            "原始行号": row_number,
            "__values__": value_map,
        }
        records.append((source, values))
        count += 1
    result.statuses.append(FileStatus(str(path), ws.title, rows=count, columns=len(keys),
                                      message="无数据行" if count == 0 else ""))


def _prepare_headers(values: list[object]) -> tuple[list[str], list[str], list[str]]:
    keys, names, warnings = [], [], []
    used: dict[str, int] = {}
    for index, value in enumerate(values, 1):
        name = str(value).strip() if not _blank(value) else f"未命名列_{index}"
        if _blank(value):
            warnings.append(f"第 {index} 列表头为空，已命名为“{name}”")
        base = _normalise_header(name)
        number = used.get(base, 0) + 1
        used[base] = number
        key = base if number == 1 else f"{base}__{number}"
        if number > 1:
            renamed = f"{name}_{number}"
            warnings.append(f"表头“{name}”重复，已命名为“{renamed}”")
            name = renamed
        keys.append(key)
        names.append(name)
    return keys, names, warnings


def export_merged_workbook(path: str | os.PathLike, result: MergeResult) -> None:
    """原子写出合并结果和处理日志，避免中途失败留下不完整文件。"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    target = Path(path)
    if target.suffix.lower() != ".xlsx":
        target = target.with_suffix(".xlsx")
    if not result.headers or not result.rows:
        raise ValueError("没有可导出的合并数据")
    if len(result.rows) + 1 > EXCEL_MAX_ROWS:
        raise ValueError(f"数据共 {len(result.rows):,} 行，超过单个 Excel 工作表上限")
    target.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook(write_only=False)
    ws = wb.active
    ws.title = "合并数据"
    ws.append(result.headers)
    for row in result.rows:
        ws.append(row)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    fill = PatternFill("solid", fgColor="1F4E78")
    for cell in ws[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center")
    for idx, header in enumerate(result.headers, 1):
        ws.column_dimensions[get_column_letter(idx)].width = min(max(len(header) + 2, 12), 32)

    log = wb.create_sheet("合并日志")
    log.append(["状态", "文件路径", "工作表", "提取行数", "列数", "说明"])
    for status in result.statuses:
        log.append([status.status, status.path, status.sheet, status.rows,
                    status.columns, status.message])
    for warning in result.warnings:
        log.append(["警告", "", "", "", "", warning])
    log.freeze_panes = "A2"
    log.auto_filter.ref = log.dimensions
    for cell in log[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = fill

    fd, temp_name = tempfile.mkstemp(prefix="excel_merge_", suffix=".xlsx",
                                     dir=str(target.parent))
    os.close(fd)
    try:
        wb.save(temp_name)
        os.replace(temp_name, target)
    finally:
        wb.close()
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _normalise_header(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).strip().casefold().split())


def _normalise_sheet_text(value: str) -> str:
    """工作表匹配忽略大小写和全半角，但保留名称内部空格。"""
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _normalise_filename_text(value: str) -> str:
    """文件名筛选忽略大小写、全半角和首尾空格。"""
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _resolved(path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))
