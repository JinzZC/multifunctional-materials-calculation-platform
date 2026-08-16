"""config.py 工具函数测试。"""

from fiber_tensile.config import sanitize_filename


def test_sanitize_filename():
    assert sanitize_filename("批次A/B:C") == "批次A_B_C"
    assert sanitize_filename('含"引号"名') == "含_引号_名"
    assert sanitize_filename("正常名字") == "正常名字"


def test_sanitize_filename_fallback():
    assert sanitize_filename("   ") == "报告"
    assert sanitize_filename("\\/:") == "___"
