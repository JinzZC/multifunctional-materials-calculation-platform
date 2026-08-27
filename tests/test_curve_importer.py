"""单丝曲线增强导入测试。"""

import openpyxl
import pytest

from fiber_tensile.curve_analysis.importer import parse_curve_file


def test_curve_custom_sheet_header_and_mapping(tmp_path):
    path = tmp_path / "curve.xlsx"
    workbook = openpyxl.Workbook()
    workbook.active.title = "说明"
    sheet = workbook.create_sheet("原始曲线")
    sheet.append(["仪器原始数据"])
    sheet.append(["Travel", "Load cell"])
    for index in range(5):
        sheet.append([index * 0.1, index * 0.2])
    workbook.save(path)

    displacement, force = parse_curve_file(
        path, sheet_name="原始曲线", header_row=2,
        column_mapping={"disp": "Travel", "force": "Load cell"})
    assert displacement == [0.0, 0.1, 0.2, 0.3, 0.4]
    assert force == pytest.approx([0.0, 0.2, 0.4, 0.6, 0.8])
