"""随机生成纤维强力测试数据并走完整工具流程（参数化版）。

数据生成：Beta(4,3) 分布缩放到 [lo, hi]，期望均值 = lo + (hi-lo)×4/7。
默认参数即第一组测试数据（均值 1.4 cN、区间 [1, 1.7]、直径 5.4 μm）。

流程：生成导入文件 xlsx → 用工具的导入器解析校验 → 写入应用数据库
（应用「历史记录」中可直接查看）→ 统计/Weibull 拟合 → 导出 Excel/PDF 报告与拟合图 PNG。

用法示例：
    py -3 scripts/generate_test_data.py                                   # 默认：均值1.4，[1,1.7]
    py -3 scripts/generate_test_data.py --lo 10 --hi 17 --tag 14cN ^
        --seed 20260815 --batch "随机测试30根-φ5.4μm-14cN"                # 强力均值 14 cN
    py -3 scripts/generate_test_data.py --skip-db --n 50                  # 只生成文件，不入库
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib

matplotlib.use("Agg")

import numpy as np

from fiber_tensile.config import default_db_path
from fiber_tensile.core.models import MODE_FILAMENT, Batch
from fiber_tensile.core.statistics import batch_statistics
from fiber_tensile.core.weibull import weibull_fit
from fiber_tensile.data.db import open_database
from fiber_tensile.data.repository import add_samples, create_batch, get_batch, get_strengths
from fiber_tensile.fileio.exporter_excel import export_excel_report
from fiber_tensile.fileio.exporter_pdf import export_pdf_report
from fiber_tensile.fileio.importer import parse_file
from fiber_tensile.plotting import build_weibull_figure

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_data")


def parse_args():
    p = argparse.ArgumentParser(description="随机生成纤维强力测试数据并走完整工具流程")
    p.add_argument("--n", type=int, default=30, help="样本数（默认 30）")
    p.add_argument("--lo", type=float, default=1.0, help="强力下界 cN（默认 1.0）")
    p.add_argument("--hi", type=float, default=1.7, help="强力上界 cN（默认 1.7）")
    p.add_argument("--diameter", type=float, default=5.4, help="直径 μm（默认 5.4）")
    p.add_argument("--seed", type=int, default=20260814, help="随机种子（默认 20260814）")
    p.add_argument("--tag", default="", help="输出文件名标识，如 14cN（默认无）")
    p.add_argument("--batch", default=None, help="批次名称（默认 随机测试N根-φDμm[标签]）")
    p.add_argument("--skip-db", action="store_true", help="不写入应用数据库")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    rng = np.random.default_rng(args.seed)
    forces = np.round(args.lo + (args.hi - args.lo) * rng.beta(4.0, 3.0, args.n), 4)
    expected_mean = args.lo + (args.hi - args.lo) * 4.0 / 7.0

    tag = f"_{args.tag}" if args.tag else ""
    batch_name = args.batch or f"随机测试{args.n}根-φ{args.diameter:g}μm{tag}"
    os.makedirs(OUT_DIR, exist_ok=True)

    # 1. 生成导入文件（工具支持的导入格式）
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "数据"
    ws.append(["编号", "批次", "断裂强力", "强力单位", "直径(μm)", "备注", "测试日期"])
    for i, f in enumerate(forces, start=1):
        ws.append([f"R{i:02d}", batch_name, float(f), "cN", args.diameter,
                   f"随机生成(种子{args.seed})", "2026-08-14"])
    for col, width in zip("ABCDEFG", [8, 24, 12, 10, 10, 18, 12]):
        ws.column_dimensions[col].width = width
    import_path = os.path.join(OUT_DIR, f"随机测试{tag}_数据_{args.n}根.xlsx")
    wb.save(import_path)

    # 2. 用工具的导入器解析（顺带验证导入链路）
    preview = parse_file(import_path, mode=MODE_FILAMENT)
    assert preview.valid_rows == args.n and not preview.errors, (preview.valid_rows, preview.errors)

    # 3. 写入应用数据库（应用「历史记录」中可直接查看该批次）
    if not args.skip_db:
        conn = open_database(default_db_path())
        bid = create_batch(conn, Batch(
            batch_name=batch_name, mode=MODE_FILAMENT, fiber_type="测试纤维",
            remark=f"随机生成测试数据：均值{expected_mean:g}cN，区间[{args.lo:g},{args.hi:g}]，"
                   f"φ{args.diameter:g}μm，种子{args.seed}"))
        add_samples(conn, bid, preview.samples)
        batch = get_batch(conn, bid)
        strengths = get_strengths(conn, bid)
        conn.close()
    else:
        from fiber_tensile.core.formulas import compute_strength
        strengths = [compute_strength(MODE_FILAMENT, s.breaking_force, s.diameter_um)[0]
                     for s in preview.samples]
        batch = Batch(batch_name=batch_name, mode=MODE_FILAMENT,
                      samples=list(preview.samples), sample_count=len(preview.samples))

    # 4. 统计与 Weibull 拟合
    stats = batch_statistics(strengths)
    w = weibull_fit(strengths)

    # 5. 导出报告与拟合图
    export_excel_report(os.path.join(OUT_DIR, f"随机测试{tag}_分析报告.xlsx"), batch, stats, w)
    export_pdf_report(os.path.join(OUT_DIR, f"随机测试{tag}_分析报告.pdf"), batch, stats, w)
    fig = build_weibull_figure([w], labels=[batch_name], sigma0_unit="MPa")
    fig.savefig(os.path.join(OUT_DIR, f"随机测试{tag}_威布尔拟合图.png"), dpi=150)

    # 6. 结果输出：完整明细写入 UTF-8 文本文件，控制台仅打印 ASCII 摘要
    lines = [
        f"seed={args.seed}  n={args.n}  diameter_um={args.diameter:g}  "
        f"range_cn=[{args.lo:g},{args.hi:g}]",
        f"forces(cN) = {[float(f) for f in forces]}",
        f"force_mean={float(forces.mean()):.4f} (expected {expected_mean:g})  "
        f"force_min={float(forces.min()):.4f}  force_max={float(forces.max()):.4f}",
        f"stats(MPa): n={stats.n}  mean={stats.mean:.2f}  std={stats.std:.2f}  "
        f"cv%={stats.cv_percent:.2f}  min={stats.min_val:.2f}  max={stats.max_val:.2f}",
        f"weibull: m={w.m:.4f}  sigma0={w.sigma0:.2f} MPa  r2={w.r2:.4f}",
        "i   sigma(MPa)   F_hat        ln_sigma     y",
    ]
    for i, (s, f_hat, x, y) in enumerate(zip(
            w.strengths_sorted, w.median_ranks, w.x, w.y), start=1):
        lines.append(f"{i:2d}  {s:8.2f}  {f_hat:.8f}  {x:10.6f}  {y:10.6f}")
    with open(os.path.join(OUT_DIR, f"随机测试{tag}_分析结果.txt"), "w",
              encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print("\n".join(lines[:6]))
    print(f"files: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
