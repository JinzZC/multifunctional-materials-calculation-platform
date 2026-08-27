"""ui/csv_export.py 测试（不依赖 QApplication 的部分）。"""

import csv

from fiber_tensile.ui.csv_export import export_csv


def test_export_csv_utf8_bom(tmp_path):
    path = tmp_path / "out.csv"
    headers = ["编号", "值"]
    rows = [["1", 2.5], ["2", 3.7]]
    export_csv(str(path), headers, rows)

    data = path.read_bytes()
    assert data[:3] == b"\xef\xbb\xbf"      # UTF-8 BOM，Excel 直接打开不乱码
    text = path.read_text(encoding="utf-8-sig")
    assert "编号" in text and "2.5" in text

    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        assert list(reader) == [["编号", "值"], ["1", "2.5"], ["2", "3.7"]]


def test_export_csv_neutralises_spreadsheet_formulas(tmp_path):
    path = tmp_path / "safe.csv"
    export_csv(str(path), ["样品名", "备注"], [["=1+1", "@SUM(A1:A2)"], ["正常", -2.5]])
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[1] == ["'=1+1", "'@SUM(A1:A2)"]
    assert rows[2] == ["正常", "-2.5"]
