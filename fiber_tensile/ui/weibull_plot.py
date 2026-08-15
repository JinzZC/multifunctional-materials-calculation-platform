"""嵌入 PySide6 的 matplotlib 画布（qtagg 后端）。"""

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ..plotting import build_weibull_figure


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
