"""单丝拉伸曲线的 CSV/Excel 导入：位移列 + 力列。

列名匹配灵活（位移/伸长/extension、力/载荷/force 等）；单位转换由界面处理
（力统一转 N、位移统一转 mm 后再分析）。
"""

import math
import unicodedata
from pathlib import Path

from ..fileio.importer import ImportFileError, read_table

_HEADER_ALIASES = {
    "disp": {"位移", "位移(mm)", "位移(mm)", "伸长", "伸长量", "伸长(mm)",
             "extension", "displacement", "x", "横坐标"},
    "force": {"力", "力(n)", "载荷", "载荷(n)", "force", "load", "f", "y", "纵坐标"},
}


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip().lower() \
        .replace(" ", "").replace("_", "")


_ALIAS_MAP = {_norm(a): key for key, aliases in _HEADER_ALIASES.items()
              for a in aliases}


def _is_blank(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return isinstance(v, str) and not v.strip()


def parse_curve_file(path) -> tuple:
    """解析曲线文件，返回 (位移列表, 力列表)；文件级错误抛 ImportFileError。"""
    df = read_table(Path(path))
    if df.shape[0] == 0:
        raise ImportFileError("文件没有数据行")
    mapping: dict = {}
    for col in df.columns:
        key = _ALIAS_MAP.get(_norm(str(col)))
        if key and key not in mapping:
            mapping[key] = col
    for required in ("disp", "force"):
        if required not in mapping:
            raise ImportFileError(f"缺少必填列「{required}」（位移/伸长列与力/载荷列）")

    disp: list = []
    force: list = []
    errors: list = []
    for idx, row in df.iterrows():
        row_number = idx + 2

        def parse(v, label):
            if _is_blank(v):
                return None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
            text = unicodedata.normalize("NFKC", str(v)).strip().replace(",", "")
            try:
                return float(text)
            except ValueError:
                raise ValueError(f"第 {row_number} 行 {label} 不是有效数字：{v!r}")

        try:
            d = parse(row[mapping["disp"]], "位移")
            f = parse(row[mapping["force"]], "力")
        except ValueError as e:
            errors.append(str(e))
            continue
        if d is None or f is None:
            errors.append(f"第 {row_number} 行存在空值")
            continue
        if f < 0:
            errors.append(f"第 {row_number} 行力为负值")
            continue
        disp.append(d)
        force.append(f)
    if errors:
        raise ValueError("曲线数据有误：\n" + "\n".join(errors))
    if len(disp) < 5:
        raise ValueError("有效数据点不足（至少 5 个）")
    return disp, force
