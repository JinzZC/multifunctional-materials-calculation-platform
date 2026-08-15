"""生成一组基于文献真实接触角值的表面能测试数据。

数据来源：常见材料在标准液体上的文献接触角（PTFE/PE/PET/碳纤维/玻璃纤维
上的水、二碘甲烷、乙二醇、烷烃系列），叠加 ±1° 正态噪声模拟真实测量，
角值保留 0.1°。

输出（test_data/接触角测试数据/）：每种测量一个导入格式 xlsx + 汇总 txt；
用工具自带的导入器回读校验并计算各方法的预期结果。

用法：
    py -3 scripts/generate_se_test_data.py           # 只生成文件与汇总
    py -3 scripts/generate_se_test_data.py --to-db   # 同时导入应用数据库（历史记录可见）
"""

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from fiber_tensile.surface_energy.core import METHOD_LABELS, compute_surface_energy
from fiber_tensile.surface_energy.importer import parse_measurement_file
from fiber_tensile.surface_energy.repository import create_measurement

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "test_data", "接触角测试数据")

# 液体参数库（γ_L, γ^d, γ^p，mN/m，文献常用值）
LIQUIDS = {
    "水": (72.8, 21.8, 51.0),
    "二碘甲烷": (50.8, 50.8, 0.0),
    "乙二醇": (48.0, 29.0, 19.0),
    "十六烷": (27.6, 27.6, 0.0),
    "正己烷": (18.4, 18.4, 0.0),
    "正庚烷": (20.1, 20.1, 0.0),
    "正辛烷": (21.8, 21.8, 0.0),
    "正壬烷": (22.9, 22.9, 0.0),
    "正癸烷": (23.9, 23.9, 0.0),
    "正十二烷": (25.4, 25.4, 0.0),
}

# (样品名称, 方法, [(液体, 文献接触角 θ/°)], 备注)
MEASUREMENTS = [
    ("PTFE 薄膜", "owrk", [("水", 109.0), ("二碘甲烷", 79.0), ("乙二醇", 92.0)],
     "三液体最小二乘示例（文献 γ_S≈19.5）"),
    ("聚乙烯 PE", "owrk", [("水", 96.0), ("二碘甲烷", 54.0)],
     "文献 γ_S≈33~36"),
    ("聚酯 PET", "owrk", [("水", 75.0), ("二碘甲烷", 38.0)],
     "文献 γ_S≈43~45"),
    ("碳纤维（未上浆）", "owrk", [("水", 86.0), ("二碘甲烷", 56.0)],
     "文献 γ_S≈37~40"),
    ("碳纤维（上浆后）", "owrk", [("水", 62.0), ("二碘甲烷", 42.0)],
     "文献 γ_S≈44~48"),
    ("玻璃纤维", "owrk", [("水", 65.0), ("二碘甲烷", 35.0)],
     "文献 γ_S≈47~50"),
    ("PTFE 薄膜", "wu", [("水", 109.0), ("二碘甲烷", 79.0)],
     "调和平均法示例"),
    ("PTFE 薄膜", "fowkes", [("十六烷", 46.0)],
     "单液体色散分量示例（文献 γ^d≈18~20）"),
    ("PTFE 薄膜", "zisman",
     [("正己烷", 12.0), ("正庚烷", 21.0), ("正辛烷", 26.0), ("正壬烷", 32.0),
      ("正癸烷", 35.0), ("正十二烷", 42.0), ("十六烷", 46.0)],
     "烷烃同系物外推示例（文献 γ_c≈18.5）"),
]

_HEADERS = ["样品名称", "方法", "液体名称", "γ_L(mN/m)", "γ^d(mN/m)",
            "γ^p(mN/m)", "接触角(°)", "备注", "测试日期"]


def main() -> int:
    parser = argparse.ArgumentParser(description="生成接触角测试数据")
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--noise", type=float, default=1.0, help="角度噪声标准差(°)")
    parser.add_argument("--to-db", action="store_true", help="导入应用数据库")
    args = parser.parse_args()

    import openpyxl
    from fiber_tensile.config import default_db_path
    from fiber_tensile.data.db import open_database

    rng = np.random.default_rng(args.seed)
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = open_database(default_db_path()) if args.to_db else None

    summary_lines = [f"seed={args.seed}  noise_std={args.noise:g}°",
                     f"文件目录: {OUT_DIR}", ""]

    for i, (sample_name, method, liquids, remark) in enumerate(MEASUREMENTS, start=1):
        rows = []
        for lname, theta0 in liquids:
            theta = round(float(theta0 + rng.normal(0.0, args.noise)), 1)
            theta = max(0.1, min(179.0, theta))
            gt, gd, gp = LIQUIDS[lname]
            rows.append([sample_name, METHOD_LABELS[method], lname, gt, gd, gp,
                         theta, remark, "2026-08-15"])
        fname = f"{i:02d}_{sample_name}_{METHOD_LABELS[method]}.xlsx"
        path = os.path.join(OUT_DIR, fname)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "数据"
        ws.append(_HEADERS)
        for r in rows:
            ws.append(r)
        for col, width in zip("ABCDEFGHI", [16, 16, 10, 11, 11, 11, 10, 30, 11]):
            ws.column_dimensions[col].width = width
        wb.save(path)

        # 用工具自带的导入器回读校验 + 计算预期结果
        preview = parse_measurement_file(path)
        assert not preview.errors, (fname, preview.errors)
        result = compute_surface_energy(method, preview.points)
        parts = []
        if result.gamma_d is not None:
            parts.append(f"γ^d={result.gamma_d:.2f}")
        if result.gamma_p is not None:
            parts.append(f"γ^p={result.gamma_p:.2f}")
        if result.gamma_total is not None:
            parts.append(f"γ_S={result.gamma_total:.2f}")
        if result.gamma_c is not None:
            parts.append(f"γ_c={result.gamma_c:.2f}")
        if result.r2 is not None:
            parts.append(f"R²={result.r2:.4f}")
        line = f"[{i:02d}] {sample_name} | {METHOD_LABELS[method]} | " + " ".join(parts)
        summary_lines.append(line)
        print(line)
        if conn is not None:
            mid = create_measurement(conn, sample_name, method, preview.points,
                                     remark=remark, test_date="2026-08-15")
            print(f"    已导入数据库 (id={mid})")

    summary_path = os.path.join(OUT_DIR, "汇总_预期结果.txt")
    with open(summary_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(summary_lines))
    if conn is not None:
        conn.close()
    print(f"files: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
