"""表面能测量数据的 CSV/Excel 批量导入。

文件格式（一个文件 = 一条测量记录，多行液体数据）：
    样品名称 | 方法 | 液体名称 | γ_L(mN/m) | γ^d(mN/m) | γ^p(mN/m) | 接触角(°) | 备注 | 测试日期
方法列可写中文别名（如 双液法）；γ^d/γ^p 按方法选填；液体名称、γ_L、接触角必填。
"""

import datetime as dt
import math
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from ..core.models import RowError
from ..fileio.importer import ImportFileError, parse_decimal_text, read_table
from .core import LiquidPoint, METHODS

_HEADER_ALIASES = {
    "sample_name": {"样品名称", "样品", "试样名称", "sample", "sample_name"},
    "method": {"方法", "计算方法", "method"},
    "liquid_name": {"液体名称", "液体", "测试液体", "liquid", "liquid_name"},
    "gamma_total": {"γl(mn/m)", "γ(mn/m)", "表面张力(mn/m)", "表面张力", "γl",
                    "gammal", "gamma_total"},
    "gamma_d": {"γ^d(mn/m)", "γd(mn/m)", "色散分量(mn/m)", "色散分量", "γd",
                "gammad", "gamma_d"},
    "gamma_p": {"γ^p(mn/m)", "γp(mn/m)", "极性分量(mn/m)", "极性分量", "γp",
                "gammap", "gamma_p"},
    "angle": {"接触角(°)", "接触角", "接触角度", "θ(°)", "θ", "angle", "angle_deg"},
    "remark": {"备注", "说明", "remark"},
    "test_date": {"测试日期", "日期", "date", "test_date"},
}

_METHOD_ALIASES = {
    "owrk": "owrk", "双液法": "owrk", "owrk双液法": "owrk", "owens-wendt": "owrk",
    "wu": "wu", "wu法": "wu", "调和": "wu", "调和平均": "wu", "调和平均法": "wu",
    "fowkes": "fowkes", "fowkes法": "fowkes",
    "zisman": "zisman", "zisman法": "zisman", "临界": "zisman", "临界表面张力": "zisman",
}

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日")


@dataclass
class ImportPreview:
    """导入预览：液体点数据 + 行错误/警告；method 为空时由界面让用户选择。"""

    sample_name: str | None = None
    method: str | None = None
    points: list = field(default_factory=list)
    remark: str | None = None
    test_date: str | None = None
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip().lower() \
        .replace(" ", "").replace("_", "")


# 注册表中的显示名（如「Wu 调和平均法」）也作为方法别名自动识别
for _key, _spec in METHODS.items():
    _METHOD_ALIASES[_norm(_spec.label)] = _key


_ALIAS_MAP = {_norm(a): key for key, aliases in _HEADER_ALIASES.items()
              for a in aliases}


def _match_headers(df) -> dict:
    mapping: dict = {}
    for col in df.columns:
        key = _ALIAS_MAP.get(_norm(str(col)))
        if key and key not in mapping:
            mapping[key] = col
    return mapping


def _is_blank(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return isinstance(v, str) and not v.strip()


def _parse_number(raw, column, row_number, errors, required=True, allow_zero=False):
    if raw is None or (isinstance(raw, str) and not raw.strip()) \
            or (isinstance(raw, float) and math.isnan(raw)):
        if required:
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
    if value < 0 or (value == 0 and not allow_zero):
        errors.append(RowError(row_number, f"{column}必须为正数", column, raw))
        return None
    return value


def _parse_angle(raw, row_number, errors):
    value = _parse_number(raw, "接触角(°)", row_number, errors)
    if value is None:
        return None
    if not 0.0 < value < 180.0:
        errors.append(RowError(row_number, "接触角必须在 0–180° 之间", "angle", raw))
        return None
    return value


def _parse_date(raw) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, dt.datetime):
        return raw.strftime("%Y-%m-%d")
    if isinstance(raw, dt.date):
        return raw.strftime("%Y-%m-%d")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        base = dt.datetime(1899, 12, 30)
        return (base + dt.timedelta(days=float(raw))).strftime("%Y-%m-%d")
    text = unicodedata.normalize("NFKC", str(raw)).strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"无法识别的日期：{raw!r}")


def _parse_method(raw, row_number, errors):
    if _is_blank(raw):
        return None
    text = unicodedata.normalize("NFKC", str(raw)).strip()
    key = _METHOD_ALIASES.get(_norm(text))
    if key is None:
        errors.append(RowError(row_number, f"无法识别的方法：{text!r}（支持 "
                                "OWRK双液法/Wu调和平均法/Fowkes法/Zisman法）",
                              "method", raw))
        return None
    return key


def parse_measurement_file(path) -> ImportPreview:
    """解析表面能数据文件；文件级错误（格式/表头）抛 ImportFileError。"""
    df = read_table(Path(path))
    if df.shape[0] == 0:
        raise ImportFileError("文件没有数据行")
    mapping = _match_headers(df)
    for required in ("liquid_name", "gamma_total", "angle"):
        if required not in mapping:
            raise ImportFileError(
                f"缺少必填列「{required}」（液体名称、γ_L、接触角为必填）")

    preview = ImportPreview()
    sample_names: set = set()
    methods: set = set()
    remark = test_date = None
    for idx, row in df.iterrows():
        row_number = idx + 2
        errors: list = []
        warnings: list = []

        if _is_blank(row[mapping["liquid_name"]]):
            errors.append(RowError(row_number, "液体名称为空", "liquid_name", None))
            liquid_name = ""
        else:
            liquid_name = str(row[mapping["liquid_name"]]).strip()
        gamma_total = _parse_number(row[mapping["gamma_total"]], "γ_L(mN/m)",
                                    row_number, errors)
        # 分量允许为 0（非极性液体的极性分量为 0）
        gamma_d = _parse_number(row[mapping["gamma_d"]], "γ^d(mN/m)", row_number,
                                errors, required=False, allow_zero=True) \
            if "gamma_d" in mapping else None
        gamma_p = _parse_number(row[mapping["gamma_p"]], "γ^p(mN/m)", row_number,
                                errors, required=False, allow_zero=True) \
            if "gamma_p" in mapping else None
        angle = _parse_angle(row[mapping["angle"]], row_number, errors)

        if "sample_name" in mapping and not _is_blank(row[mapping["sample_name"]]):
            sample_names.add(str(row[mapping["sample_name"]]).strip())
        if "method" in mapping:
            m = _parse_method(row[mapping["method"]], row_number, errors)
            if m:
                methods.add(m)
        if remark is None and "remark" in mapping and not _is_blank(row[mapping["remark"]]):
            remark = str(row[mapping["remark"]]).strip()
        if test_date is None and "test_date" in mapping \
                and not _is_blank(row[mapping["test_date"]]):
            try:
                test_date = _parse_date(row[mapping["test_date"]])
            except ValueError as e:
                warnings.append(RowError(row_number, f"{e}，已置空", "test_date",
                                         row[mapping["test_date"]]))

        if errors:
            preview.errors.extend(errors)
            preview.warnings.extend(warnings)
            continue
        preview.warnings.extend(warnings)
        preview.points.append(LiquidPoint(
            liquid_name=liquid_name, gamma_total=gamma_total, angle_deg=angle,
            gamma_d=gamma_d, gamma_p=gamma_p))

    preview.sample_name = next(iter(sample_names)) if len(sample_names) == 1 else (
        Path(path).stem if not sample_names else min(sample_names))
    if len(sample_names) > 1:
        preview.warnings.append(RowError(1, "文件中出现多个样品名称，已取第一个", "sample_name"))
    if len(methods) == 1:
        preview.method = methods.pop()
    elif len(methods) > 1:
        preview.errors.append(RowError(1, "文件中出现多种计算方法，请统一后重试", "method"))
    preview.remark = remark
    preview.test_date = test_date
    return preview
