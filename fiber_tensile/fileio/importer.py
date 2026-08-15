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

from ..config import (
    RANGE_DENSITY_GCM3,
    RANGE_DIAMETER_UM,
    RANGE_FORCE_CN,
    RANGE_LINEAR_DENSITY_DTEX,
)
from ..core.models import (
    MODE_FILAMENT,
    MODE_TEXTILE,
    VALID_FORCE_UNITS,
    VALID_MODES,
    RowError,
    Sample,
)
from ..core.units import force_to_cn

# 规范列名 → (别名集合, 内部字段名)
_COLUMN_SPECS = [
    ("编号", {"编号", "样品编号", "样本号", "序号", "no", "sample_no", "id"}, "sample_no"),
    ("批次", {"批次", "批次号", "批次名称", "batch", "batch_name"}, "batch"),
    ("断裂强力", {"断裂强力", "强力", "断裂强力(n)", "断裂强力(cn)", "force", "f"}, "breaking_force"),
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


def _normalize(text: str) -> str:
    """NFKC 归一（全角→半角）+ 去空白 + 小写。"""
    return unicodedata.normalize("NFKC", text).strip().lower().replace(" ", "")


_ALIAS_MAP = {_normalize(a): key for _, aliases, key in _COLUMN_SPECS for a in aliases}
_CANONICAL_NAMES = {key: name for name, _, key in _COLUMN_SPECS}


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
        text = unicodedata.normalize("NFKC", str(raw)).strip()
        text = text.replace(",", "").replace(" ", "")
        try:
            value = float(text)
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


def read_table(path) -> "pd.DataFrame":
    """读取表格文件为 DataFrame（所有列保持原始 object 类型）。"""
    import pandas as pd   # 延迟导入：pandas 只在导入文件时加载，加快应用启动

    p = Path(path)
    if not p.exists():
        raise ImportFileError(f"文件不存在：{path}")
    suffix = p.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        return pd.read_excel(p, dtype=object)
    if suffix == ".xls":
        raise ImportFileError("暂不支持 .xls 旧格式，请在 Excel 中另存为 .xlsx 后再导入")
    if suffix in (".csv", ".txt"):
        data = p.read_bytes()
        for enc in ("utf-8-sig", "gb18030"):
            try:
                if suffix == ".csv":
                    return pd.read_csv(BytesIO(data), encoding=enc, dtype=object)
                # txt：由分隔符嗅探器处理制表符/逗号/空格
                return pd.read_csv(BytesIO(data), encoding=enc, dtype=object,
                                   sep=None, engine="python")
            except UnicodeDecodeError:
                continue
        raise ImportFileError("无法识别文件编码（尝试了 UTF-8 与 GB18030）")
    raise ImportFileError(f"不支持的文件格式：{suffix}（支持 .xlsx/.xlsm/.csv/.txt）")


def parse_file(path, mode: str | None = None) -> ImportPreview:
    """解析导入文件并逐行校验。

    mode 可选 'filament'/'textile'；缺省时按文件列自动推断：
    含直径列→单丝，含线密度列→纺织，两者都有或都没有→报错。
    """
    if mode is not None and mode not in VALID_MODES:
        raise ImportFileError(f"未知模式：{mode!r}")
    df = read_table(path)
    if df.shape[0] == 0:
        raise ImportFileError("文件没有数据行")

    mapping = _match_headers(df)
    if "breaking_force" not in mapping:
        raise ImportFileError("缺少必填列「断裂强力」")
    has_diameter = "diameter_um" in mapping
    has_dtex = "linear_density_dtex" in mapping

    if mode is None:
        if has_diameter and has_dtex:
            raise ImportFileError(
                "文件同时包含「直径(μm)」与「线密度(dtex)」列，请手动指定模式或删除多余列")
        if has_diameter:
            mode = MODE_FILAMENT
        elif has_dtex:
            mode = MODE_TEXTILE
        else:
            raise ImportFileError("缺少「直径(μm)」或「线密度(dtex)」列，无法确定计算模式")
    elif mode == MODE_FILAMENT and not has_diameter:
        raise ImportFileError("单丝模式需要「直径(μm)」列（若文件为线密度数据请改选纺织模式）")
    elif mode == MODE_TEXTILE and not has_dtex:
        raise ImportFileError("纺织模式需要「线密度(dtex)」列（若文件为直径数据请改选单丝模式）")

    preview = ImportPreview(inferred_mode=mode, total_rows=len(df))
    batch_values: set[str] = set()

    for idx, row in df.iterrows():
        row_number = idx + 2          # 第 1 行为表头
        errors: list = []
        warnings: list = []
        if all(_is_blank(v) for v in row.values):
            continue                 # 整行全空跳过

        sample_no = _parse_text(row[mapping["sample_no"]]) if "sample_no" in mapping else None
        force = _parse_number(row[mapping["breaking_force"]], "断裂强力", row_number, errors)
        unit = _parse_force_unit(
            row[mapping["force_unit"]] if "force_unit" in mapping else None, row_number, errors)

        diameter = dtex = density = test_date = None
        if mode == MODE_FILAMENT:
            diameter = _parse_number(row[mapping["diameter_um"]], "直径(μm)", row_number, errors)
            if diameter is not None:
                _warn_out_of_range(diameter, "直径(μm)", row_number,
                                   *RANGE_DIAMETER_UM, warnings)
        else:
            dtex = _parse_number(row[mapping["linear_density_dtex"]],
                                 "线密度(dtex)", row_number, errors)
            if dtex is not None:
                _warn_out_of_range(dtex, "线密度(dtex)", row_number,
                                   *RANGE_LINEAR_DENSITY_DTEX, warnings)
        if "density_gcm3" in mapping and not _is_blank(row[mapping["density_gcm3"]]):
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
            diameter_um=diameter if mode == MODE_FILAMENT else None,
            linear_density_dtex=dtex if mode == MODE_TEXTILE else None,
            sample_no=sample_no,
            remark=remark,
            test_date=test_date,
            density_gcm3=density,
        ))

    preview.valid_rows = len(preview.samples)
    if len(batch_values) == 1:
        preview.batch_from_file = batch_values.pop()
    return preview
