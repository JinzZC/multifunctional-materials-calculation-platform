"""PDF 报告导出（reportlab）。

中文方案：reportlab 内置 CID 字体 STSong-Light，开箱即用、无需打包字体文件。
注意 CID 字体没有粗体/斜体，标题层级用字号与颜色区分。

reportlab/matplotlib 均为函数内延迟导入，避免拖慢应用启动。
"""

from datetime import datetime

from ..core.models import MODE_LABELS
from ..core.modes import get_mode_spec
from ..core.weibull import rank_method_label, weibull_in_gpa, weibull_intercept, weibull_x_label
from .atomic import atomic_write_bytes

_CJK = "STSong-Light"


def _p(text, style) -> "Paragraph":
    import html as _html
    from reportlab.platypus import Paragraph

    # 转义用户文本中的 & < >，防止被 reportlab 当作标记解析
    return Paragraph(_html.escape(str(text)), style)


def export_pdf_report(path, batch, analysis=None, weibull=None) -> None:
    """导出一个批次的 PDF 报告。analysis/weibull 由调用方计算后传入。"""
    from io import BytesIO

    import matplotlib.pyplot as plt
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Image, SimpleDocTemplate, Spacer, Table, TableStyle

    from ..plotting import build_weibull_figure

    if _CJK not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(_CJK))

    title_style = ParagraphStyle("title", fontName=_CJK, fontSize=16, leading=22,
                                 alignment=1, spaceAfter=14)
    h2_style = ParagraphStyle("h2", fontName=_CJK, fontSize=13, leading=18,
                              spaceBefore=16, spaceAfter=8,
                              textColor=colors.HexColor("#1F4E79"))
    body_style = ParagraphStyle("body", fontName=_CJK, fontSize=10, leading=14)
    cell_style = ParagraphStyle("cell", fontName=_CJK, fontSize=9, leading=12)
    cell_small = ParagraphStyle("cellsm", fontName=_CJK, fontSize=8.5, leading=11)
    grid_style = TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B0B0B0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])

    spec = get_mode_spec(batch.mode)
    unit = spec.strength_unit
    weibull_error = "无法进行 Weibull 分析（至少需要 2 个有效且不完全相同的强度值）"
    if weibull is not None:
        try:
            weibull = weibull_in_gpa(weibull, unit, batch.density)
        except ValueError as exc:
            weibull_error = str(exc)
            weibull = None
    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"纤维拉伸强度分析报告 - {batch.batch_name}",
    )
    story = []
    story.append(_p("纤维拉伸强度分析报告", title_style))
    story.append(_p(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    ParagraphStyle("meta", parent=body_style, alignment=1, fontSize=9)))

    story.append(_p("一、批次信息", h2_style))
    info_rows = [
        ["批次名称", batch.batch_name],
        ["计算模式", MODE_LABELS[batch.mode]],
        ["纤维类型", batch.fiber_type or "—"],
        ["密度(g/cm³)", f"{batch.density:g}" if batch.density is not None else "—"],
        ["备注", batch.remark or "—"],
        ["创建时间", batch.created_at or "—"],
        ["样本数", str(batch.sample_count)],
    ]
    info_style = TableStyle(grid_style.getCommands() + [
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F6FB"))])
    story.append(Table([[_p(k, body_style), _p(v, body_style)] for k, v in info_rows],
                       colWidths=[4 * cm, 11 * cm], style=info_style))

    story.append(_p("二、统计结果", h2_style))
    if analysis is not None:
        headers = ["样本数 N", f"均值({unit})", f"标准差({unit})", "变异系数 CV%",
                   f"最小值({unit})", f"最大值({unit})"]
        vals = [
            str(analysis.n),
            f"{analysis.mean:.2f}",
            f"{analysis.std:.2f}" if analysis.std is not None else "—",
            f"{analysis.cv_percent:.2f}" if analysis.cv_percent is not None else "—",
            f"{analysis.min_val:.2f}",
            f"{analysis.max_val:.2f}",
        ]
        stats_style = TableStyle(grid_style.getCommands() + [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEBF7"))])
        story.append(Table([[_p(h, cell_style) for h in headers],
                            [_p(v, body_style) for v in vals]],
                           colWidths=[2.5 * cm] * 6, style=stats_style))
    else:
        story.append(_p("无数据", body_style))

    story.append(_p("三、Weibull 分析结果", h2_style))
    if weibull is not None:
        kv_rows = [
            ["排序概率方法", rank_method_label(weibull.rank_method)],
            ["Weibull 模数 m", f"{weibull.m:.4f}"],
            ["特征强度 σ₀(GPa)", f"{weibull.sigma0:.6g}"],
            ["位置参数 γ(GPa)", f"{weibull.gamma:.6g}"],
            ["横坐标 X", weibull_x_label(weibull)],
            ["拟合直线 y = m·x+a", f"m = {weibull.m:.6g}，a = {weibull_intercept(weibull):.6g}"],
            ["拟合优度 R²", f"{weibull.r2:.4f}"],
        ]
        story.append(Table([[_p(k, body_style), _p(v, body_style)] for k, v in kv_rows],
                           colWidths=[5 * cm, 10 * cm], style=grid_style))
        fig = build_weibull_figure([weibull], labels=[batch.batch_name], sigma0_unit="GPa")
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150)
        plt.close(fig)
        story.append(Spacer(1, 0.4 * cm))
        story.append(Image(buf, width=15 * cm, height=11 * cm))
    else:
        story.append(_p(weibull_error, body_style))

    story.append(_p("四、数据明细", h2_style))
    dim_col = spec.dim_label
    headers4 = ["编号", "断裂强力", "强力单位", dim_col, "密度(g/cm³)",
                f"强度({unit})", "强度(MPa)", "备注", "测试日期"]
    data_rows = [[_p(h, cell_small) for h in headers4]]
    for s in batch.samples:
        dim = getattr(s, spec.dim_field)
        data_rows.append([_p(v, cell_small) for v in [
            s.sample_no or "—",
            f"{s.breaking_force:g}",
            s.force_unit,
            f"{dim:g}",
            f"{batch.density:g}" if batch.density is not None else "—",
            f"{s.strength:.2f}" if s.strength is not None else "—",
            f"{s.strength_mpa:.2f}" if s.strength_mpa is not None else "—",
            (s.remark or "")[:40],
            s.test_date or "",
        ]])
    detail_style = TableStyle(grid_style.getCommands() + [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEBF7"))])
    story.append(Table(data_rows,
                       colWidths=[w * cm for w in [1.6, 2.0, 1.4, 2.0, 1.8, 2.2, 2.0, 2.4, 1.6]],
                       repeatRows=1, style=detail_style))

    doc.build(story)
    atomic_write_bytes(path, pdf_buffer.getvalue())
