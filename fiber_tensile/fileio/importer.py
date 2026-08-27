"""Excel/CSV/TXT 批量导入与逐行校验。

列名匹配：去空白、全角转半角（NFKC 归一）、忽略大小写后与规范列名/别名比对。
校验流水线：表头匹配 → 逐行解析 → 阻断性问题记入 errors（该行不导入），
非阻断问题（日期无法识别已置空、数值超出常见范围）记入 warnings。

行号约定：第 1 行为表头，数据行号从 2 开始。
"""

from __future__ import annotations

import datetime as dt
import math
import unicodedata
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from ..config import RANGE_DENSITY_GCM3, RANGE_FORCE_CN
from ..core.models import VALID_FORCE_UNITS, VALID_MODES, RowError, Sample
from ..core.modes import MODES, get_mode_spec
from ..core.units import force_to_cn

# 规范列名 → (别名集合, 内部字段名)
_COLUMN_SPECS = [
    ("编号", {"编号", "样品编号", "样本号", "序号", "no", "sample_no", "id"}, "sample_no"),
    ("批次", {"批次", "批次号", "批次名称", "batch", "batch_name"}, "batch"),
    ("断裂强力", {"断裂强力", "强力", "断裂强力(n)", "断裂强力(cn)",
                  "断裂强力(mn)", "force", "force(n)", "force(cn)",
                  "force(mn)", "load", "load(n)", "f"}, "breaking_force"),
    ("强力单位", {"强力单位", "单位", "unit"}, "force_unit"),
    ("直径(μm)", {"直径(μm)", "直径(um)", "直径", "diameter", "d"}, "diameter_um"),
    ("线密度(dtex)", {"线密度(dtex)", "线密度", "titer", "tt", "dtex"}, "linear_density_dtex"),
    ("密度(g/cm³)", {"密度(g/cm³)", "密度(g/cm3)", "密度", "rho", "density"}, "density_gcm3"),
    ("备注", {"备注", "说明", "remark"}, "remark"),
    ("测试日期", {"测试日期", "日期", "date", "test_date"}, "test_date"),
]

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日")


class ImportFileError(ValueError):
    """文件级错误（表头缺失、格式不支持等），无法继续导入。"""


@dataclass
class ImportPreview:
    """导入预览结果：有效样本 + 错误/警告列表。"""

    samples: list = field(default_factory=list)
    errors: list = field(default_factory=list)      # 阻断性错误，对应行不导入
    warnings: list = field(default_factory=list)    # 非阻断警告
    total_rows: int = 0                             # 数据行总数（不含表头）
    valid_rows: int = 0
    batch_from_file: str | None = None              # 文件"批次"列唯一值时预填批次名
    inferred_mode: str | None = None
    header_row: int = 1                            # 实际表头行（1-based）
    sheet_name: str | None = None
    column_mapping: dict = field(default_factory=dict)


def _normalize(text: str) -> str:
    """NFKC 归一（全角→半角）+ 去空白 + 小写。"""
    return unicodedata.normalize("NFKC", text).strip().lower().replace(" ", "")


_ALIAS_MAP = {_normalize(a): key for _, aliases, key in _COLUMN_SPECS for a in aliases}
_CANONICAL_NAMES = {key: name for name, _, key in _COLUMN_SPECS}
FIBER_IMPORT_FIELDS = tuple((key, _CANONICAL_NAMES[key]) for key in _CANONICAL_NAMES)
FIBER_HEADER_ALIASES = tuple(_ALIAS_MAP)


def _match_headers(df: pd.DataFrame) -> dict:
    """表头匹配：返回 {内部字段名: 原列标签}，重复列取第一个。"""
    mapping: dict = {}
    for col in df.columns:
        key = _ALIAS_MAP.get(_normalize(str(col)))
        if key and key not in mapping:
            mapping[key] = col
    return mapping


def _is_blank(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return isinstance(v, str) and not v.strip()


def parse_decimal_text(text: str) -> str:
    """数字文本归一：逗号后只有 1-2 位数字视为欧式小数（0,5→0.5、12,34→12.34），
    否则逗号按千分位剔除（1,234→1234）。"""
    import re

    t = unicodedata.normalize("NFKC", text).strip().replace(" ", "")
    if re.fullmatch(r"\d+,\d{1,2}", t):
        return t.replace(",", ".")
    return t.replace(",", "")


def _parse_text(raw) -> str | None:
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None
    text = str(raw).strip()
    return text or None


def _parse_number(raw, column: str, row_number: int, errors: list) -> float | None:
    """解析正数。支持千分位逗号、全角数字；失败记入 errors 并返回 None。"""
    if raw is None or (isinstance(raw, str) and not raw.strip()) \
            or (isinstance(raw, float) and math.isnan(raw)):
        errors.append(RowError(row_number, f"{column}为空", column, raw))
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        value = float(raw)
    else:
        try:
            value = float(parse_decimal_text(str(raw)))
        except ValueError:
            errors.append(RowError(row_number, f"{column}不是有效数字", column, raw))
            return None
    if not math.isfinite(value):
        errors.append(RowError(row_number, f"{column}不是有效数字", column, raw))
        return None
    if value <= 0:
        errors.append(RowError(row_number, f"{column}必须为正数", column, raw))
        return None
    return value


def _parse_date(raw):
    """解析日期为 'YYYY-MM-DD'。空值返回 None；无法识别抛 ValueError。"""
    if raw is None:
        return None
    if isinstance(raw, dt.datetime):
        return raw.strftime("%Y-%m-%d")
    if isinstance(raw, dt.date):
        return raw.strftime("%Y-%m-%d")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        # Excel 日期序列号（1900 日期系统）
        try:
            base = dt.datetime(1899, 12, 30)
            return (base + dt.timedelta(days=float(raw))).strftime("%Y-%m-%d")
        except (OverflowError, ValueError):
            raise ValueError(f"无法识别的日期：{raw!r}") from None
    text = unicodedata.normalize("NFKC", str(raw)).strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"无法识别的日期：{raw!r}")


def _parse_force_unit(raw, row_number: int, errors: list) -> str:
    if _is_blank(raw):
        return "cN"
    text = _parse_text(raw)
    if text is None:
        return "cN"
    norm = text.lower()
    aliases = {"cn": "cN", "n": "N", "mn": "mN", "牛": "N", "厘牛": "cN", "毫牛": "mN"}
    unit = aliases.get(norm, norm)
    if unit not in VALID_FORCE_UNITS:
        errors.append(RowError(
            row_number, f"强力单位无效：{text!r}（仅支持 cN/N/mN）", "force_unit", raw))
    return unit


def _warn_out_of_range(value: float, column: str, row_number: int,
                       lo: float, hi: float, warnings: list) -> None:
    if value < lo or value > hi:
        warnings.append(RowError(
            row_number, f"{column}超出常见范围 [{lo:g}, {hi:g}]，请确认数值无误", column, value))


def list_sheet_names(path) -> list[str]:
    """返回 Excel 工作表名称；文本文件返回空列表。"""
    import pandas as pd

    p = Path(path)
    if p.suffix.lower() not in (".xlsx", ".xlsm"):
        return []
    try:
        with pd.ExcelFile(p) as workbook:
            return list(workbook.sheet_names)
    except Exception as exc:
        raise ImportFileError(f"无法读取 Excel 工作表：{exc}") from exc


def _unique_headers(values) -> list[str]:
    """把空表头和重复表头转换为稳定、唯一的字符串名称。"""
    headers: list[str] = []
    counts: dict[str, int] = {}
    for index, raw in enumerate(values, 1):
        base = str(raw).strip() if not _is_blank(raw) else f"未命名列{index}"
        counts[base] = counts.get(base, 0) + 1
        headers.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return headers


def detect_header_row(raw_df, header_aliases=None, max_scan_rows: int = 30) -> int:
    """在原始表格中检测表头，返回 0-based 行号。

    优先匹配调用模块提供的表头别名；无别名时按文本单元格数量与数据行结构评分。
    """
    aliases = {_normalize(str(value)) for value in (header_aliases or ())}
    best_row = 0
    best_score = float("-inf")
    limit = min(len(raw_df), max_scan_rows)
    for row_index in range(limit):
        values = [value for value in raw_df.iloc[row_index].tolist() if not _is_blank(value)]
        if not values:
            continue
        normalized = [_normalize(str(value)) for value in values]
        alias_hits = sum(value in aliases for value in normalized)
        text_count = sum(isinstance(value, str) for value in values)
        unique_count = len(set(normalized))
        # 别名命中权重最高；文本多、名称不重复的行更像表头。越靠前略优先。
        score = alias_hits * 100 + text_count * 3 + unique_count - row_index * 0.01
        if aliases and alias_hits == 0:
            score -= 20
        if score > best_score:
            best_score = score
            best_row = row_index
    return best_row


def read_table(path, *, sheet_name=0, header_row: int | str | None = "auto",
               header_aliases=None) -> "pd.DataFrame":
    """读取表格并返回 DataFrame。

    ``header_row`` 为 1-based 行号，``"auto"`` 自动扫描前 30 行；所有列保持
    原始 object 类型。Excel 可用 ``sheet_name`` 指定工作表名称或索引。
    """
    import pandas as pd   # 延迟导入：pandas 只在导入文件时加载，加快应用启动

    p = Path(path)
    if not p.exists():
        raise ImportFileError(f"文件不存在：{path}")
    suffix = p.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        try:
            raw = pd.read_excel(p, sheet_name=sheet_name, header=None, dtype=object)
        except ValueError as exc:
            raise ImportFileError(f"找不到指定工作表：{sheet_name!r}") from exc
    elif suffix == ".xls":
        raise ImportFileError("暂不支持 .xls 旧格式，请在 Excel 中另存为 .xlsx 后再导入")
    elif suffix in (".csv", ".txt", ".tsv"):
        data = p.read_bytes()
        for enc in ("utf-8-sig", "gb18030"):
            try:
                sep = "," if suffix == ".csv" else "\t" if suffix == ".tsv" else None
                raw = pd.read_csv(
                    BytesIO(data), encoding=enc, dtype=object, header=None,
                    sep=sep, engine="python" if sep is None else "c")
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ImportFileError("无法识别文件编码（尝试了 UTF-8 与 GB18030）")
    else:
        raise ImportFileError(
            f"不支持的文件格式：{suffix}（支持 .xlsx/.xlsm/.csv/.txt/.tsv）")

    if raw.shape[0] == 0:
        return raw
    if header_row == "auto" or header_row is None:
        header_index = detect_header_row(raw, header_aliases)
    else:
        try:
            header_index = int(header_row) - 1
        except (TypeError, ValueError):
            raise ImportFileError("表头行必须是正整数或“自动识别”") from None
        if header_index < 0 or header_index >= len(raw):
            raise ImportFileError(f"表头行 {header_row} 超出文件范围")
    frame = raw.iloc[header_index + 1:].copy()
    frame.columns = _unique_headers(raw.iloc[header_index].tolist())
    frame.attrs["header_row"] = header_index + 1
    frame.attrs["sheet_name"] = str(sheet_name) if isinstance(sheet_name, str) else None
    return frame.reset_index(drop=True)


def _force_unit_from_header(header) -> str | None:
    text = _normalize(str(header))
    if "(mn)" in text or "毫牛" in text:
        return "mN"
    if "(cn)" in text or "厘牛" in text:
        return "cN"
    if "(n)" in text or text.endswith("力n"):
        return "N"
    return None


def parse_file(path, mode: str | None = None, *, sheet_name=0,
               header_row: int | str | None = "auto",
               column_mapping: dict[str, str] | None = None,
               default_force_unit: str | None = None) -> ImportPreview:
    """解析导入文件并逐行校验。

    mode 可选 'filament'/'textile'；缺省时按文件列自动推断：
    含直径列→单丝，含线密度列→纺织，两者都有或都没有→报错。
    """
    if mode is not None and mode not in VALID_MODES:
        raise ImportFileError(f"未知模式：{mode!r}")
    df = read_table(path, sheet_name=sheet_name, header_row=header_row,
                    header_aliases=_ALIAS_MAP)
    if df.shape[0] == 0:
        raise ImportFileError("文件没有数据行")

    mapping = _match_headers(df)
    if column_mapping:
        valid_keys = set(_CANONICAL_NAMES)
        unknown = set(column_mapping) - valid_keys
        if unknown:
            raise ImportFileError(f"列映射包含未知字段：{sorted(unknown)}")
        for key, source in column_mapping.items():
            if source and source not in df.columns:
                raise ImportFileError(f"列映射字段不存在：{source!r}")
            if source:
                mapping[key] = source
    if "breaking_force" not in mapping:
        raise ImportFileError("缺少必填列「断裂强力」")

    # 模式确定：按注册表中各模式的维度字段推断或校验
    mode_specs = list(MODES.values())
    if mode is None:
        present = [s for s in mode_specs if s.dim_field in mapping]
        if len(present) > 1:
            raise ImportFileError(
                "文件同时包含" + "与".join(f"「{s.dim_label}」" for s in present)
                + "列，请手动指定模式或删除多余列")
        if not present:
            raise ImportFileError(
                "缺少" + "或".join(f"「{s.dim_label}」" for s in mode_specs)
                + "列，无法确定计算模式")
        spec = present[0]
        mode = spec.key
    else:
        spec = get_mode_spec(mode)
        if spec.dim_field not in mapping:
            raise ImportFileError(
                f"{spec.label}需要「{spec.dim_label}」列"
                f"（若文件为其他维度数据请改选对应模式）")

    force_unit_hint = default_force_unit or _force_unit_from_header(
        mapping.get("breaking_force", "")) or "cN"
    if force_unit_hint not in VALID_FORCE_UNITS:
        raise ImportFileError("默认强力单位仅支持 cN/N/mN")
    preview = ImportPreview(
        inferred_mode=mode, total_rows=len(df),
        header_row=int(df.attrs.get("header_row", 1)),
        sheet_name=df.attrs.get("sheet_name"), column_mapping=dict(mapping))
    batch_values: set[str] = set()
    sample_numbers: dict[str, int] = {}

    for idx, row in df.iterrows():
        row_number = preview.header_row + idx + 1
        errors: list = []
        warnings: list = []
        if all(_is_blank(v) for v in row.values):
            continue                 # 整行全空跳过

        sample_no = _parse_text(row[mapping["sample_no"]]) if "sample_no" in mapping else None
        force = _parse_number(row[mapping["breaking_force"]], "断裂强力", row_number, errors)
        unit = _parse_force_unit(
            row[mapping["force_unit"]] if "force_unit" in mapping else force_unit_hint,
            row_number, errors)

        density = test_date = None
        dim = _parse_number(row[mapping[spec.dim_field]], spec.dim_label,
                            row_number, errors)
        if dim is not None:
            _warn_out_of_range(dim, spec.dim_label, row_number,
                               *spec.dim_range, warnings)
        if spec.uses_density and "density_gcm3" in mapping \
                and not _is_blank(row[mapping["density_gcm3"]]):
            density = _parse_number(row[mapping["density_gcm3"]], "密度(g/cm³)",
                                    row_number, errors)
            if density is not None:
                _warn_out_of_range(density, "密度(g/cm³)", row_number,
                                   *RANGE_DENSITY_GCM3, warnings)
        if "test_date" in mapping and not _is_blank(row[mapping["test_date"]]):
            try:
                test_date = _parse_date(row[mapping["test_date"]])
            except ValueError as e:
                test_date = None
                warnings.append(RowError(row_number, f"{e}，已置空", "test_date",
                                         row[mapping["test_date"]]))
        remark = _parse_text(row[mapping["remark"]]) if "remark" in mapping else None
        if "batch" in mapping:
            batch_text = _parse_text(row[mapping["batch"]])
            if batch_text:
                batch_values.add(batch_text)

        if sample_no:
            normalized_no = _normalize(sample_no)
            if normalized_no in sample_numbers:
                warnings.append(RowError(
                    row_number,
                    f"编号与第 {sample_numbers[normalized_no]} 行重复，请确认是否为重复试样",
                    "sample_no", sample_no))
            else:
                sample_numbers[normalized_no] = row_number

        if force is not None and unit in VALID_FORCE_UNITS:
            _warn_out_of_range(force_to_cn(force, unit), "断裂强力(cN)", row_number,
                               *RANGE_FORCE_CN, warnings)

        if errors:
            preview.errors.extend(errors)
            preview.warnings.extend(warnings)
            continue

        preview.warnings.extend(warnings)
        preview.samples.append(Sample(
            breaking_force=force,
            force_unit=unit,
            sample_no=sample_no,
            remark=remark,
            test_date=test_date,
            density_gcm3=density,
            **{spec.dim_field: dim},
        ))

    preview.valid_rows = len(preview.samples)
    if len(batch_values) == 1:
        preview.batch_from_file = batch_values.pop()
    return preview
