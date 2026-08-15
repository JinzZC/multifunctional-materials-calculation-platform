"""pytest 全局配置：无头 matplotlib 后端（Agg），避免测试环境弹窗。"""

import matplotlib

matplotlib.use("Agg")
