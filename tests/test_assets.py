"""应用视觉资源与打包配置测试。"""

from pathlib import Path

from fiber_tensile.config import asset_path
from fiber_tensile.ui.background import GLASS_STYLE
from scripts import build


def test_bundled_visual_assets_exist():
    for name in ("app_icon.png", "app_icon.ico", "default_background.png",
                 "background_sunset.jpg", "background_sky_lake.jpg"):
        path = Path(asset_path(name))
        assert path.is_file()
        assert path.stat().st_size > 1000


def test_build_includes_icon_and_assets():
    assert "--icon" in build._COMMON
    assert str(build.ICON) in build._COMMON
    assert "--add-data" in build._COMMON
    assert build.ICON.is_file()


def test_glass_style_covers_data_entry_widgets():
    assert "BackgroundWidget QTableView" in GLASS_STYLE
    assert "BackgroundWidget QLineEdit" in GLASS_STYLE
    assert "BackgroundWidget QGroupBox" in GLASS_STYLE
    assert "rgba(" in GLASS_STYLE
