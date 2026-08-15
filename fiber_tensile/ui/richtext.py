"""公式富文本助手：符号记号 → Qt 富文本真上下标；⟨分子|分母⟩ → 分数形式。

供各计算模块的公式展示、计算过程面板与表格表头共用。
HtmlHeaderView：以 HTML 富文本渲染表头文字（真上下标、前景色/字体取自
HeaderItem 的 ForegroundRole/FontRole）。
"""

import re

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAbstractTextDocumentLayout, QColor, QTextDocument
from PySide6.QtWidgets import QHeaderView

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


class HtmlHeaderView(QHeaderView):
    """以 HTML 富文本渲染表头文字的表头视图（支持真上下标）。

    文字颜色/字体取自 HeaderItem 的 ForegroundRole/FontRole（setForeground/
    setFont 依然生效）；背景固定为浅蓝、带边框。
    """

    def _doc_for(self, logical_index: int) -> QTextDocument:
        text = str(self.model().headerData(
            logical_index, self.orientation(), Qt.DisplayRole) or "")
        font = self.model().headerData(
            logical_index, self.orientation(), Qt.FontRole) or self.font()
        color = self.model().headerData(
            logical_index, self.orientation(), Qt.ForegroundRole)
        if color is None:
            color = QColor("#1F4E79")
        elif not isinstance(color, QColor):
            color = QColor(color.color())   # QBrush → QColor
        doc = QTextDocument()
        doc.setDefaultFont(font)
        doc.setHtml(f'<div align="center" style="color:{color.name()}">{text}</div>')
        return doc

    def paintSection(self, painter, rect, logical_index: int) -> None:
        painter.save()
        painter.fillRect(rect, QColor("#DDEBF7"))
        painter.setPen(QColor("#B0B0B0"))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        doc = self._doc_for(logical_index)
        painter.translate(
            rect.left() + 4,
            rect.top() + max(0, int((rect.height() - doc.size().height()) / 2)))
        painter.setClipRect(rect.adjusted(3, 2, -3, -2))
        ctx = QAbstractTextDocumentLayout.PaintContext()
        doc.documentLayout().draw(painter, ctx)
        painter.restore()

    def sectionSizeFromContents(self, logical_index: int) -> QSize:
        # 注意：不能调用基类实现——QHeaderView 的默认实现会回调
        # sizeHint/sectionSizeFromContents 造成无限递归
        doc = self._doc_for(logical_index)
        return QSize(int(doc.size().width()) + 16,
                     max(self.defaultSectionSize(), 32))

    def sizeHint(self) -> QSize:
        # 同样不能调用基类实现（递归风险），直接累加各列宽度
        total = 0
        for i in range(self.count()):
            total += self.sectionSizeFromContents(i).width()
        return QSize(max(total, 100), 32)
