"""公式富文本助手：符号记号 → Qt 富文本真上下标；⟨分子|分母⟩ → 分数形式。

供各计算模块的公式展示与计算过程面板共用。
"""

import re

# 符号记号（γ_S^d 等）→ Qt 富文本真上下标
_RICH_RULES = [
    (re.compile(r"γ_([SLc])\^([dp])"), r"γ<sub>\1</sub><sup>\2</sup>"),
    (re.compile(r"W_A"), "W<sub>A</sub>"),
    (re.compile(r"γ_SL"), "γ<sub>SL</sub>"),
    (re.compile(r"γ_([SLc])"), r"γ<sub>\1</sub>"),
    (re.compile(r"\^([dp])"), r"<sup>\1</sup>"),
    # 通用下标（E_1、G_12、ν_f、ρ_c、w_f 等）
    (re.compile(r"_([0-9A-Za-z]{1,2})"), r"<sub>\1</sub>"),
]
_FRAC_RE = re.compile(r"⟨([^|⟩]*)\|([^⟩]*)⟩")


def _apply_symbols(text: str) -> str:
    """上下标记号 → 富文本（不处理分数）。"""
    for pattern, repl in _RICH_RULES:
        text = pattern.sub(repl, text)
    return text


def _fraction_html(num: str, den: str) -> str:
    """分子/分母形式的分数（嵌套表格 + 上边框分数线）。"""
    return (
        '<table border="0" cellspacing="0" cellpadding="0">'
        f'<tr><td align="center" style="padding:0 3px">{_apply_symbols(num)}</td></tr>'
        '<tr><td style="border-top:1px solid #333; padding:0 3px"></td></tr>'
        f'<tr><td align="center" style="padding:0 3px">{_apply_symbols(den)}</td></tr>'
        '</table>')


def to_rich(text: str) -> str:
    """⟨分子|分母⟩ → 分数表格；γ_S^d 等记号 → 真上下标。"""
    parts = _FRAC_RE.split(text)
    out = []
    for i in range(0, len(parts), 3):
        if parts[i]:
            out.append(_apply_symbols(parts[i]))
        if i + 2 < len(parts):
            out.append(_fraction_html(parts[i + 1], parts[i + 2]))
    return "".join(out)


def equation_line_html(line: str) -> str:
    """一条公式 → 单行表格：文本段与分数段交替、垂直居中对齐。"""
    parts = _FRAC_RE.split(line)
    cells = []
    for i in range(0, len(parts), 3):
        if parts[i]:
            cells.append(f'<td valign="middle" style="padding:0 3px">'
                         f"{_apply_symbols(parts[i])}</td>")
        if i + 2 < len(parts):
            cells.append(f'<td valign="middle" style="padding:0 3px">'
                         f"{_fraction_html(parts[i + 1], parts[i + 2])}</td>")
    return ('<table border="0" cellspacing="0" cellpadding="0"><tr>'
            + "".join(cells) + "</tr></table>")
