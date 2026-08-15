"""matplotlib 内置图形工具的中文替代对话框。

- SubplotDialog：子图边距/间距设置（替代英文版 SubplotToolQt，改动实时生效）
- AxesEditDialog：坐标轴编辑（替代英文版 figureoptions，保留核心功能）

注意：本应用的图形在切换批次时会按数据重建，这些设置只对当前视图生效。
"""

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QInputDialog, QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)


class SubplotDialog(QDialog):
    """子图布局设置：边距与子图间距，改动实时应用到图形。"""

    _FIELDS = [
        ("left", "左边距", 0.125),
        ("bottom", "下边距", 0.11),
        ("right", "右边距", 0.9),
        ("top", "上边距", 0.88),
        ("wspace", "水平间距", 0.2),
        ("hspace", "垂直间距", 0.2),
    ]

    def __init__(self, figure, parent=None):
        super().__init__(parent)
        self._figure = figure
        self.setWindowTitle("子图布局设置")
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._spins: dict = {}
        for key, label, default in self._FIELDS:
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1.0)
            spin.setDecimals(3)
            spin.setSingleStep(0.01)
            spin.setValue(default)
            spin.valueChanged.connect(self._apply)
            self._spins[key] = spin
            form.addRow(f"{label}：", spin)
        layout.addLayout(form)

        row = QHBoxLayout()
        btn_tight = QPushButton("紧致布局")
        btn_tight.clicked.connect(self._tight)
        btn_reset = QPushButton("重置")
        btn_reset.clicked.connect(self._reset)
        row.addWidget(btn_tight)
        row.addWidget(btn_reset)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _params(self) -> dict:
        return {key: spin.value() for key, spin in self._spins.items()}

    def _apply(self, *args) -> None:
        self._figure.subplots_adjust(**self._params())
        self._figure.canvas.draw_idle()

    def _tight(self) -> None:
        self._figure.tight_layout()
        self._figure.canvas.draw_idle()

    def _reset(self) -> None:
        for (_, _, default), spin in zip(self._FIELDS, self._spins.values()):
            spin.blockSignals(True)
            spin.setValue(default)
            spin.blockSignals(False)
        self._apply()


def _parse_optional(text: str):
    """空字符串 → None（自动），否则解析为 float。"""
    text = text.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"无法解析数值：{text!r}") from None


class AxesEditDialog(QDialog):
    """图形设置：标题、坐标轴标签、显示范围、对数刻度。"""

    def __init__(self, axes, parent=None):
        super().__init__(parent)
        self._axes = axes
        self.setWindowTitle("图形设置")
        self._init_ui()

    def _init_ui(self) -> None:
        ax = self._axes
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._edit_title = QLineEdit(ax.get_title())
        self._edit_xlabel = QLineEdit(ax.get_xlabel())
        self._edit_ylabel = QLineEdit(ax.get_ylabel())
        form.addRow("标题：", self._edit_title)
        form.addRow("X 轴标签：", self._edit_xlabel)
        form.addRow("Y 轴标签：", self._edit_ylabel)

        xlo, xhi = ax.get_xlim()
        ylo, yhi = ax.get_ylim()
        self._edit_xmin = QLineEdit(f"{xlo:.6g}")
        self._edit_xmax = QLineEdit(f"{xhi:.6g}")
        self._edit_ymin = QLineEdit(f"{ylo:.6g}")
        self._edit_ymax = QLineEdit(f"{yhi:.6g}")
        for edit in (self._edit_xmin, self._edit_xmax, self._edit_ymin, self._edit_ymax):
            edit.setPlaceholderText("留空 = 自动")
        form.addRow("X 轴下限：", self._edit_xmin)
        form.addRow("X 轴上限：", self._edit_xmax)
        form.addRow("Y 轴下限：", self._edit_ymin)
        form.addRow("Y 轴上限：", self._edit_ymax)

        self._chk_xlog = QCheckBox("X 轴对数刻度")
        self._chk_ylog = QCheckBox("Y 轴对数刻度")
        self._chk_xlog.setChecked(ax.get_xscale() == "log")
        self._chk_ylog.setChecked(ax.get_yscale() == "log")
        form.addRow(self._chk_xlog)
        form.addRow(self._chk_ylog)
        layout.addLayout(form)

        from PySide6.QtWidgets import QLabel
        layout.addWidget(QLabel("提示：切换批次后图形会重建，这里的设置不保留。"))

        buttons = QDialogButtonBox()
        btn_apply = buttons.addButton("应用并关闭", QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        if self._apply():
            self.accept()

    def _apply(self) -> bool:
        ax = self._axes
        try:
            xmin = _parse_optional(self._edit_xmin.text())
            xmax = _parse_optional(self._edit_xmax.text())
            ymin = _parse_optional(self._edit_ymin.text())
            ymax = _parse_optional(self._edit_ymax.text())
        except ValueError as e:
            QMessageBox.warning(self, "输入无效", str(e))
            return False

        ax.set_title(self._edit_title.text())
        ax.set_xlabel(self._edit_xlabel.text())
        ax.set_ylabel(self._edit_ylabel.text())

        for axis, lo, hi, lo_edit, hi_edit in (
                ("x", xmin, xmax, self._edit_xmin, self._edit_xmax),
                ("y", ymin, ymax, self._edit_ymin, self._edit_ymax)):
            if lo is None and hi is None:
                if axis == "x":
                    ax.autoscale(axis="x")
                else:
                    ax.autoscale(axis="y")
            else:
                cur_lo, cur_hi = ax.get_xlim() if axis == "x" else ax.get_ylim()
                if axis == "x":
                    ax.set_xlim(lo if lo is not None else cur_lo,
                                hi if hi is not None else cur_hi)
                else:
                    ax.set_ylim(lo if lo is not None else cur_lo,
                                hi if hi is not None else cur_hi)

        ax.set_xscale("log" if self._chk_xlog.isChecked() else "linear")
        ax.set_yscale("log" if self._chk_ylog.isChecked() else "linear")
        ax.figure.canvas.draw_idle()
        return True
