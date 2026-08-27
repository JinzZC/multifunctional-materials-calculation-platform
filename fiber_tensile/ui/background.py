"""可更换的低干扰应用背景及设置对话框。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from ..config import asset_path
from . import prefs

BUILTIN_BACKGROUNDS = (
    ("低干扰材料科学（推荐）", "science", "default_background.png"),
    ("霞光星海", "sunset", "background_sunset.jpg"),
    ("云海湖畔", "sky_lake", "background_sky_lake.jpg"),
)
_BUILTIN_FILES = {key: filename for _, key, filename in BUILTIN_BACKGROUNDS}

# Qt Widgets 不支持网页式 backdrop-filter；这里用多层半透明底色、柔和边框和
# 选中态模拟稳定的磨砂玻璃效果，同时保证表格数字在明暗背景上都清晰可读。
GLASS_STYLE = """
BackgroundWidget QTabWidget::pane {
    background-color: rgba(247, 250, 253, 178);
    border: 1px solid rgba(174, 196, 219, 205);
    border-radius: 7px;
}
BackgroundWidget QTabBar::tab {
    background-color: rgba(232, 241, 249, 205);
    border: 1px solid rgba(174, 196, 219, 190);
    padding: 7px 13px;
}
BackgroundWidget QTabBar::tab:selected {
    background-color: rgba(255, 255, 255, 225);
    color: #173F63;
}
BackgroundWidget QGroupBox {
    background-color: rgba(247, 251, 255, 184);
    border: 1px solid rgba(174, 196, 219, 210);
    border-radius: 7px;
    margin-top: 9px;
    padding-top: 7px;
}
BackgroundWidget QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #173F63;
    background-color: rgba(244, 249, 253, 218);
}
BackgroundWidget QLineEdit,
BackgroundWidget QSpinBox,
BackgroundWidget QDoubleSpinBox,
BackgroundWidget QDateEdit,
BackgroundWidget QComboBox {
    background-color: rgba(255, 255, 255, 196);
    border: 1px solid rgba(154, 181, 207, 220);
    border-radius: 4px;
    padding: 3px 5px;
    selection-background-color: #2E6F9E;
}
BackgroundWidget QLineEdit:focus,
BackgroundWidget QSpinBox:focus,
BackgroundWidget QDoubleSpinBox:focus,
BackgroundWidget QDateEdit:focus,
BackgroundWidget QComboBox:focus {
    background-color: rgba(255, 255, 255, 222);
    border: 1px solid #4D87B3;
}
BackgroundWidget QTableView,
BackgroundWidget QTableWidget,
BackgroundWidget QListView {
    background-color: rgba(250, 253, 255, 170);
    alternate-background-color: rgba(228, 239, 248, 158);
    border: 1px solid rgba(154, 181, 207, 210);
    border-radius: 5px;
    gridline-color: rgba(159, 184, 207, 170);
    selection-background-color: rgba(47, 111, 158, 210);
    selection-color: white;
}
BackgroundWidget QTableView::item,
BackgroundWidget QTableWidget::item,
BackgroundWidget QListView::item {
    background-color: rgba(255, 255, 255, 112);
}
BackgroundWidget QTableView::item:selected,
BackgroundWidget QTableWidget::item:selected,
BackgroundWidget QListView::item:selected {
    background-color: rgba(47, 111, 158, 218);
    color: white;
}
BackgroundWidget QHeaderView::section {
    background-color: rgba(222, 235, 247, 220);
    color: #173F63;
    border: 0;
    border-right: 1px solid rgba(154, 181, 207, 190);
    border-bottom: 1px solid rgba(154, 181, 207, 190);
    padding: 5px;
}
BackgroundWidget QTextEdit,
BackgroundWidget QPlainTextEdit,
BackgroundWidget QTextBrowser,
BackgroundWidget QScrollArea {
    background-color: rgba(250, 253, 255, 174);
    border: 1px solid rgba(174, 196, 219, 205);
    border-radius: 5px;
}
BackgroundWidget QScrollArea > QWidget > QWidget {
    background: transparent;
}
BackgroundWidget QPushButton {
    background-color: rgba(241, 247, 252, 218);
    border: 1px solid rgba(137, 168, 197, 220);
    border-radius: 4px;
    padding: 5px 10px;
}
BackgroundWidget QPushButton:hover {
    background-color: rgba(218, 234, 247, 235);
}
BackgroundWidget QPushButton:pressed {
    background-color: rgba(194, 218, 238, 238);
}
"""


class BackgroundWidget(QWidget):
    """在普通控件后方绘制背景，不影响子控件交互。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()
        self.reload_background()

    def reload_background(self) -> None:
        enabled = prefs.background_enabled()
        source = prefs.background_source()
        custom = Path(prefs.background_path()) if prefs.background_path() else None
        if source == "custom" and custom is not None and custom.is_file():
            selected = custom
        else:
            filename = _BUILTIN_FILES.get(source, "default_background.png")
            selected = Path(asset_path(filename))
        self._pixmap = QPixmap(str(selected)) if enabled else QPixmap()
        self.setStyleSheet(GLASS_STYLE if enabled else "")
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#F7FAFD"))
        if self._pixmap.isNull():
            return
        painter.setOpacity(prefs.background_opacity() / 100.0)
        mode = prefs.background_mode()
        if mode == "tile":
            painter.drawTiledPixmap(self.rect(), self._pixmap)
            return
        if mode == "center":
            x = (self.width() - self._pixmap.width()) // 2
            y = (self.height() - self._pixmap.height()) // 2
            painter.drawPixmap(x, y, self._pixmap)
            return
        aspect = (Qt.KeepAspectRatioByExpanding if mode == "cover"
                  else Qt.KeepAspectRatio)
        scaled = self._pixmap.scaled(
            self.size(), aspect, Qt.SmoothTransformation)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)


class BackgroundSettingsDialog(QDialog):
    """选择默认/自定义背景、透明度和缩放方式。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("背景设置")
        self.setMinimumWidth(520)
        self._path = prefs.background_path()

        root = QVBoxLayout(self)
        self._enabled = QCheckBox("启用界面背景")
        self._enabled.setChecked(prefs.background_enabled())
        root.addWidget(self._enabled)

        form = QFormLayout()
        self._source = QComboBox()
        for label, key, _ in BUILTIN_BACKGROUNDS:
            self._source.addItem(label, key)
        self._source.addItem("自定义图片", "custom")
        source_index = self._source.findData(prefs.background_source())
        self._source.setCurrentIndex(max(source_index, 0))
        self._source.currentIndexChanged.connect(self._refresh_path_label)
        form.addRow("背景选择：", self._source)

        path_row = QHBoxLayout()
        self._path_label = QLabel()
        self._path_label.setWordWrap(True)
        self._refresh_path_label()
        choose = QPushButton("选择图片…")
        choose.clicked.connect(self._choose_image)
        default = QPushButton("恢复推荐背景")
        default.clicked.connect(self._use_default)
        path_row.addWidget(self._path_label, 1)
        path_row.addWidget(choose)
        path_row.addWidget(default)
        form.addRow("背景图片：", path_row)

        opacity_row = QHBoxLayout()
        self._opacity = QSlider(Qt.Horizontal)
        self._opacity.setRange(5, 100)
        self._opacity.setValue(prefs.background_opacity())
        self._opacity_value = QLabel(f"{self._opacity.value()}%")
        self._opacity.valueChanged.connect(
            lambda value: self._opacity_value.setText(f"{value}%"))
        opacity_row.addWidget(self._opacity, 1)
        opacity_row.addWidget(self._opacity_value)
        form.addRow("显示强度：", opacity_row)

        self._mode = QComboBox()
        for label, key in (("填充窗口（推荐）", "cover"), ("完整适应", "contain"),
                           ("原始尺寸居中", "center"), ("平铺", "tile")):
            self._mode.addItem(label, key)
        index = self._mode.findData(prefs.background_mode())
        self._mode.setCurrentIndex(max(index, 0))
        form.addRow("显示方式：", self._mode)
        root.addLayout(form)

        tip = QLabel("建议将显示强度保持在 35%～60%。启用背景后，表格、输入框和"
                     "功能面板会自动使用半透明磨砂玻璃效果；自定义图片丢失时会"
                     "自动回到内置背景。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #526579;")
        root.addWidget(tip)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _refresh_path_label(self) -> None:
        if self._source.currentData() == "custom":
            self._path_label.setText(self._path if self._path else "尚未选择自定义图片")
        else:
            self._path_label.setText("随软件内置，分享和打包后仍可使用")

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择背景图片", prefs.last_dir(),
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self._path = path
            self._source.setCurrentIndex(self._source.findData("custom"))
            prefs.set_last_dir(str(Path(path).parent))
            self._refresh_path_label()

    def _use_default(self) -> None:
        self._source.setCurrentIndex(self._source.findData("science"))
        self._refresh_path_label()

    def accept(self) -> None:
        prefs.set_background_enabled(self._enabled.isChecked())
        prefs.set_background_source(self._source.currentData())
        prefs.set_background_path(self._path)
        prefs.set_background_opacity(self._opacity.value())
        prefs.set_background_mode(self._mode.currentData())
        super().accept()
