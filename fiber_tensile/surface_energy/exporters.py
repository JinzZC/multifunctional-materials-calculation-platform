"""表面能测量报告的 Excel/PDF 导出。

结构：测量信息 → 液体数据表 → 计算结果（按方法不同字段）→
各液体界面能/粘附功表 → Zisman 图（仅 Zisman 法）。
openpyxl/reportlab/matplotlib 均为函数内延迟导入。
"""

from datetime import datetime

from .core import METHOD_LABELS, compute_surface_energy

_SE_TABLE_HEADERS = ["液体名称", "γ_L(mN/m)", "γ^d(mN/m)", "γ^p(mN/m)", "接触角(°)"]
_PER_HEADERS = ["液体名称", "界面能 γ_SL(mN/m)", "粘附功 W_A(mN/m)"]


def _fmt(v, nd=2):
    return "—" if v is None else f"{v:.{nd}f}"


def _build_data_tables(method, points, result):
    """返回 (信息键值行, 液体数据行, 结果键值行, 每液体行)。"""
    liquid_rows = [[p.liquid_name, f"{p.gamma_total:g}",
                    _fmt(p.gamma_d, 2) if p.gamma_d is not None else "—",
                    _fmt(p.gamma_p, 2) if p.gamma_p is not None else "—",
                    f"{p.angle_deg:g}"] for p in points]
    result_rows = [("计算方法", METHOD_LABELS[method]), ("液体种数", str(len(points)))]
    if result.gamma_d is not None:
        result_rows.append(("色散分量 γ^d (mN/m)", _fmt(result.gamma_d)))
    if result.gamma_p is not None:
        result_rows.append(("极性分量 γ^p (mN/m)", _fmt(result.gamma_p)))
    if result.gamma_total is not None:
        result_rows.append(("总表面能 γ_S (mN/m)", _fmt(result.gamma_total)))
    if result.gamma_c is not None:
        result_rows.append(("临界表面张力 γ_c (mN/m)", _fmt(result.gamma_c)))
    if result.r2 is not None:
        result_rows.append(("拟合优度 R²", f"{result.r2:.4f}"))
    per_rows = []
    if result.per_liquid:
        per_rows = [[name, _fmt(gamma_sl), _fmt(wa)]
                    for name, gamma_sl, wa in result.per_liquid]
    return result_rows, liquid_rows, per_rows


def export_excel_report(path, sample_name: str, method: str, points: list,
                        remark=None, test_date=None) -> None:
    """导出 Excel 报告。"""
    from io import BytesIO

    import matplotlib.pyplot as plt
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    from .plotting import build_zisman_figure

    result = compute_surface_energy(method, points)
    result_rows, liquid_rows, per_rows = _build_data_tables(method, points, result)

    thin = Side(style="thin", color="B0B0B0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    bold = Font(bold=True)
    hdr_fill = PatternFill("solid", fgColor="DDEBF7")

    wb = Workbook()
    ws = wb.active
    ws.title = "表面能分析"
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 18

    def kv(row, k, v):
        ws.cell(row, 1, k).font = bold
        ws.cell(row, 2, v)
        return row + 1

    def table(wsx, row, headers, rows):
        for col, h in enumerate(headers, start=1):
            c = wsx.cell(row, col, h)
            c.font = bold
            c.fill = hdr_fill
            c.border = border
            c.alignment = Alignment(horizontal="center")
        row += 1
        for r in rows:
            for col, v in enumerate(r, start=1):
                wsx.cell(row, col, v).border = border
            row += 1
        return row

    row = 1
    c = ws.cell(row, 1, f"表面能分析报告 — {sample_name}")
    c.font = Font(bold=True, size=14)
    row += 2
    c = ws.cell(row, 1, "测量信息")
    c.font = Font(bold=True, size=12)
    row += 1
    for k, v in [("样品名称", sample_name), ("测试日期", test_date or "—"),
                 ("备注", remark or "—")]:
        row = kv(row, k, v)
    row += 1
    c = ws.cell(row, 1, "计算结果")
    c.font = Font(bold=True, size=12)
    row += 1
    for k, v in result_rows:
        row = kv(row, k, v)
    if method == "zisman":
        fig = build_zisman_figure(points, result.gamma_c, result.r2)
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150)
        plt.close(fig)
        img = XLImage(buf)
        img.width = 560
        img.height = 400
        ws.add_image(img, "D2")
    row += 1
    c = ws.cell(row, 1, "液体数据")
    c.font = Font(bold=True, size=12)
    row += 1
    row = table(ws, row, _SE_TABLE_HEADERS, liquid_rows)
    if per_rows:
        row += 1
        c = ws.cell(row, 1, "各液体界面能与粘附功")
        c.font = Font(bold=True, size=12)
        row += 1
        table(ws, row, _PER_HEADERS, per_rows)
    wb.save(path)


def export_pdf_report(path, sample_name: str, method: str, points: list,
                      remark=None, test_date=None) -> None:
    """导出 PDF 报告。"""
    from io import BytesIO

    import matplotlib.pyplot as plt
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    from .plotting import build_zisman_figure

    cjk = "STSong-Light"
    if cjk not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(cjk))

    title = ParagraphStyle("t", fontName=cjk, fontSize=16, leading=22,
                           alignment=1, spaceAfter=14)
    h2 = ParagraphStyle("h", fontName=cjk, fontSize=13, leading=18,
                        spaceBefore=14, spaceAfter=8,
                        textColor=colors.HexColor("#1F4E79"))
    body = ParagraphStyle("b", fontName=cjk, fontSize=10, leading=14)
    cell = ParagraphStyle("c", fontName=cjk, fontSize=9, leading=12)
    grid = TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B0B0B0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])

    def p(text, style=body):
        return Paragraph(str(text), style)

    result = compute_surface_energy(method, points)
    result_rows, liquid_rows, per_rows = _build_data_tables(method, points, result)

    doc = SimpleDocTemplate(str(path), pagesize=A4,
                            leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm,
                            title=f"表面能分析报告 - {sample_name}")
    story = [p("表面能分析报告", title),
             p(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
               ParagraphStyle("meta", parent=body, alignment=1, fontSize=9)),
             p("一、测量信息", h2)]
    story.append(Table([[p("样品名称"), p(sample_name)],
                        [p("测试日期"), p(test_date or "—")],
                        [p("备注"), p(remark or "—")]],
                       colWidths=[4 * cm, 11 * cm], style=grid))
    story.append(p("二、计算结果", h2))
    story.append(Table([[p(k), p(v)] for k, v in result_rows],
                       colWidths=[6 * cm, 9 * cm], style=grid))
    if method == "zisman":
        fig = build_zisman_figure(points, result.gamma_c, result.r2)
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150)
        plt.close(fig)
        story.append(Spacer(1, 0.3 * cm))
        story.append(Image(buf, width=14 * cm, height=10 * cm))
    story.append(p("三、液体数据", h2))
    story.append(Table([[p(h, cell) for h in _SE_TABLE_HEADERS]]
                       + [[p(v, cell) for v in r] for r in liquid_rows],
                       colWidths=[3.5 * cm] + [2.9 * cm] * 4, style=grid))
    if per_rows:
        story.append(p("四、各液体界面能与粘附功", h2))
        story.append(Table([[p(h, cell) for h in _PER_HEADERS]]
                           + [[p(v, cell) for v in r] for r in per_rows],
                           colWidths=[4 * cm, 5.5 * cm, 5.5 * cm], style=grid))
    doc.build(story)
