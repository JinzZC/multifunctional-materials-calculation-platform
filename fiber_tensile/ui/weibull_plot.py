"""嵌入 PySide6 的 matplotlib 画布（qtagg 后端）。"""

from PySide6.QtCore import Qt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ..plotting import build_weibull_figure

# matplotlib 导航工具栏按钮的中文化：{matplotlib 内部名: (按钮文字, 提示)}
_TOOLBAR_TEXTS = {
    "home": ("复位", "恢复原始视图"),
    "back": ("后退", "回到上一个视图"),
    "forward": ("前进", "到下一个视图"),
    "pan": ("平移", "拖动平移图形；右键缩放"),
    "zoom": ("缩放", "框选区域放大"),
    "configure_subplots": ("子图", "调整子图布局"),
    "edit_parameters": ("设置", "编辑图形参数"),
    "save_figure": ("保存图像", "保存图像为文件"),
}


def localize_toolbar(toolbar) -> None:
    """把 matplotlib 导航工具栏的按钮文字与提示改为中文。"""
    for name, (text, tip) in _TOOLBAR_TEXTS.items():
        action = getattr(toolbar, "_actions", {}).get(name)
        if action is not None:
            action.setText(text)
            action.setToolTip(tip)
    toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)


class MplCanvas(FigureCanvasQTAgg):
    """Weibull 拟合图画布：把构建好的图绘制到自身 Figure 上并刷新。"""

    def __init__(self, parent=None, width=7.5, height=5.5, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setMinimumSize(420, 320)

    def draw_weibull(self, series, labels=None, title="Weibull 分布拟合图",
                     sigma0_unit: str = "") -> None:
        build_weibull_figure(series, labels=labels, title=title,
                             sigma0_unit=sigma0_unit, fig=self.fig)
        self.draw()
