"""Strict tabular import with explicit unit selection and row-level errors."""

import math
from numbers import Real
from pathlib import Path
import re
import unicodedata

from ..fileio.importer import read_table

FIELDS = (("x", "变形 / 工程应变 *"), ("force", "总力 / 载荷 *"))
FORCE_UNITS = {"N": 1.0, "kN": 1000.0, "cN": .01, "mN": .001}
X_UNITS = {"mm": 1.0, "μm": .001, "%": .01, "mm/mm": 1.0}
_X = ("应变", "工程应变", "strain", "位移", "伸长", "伸长量", "extension", "displacement", "x")
_F = ("力", "总力", "载荷", "负荷", "force", "load", "f")


def norm(text):
    return unicodedata.normalize("NFKC", str(text)).lower().replace(" ", "").replace("_", "").replace("μ", "u").replace("µ", "u")


ALIASES = tuple([* _X, * _F] + [f"{a}({u})" for a in _X for u in X_UNITS]
                + [f"{a}({u})" for a in _F for u in FORCE_UNITS])


def _base(header):
    return re.split(r"[([]", norm(header), maxsplit=1)[0]


def read_curve(path, *, source, x_unit, force_unit, sheet_name=0,
               header_row="auto", column_mapping=None, decimal_separator="."):
    if decimal_separator not in {".", ","}:
        raise ValueError("小数分隔符必须为点或逗号")
    if source not in {"strain", "extension", "crosshead"}:
        raise ValueError("拉伸需使用应变、标距伸长或横梁位移")
    if force_unit not in FORCE_UNITS or x_unit not in X_UNITS:
        raise ValueError("不支持的单位")
    if (source == "strain") != (x_unit in {"%", "mm/mm"}):
        raise ValueError("实测应变需选 % 或 mm/mm；伸长、位移需选 mm 或 μm")
    frame = read_table(Path(path), sheet_name=sheet_name, header_row=header_row, header_aliases=ALIASES)
    mapping = dict(column_mapping or {})
    if set(mapping) - {"x", "force"}:
        raise ValueError("未知映射字段")
    for key, aliases in (("x", _X), ("force", _F)):
        if not mapping.get(key):
            candidates = [c for c in frame.columns if _base(c) in {norm(a) for a in aliases}]
            if len(candidates) != 1:
                raise ValueError(f"{key} 列缺失或有多个候选，请使用自定义映射")
            mapping[key] = candidates[0]
        if mapping[key] not in frame.columns:
            raise ValueError(f"源文件不存在列：{mapping[key]}")
    if mapping["x"] == mapping["force"]:
        raise ValueError("变形与力不能映射到同一列")
    for key, unit in (("x", x_unit), ("force", force_unit)):
        match = re.search(r"[([]([^()\[\]]+)[)\]]", norm(mapping[key]))
        if match and match.group(1) in {norm(u) for u in (*X_UNITS, *FORCE_UNITS)} and match.group(1) != norm(unit):
            raise ValueError(f"列名 {mapping[key]} 的单位与所选 {unit} 不一致")
    x, force, errors = [], [], []
    start = int(frame.attrs.get("header_row", 1))
    for offset, (_, row) in enumerate(frame.iterrows(), start + 1):
        try:
            values = []
            for key in ("x", "force"):
                value = row[mapping[key]]
                if isinstance(value, bool):
                    raise ValueError("布尔值不是测量数值")
                if isinstance(value, Real):
                    number = float(value)
                else:
                    text = unicodedata.normalize("NFKC", str(value)).strip()
                    forbidden = "," if decimal_separator == "." else "."
                    if forbidden in text:
                        raise ValueError("数字分隔符与导入设置不符；不支持千分位，请确认小数点/逗号")
                    number = float(text.replace(",", "."))
                if not math.isfinite(number):
                    raise ValueError("空值或非有限值")
                values.append(number)
            x.append(values[0] * X_UNITS[x_unit])
            force.append(values[1] * FORCE_UNITS[force_unit])
        except (ValueError, TypeError) as exc:
            errors.append(f"第 {offset} 行：{exc}")
    if errors:
        raise ValueError("文件未导入，存在无效数据：\n" + "\n".join(errors[:20])
                         + (f"\n共 {len(errors)} 行错误" if len(errors) > 20 else ""))
    if len(x) < 5:
        raise ValueError("有效数据点不足 5 个")
    return x, force, {"file": str(Path(path).resolve()), "sheet_name": sheet_name,
                      "header_row": start, "column_mapping": mapping,
                      "x_unit": x_unit, "force_unit": force_unit,
                      "decimal_separator": decimal_separator}
