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


class BackgroundWidget(QWidget):
    """在普通控件后方绘制背景，不影响子控件交互。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()
        self.reload_background()

    def reload_background(self) -> None:
        custom = Path(prefs.background_path()) if prefs.background_path() else None
        selected = custom if custom is not None and custom.is_file() \
            else Path(asset_path("default_background.png"))
        self._pixmap = QPixmap(str(selected)) if prefs.background_enabled() else QPixmap()
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
        path_row = QHBoxLayout()
        self._path_label = QLabel()
        self._path_label.setWordWrap(True)
        self._refresh_path_label()
        choose = QPushButton("选择图片…")
        choose.clicked.connect(self._choose_image)
        default = QPushButton("恢复内置背景")
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

        tip = QLabel("建议将显示强度保持在 35%～60%，表格和输入框仍使用不透明底色，"
                     "不会影响数据阅读。自定义图片丢失时会自动回到内置背景。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #526579;")
        root.addWidget(tip)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _refresh_path_label(self) -> None:
        self._path_label.setText(self._path if self._path else "内置碳纤维/材料科学背景")

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择背景图片", prefs.last_dir(),
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self._path = path
            prefs.set_last_dir(str(Path(path).parent))
            self._refresh_path_label()

    def _use_default(self) -> None:
        self._path = ""
        self._refresh_path_label()

    def accept(self) -> None:
        prefs.set_background_enabled(self._enabled.isChecked())
        prefs.set_background_path(self._path)
        prefs.set_background_opacity(self._opacity.value())
        prefs.set_background_mode(self._mode.currentData())
        super().accept()
