"""Excel 报告导出（openpyxl）：统计汇总 / 数据明细 / Weibull 分析数据 三个 sheet。

openpyxl/matplotlib 均为函数内延迟导入，避免拖慢应用启动。
"""

from ..core.models import MODE_FILAMENT, MODE_LABELS, MODE_TEXTILE, strength_unit_label


def _styles():
    """延迟构建 openpyxl 样式对象。"""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    return (
        PatternFill("solid", fgColor="DDEBF7"),
        Font(bold=True),
        Border(left=Side(style="thin", color="B0B0B0"),
               right=Side(style="thin", color="B0B0B0"),
               top=Side(style="thin", color="B0B0B0"),
               bottom=Side(style="thin", color="B0B0B0")),
        Alignment,
    )


def _write_kv(ws, row: int, key, value, styles) -> int:
    _, bold, _, _ = styles
    ws.cell(row, 1, key).font = bold
    ws.cell(row, 2, value)
    return row + 1


def _write_table(ws, row: int, headers: list, rows: list, styles) -> int:
    hdr_fill, bold, border, alignment = styles
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row, col, h)
        c.font = bold
        c.fill = hdr_fill
        c.border = border
        c.alignment = alignment(horizontal="center")
    row += 1
    for r in rows:
        for col, v in enumerate(r, start=1):
            c = ws.cell(row, col, v)
            c.border = border
            if isinstance(v, (int, float)):
                c.number_format = "0.00"
        row += 1
    return row


def export_excel_report(path, batch, analysis=None, weibull=None) -> None:
    """导出一个批次的 Excel 报告。analysis/weibull 由调用方计算后传入。"""
    from io import BytesIO

    import matplotlib.pyplot as plt
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    from ..plotting import build_weibull_figure

    styles = _styles()
    unit = strength_unit_label(batch.mode)
    wb = Workbook()
    ws = wb.active
    ws.title = "统计汇总"
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 14

    row = 1
    c = ws.cell(row, 1, f"纤维拉伸强度分析报告 — {batch.batch_name}")
    c.font = Font(bold=True, size=14)
    row += 2
    c = ws.cell(row, 1, "批次信息")
    c.font = Font(bold=True, size=12)
    row += 1
    info = [
        ("批次名称", batch.batch_name),
        ("计算模式", MODE_LABELS[batch.mode]),
        ("纤维类型", batch.fiber_type or "—"),
        ("密度(g/cm³)", batch.density if batch.density is not None else "—"),
        ("备注", batch.remark or "—"),
        ("创建时间", batch.created_at or "—"),
        ("样本数", batch.sample_count),
    ]
    for k, v in info:
        row = _write_kv(ws, row, k, v, styles)
    row += 1

    c = ws.cell(row, 1, "统计结果")
    c.font = Font(bold=True, size=12)
    row += 1
    if analysis is not None:
        headers = ["样本数 N", f"均值({unit})", f"标准差({unit})", "变异系数 CV%",
                   f"最小值({unit})", f"最大值({unit})"]
        values = [
            analysis.n,
            round(analysis.mean, 2),
            round(analysis.std, 2) if analysis.std is not None else "—",
            round(analysis.cv_percent, 2) if analysis.cv_percent is not None else "—",
            round(analysis.min_val, 2),
            round(analysis.max_val, 2),
        ]
        row = _write_table(ws, row, headers, [values], styles)
    else:
        ws.cell(row, 1, "无数据")
        row += 1
    row += 1

    c = ws.cell(row, 1, "Weibull 分析结果")
    c.font = Font(bold=True, size=12)
    row += 1
    if weibull is not None:
        kv_rows = [
            ("Weibull 模数 m", round(weibull.m, 4)),
            (f"特征强度 σ₀({unit})", round(weibull.sigma0, 2)),
            ("拟合优度 R²", round(weibull.r2, 4)),
        ]
        if batch.mode == MODE_TEXTILE and batch.density is not None:
            kv_rows.append(("特征强度 σ₀(MPa)", round(weibull.sigma0 * batch.density * 100, 2)))
        for k, v in kv_rows:
            row = _write_kv(ws, row, k, v, styles)
        fig = build_weibull_figure([weibull], labels=[batch.batch_name], sigma0_unit=unit)
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150)
        plt.close(fig)
        img = XLImage(buf)
        img.width = 640
        img.height = 470
        ws.add_image(img, "E2")
    else:
        ws.cell(row, 1, "数据不足（Weibull 分析至少需要 2 个数据点）")

    # ---- Sheet2 数据明细 ----
    ws2 = wb.create_sheet("数据明细")
    dim_col = "直径(μm)" if batch.mode == MODE_FILAMENT else "线密度(dtex)"
    headers2 = ["编号", "断裂强力", "强力单位", dim_col, "密度(g/cm³)",
                f"强度({unit})", "强度(MPa)", "备注", "测试日期"]
    rows2 = []
    for s in batch.samples:
        dim = s.diameter_um if batch.mode == MODE_FILAMENT else s.linear_density_dtex
        rows2.append([
            s.sample_no or "—",
            s.breaking_force,
            s.force_unit,
            dim,
            batch.density if batch.density is not None else "—",
            round(s.strength, 2) if s.strength is not None else "—",
            round(s.strength_mpa, 2) if s.strength_mpa is not None else "—",
            s.remark or "",
            s.test_date or "",
        ])
    _write_table(ws2, 1, headers2, rows2, styles)
    ws2.freeze_panes = "A2"
    for i, w in enumerate([10, 11, 9, 13, 12, 13, 12, 22, 12], start=1):
        ws2.column_dimensions[get_column_letter(i)].width = w

    # ---- Sheet3 Weibull 分析数据 ----
    if weibull is not None:
        ws3 = wb.create_sheet("Weibull 分析数据")
        headers3 = ["序号 i", f"σ({unit})", "F̂(median rank)", "ln σ", "ln(−ln(1/(1−F̂)))"]
        rows3 = []
        for i, (s_val, f_hat, x, y) in enumerate(zip(
                weibull.strengths_sorted, weibull.median_ranks,
                weibull.x, weibull.y), start=1):
            rows3.append([i, round(s_val, 2), round(f_hat, 6), round(x, 6), round(y, 6)])
        _write_table(ws3, 1, headers3, rows3, styles)
        ws3.freeze_panes = "A2"
        for i, w in enumerate([8, 14, 16, 12, 18], start=1):
            ws3.column_dimensions[get_column_letter(i)].width = w

    wb.save(path)
