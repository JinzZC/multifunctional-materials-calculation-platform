"""UI 冒烟测试：无人工交互验证全流程，随后自动退出。

运行方式（本机必须用 py 启动器）：
    py -3 scripts/smoke_ui.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QMessageBox, QTableWidgetItem

# 界面偏好隔离到临时 ini，避免污染真实用户设置
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tempfile.gettempdir())

# 冒烟测试中自动确认所有弹窗，避免阻塞
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

from fiber_tensile.core.statistics import batch_statistics
from fiber_tensile.core.weibull import weibull_fit
from fiber_tensile.data.db import open_database
from fiber_tensile.data.repository import get_batch, get_strengths, list_batches
from fiber_tensile.fileio.exporter_excel import export_excel_report
from fiber_tensile.fileio.exporter_pdf import export_pdf_report
from fiber_tensile.logging_setup import setup_logging
from fiber_tensile.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    tmp_db = os.path.join(tempfile.gettempdir(), "fiber_smoke.db")
    if os.path.exists(tmp_db):
        os.remove(tmp_db)
    # 日志与数据库同目录
    import logging
    log_path = setup_logging(tmp_db)
    logging.getLogger("app").info("smoke 冒烟测试启动")
    assert os.path.exists(log_path), f"日志文件未创建：{log_path}"
    conn = open_database(tmp_db)
    win = MainWindow(conn)
    win.show()

    tab = win.entry_tab
    # 1. 锚点：10 cN / 7 μm → 2598.45 MPa（期望值由公式层计算，避免硬编码四舍五入偏差）
    from fiber_tensile.core.formulas import filament_strength_mpa
    expected = f"{filament_strength_mpa(10.0, 7.0):,.2f}"
    tab._spin_force.setValue(10.0)
    tab._combo_unit.setCurrentText("cN")
    tab._spin_dim.setValue(7.0)
    assert expected in tab._lbl_preview.text(), f"预览不符：{tab._lbl_preview.text()}"
    # 1b. 模式切换：纺织模式 10 cN / 2 dtex → 5 cN/dtex（维度输入框随注册表切换）
    tab._radio_modes["textile"].setChecked(True)
    tab._spin_force.setValue(10.0)
    tab._spin_dim.setValue(2.0)
    assert "5.0000 cN/dtex" in tab._lbl_preview.text(), f"纺织预览不符：{tab._lbl_preview.text()}"
    tab._radio_modes["filament"].setChecked(True)
    tab._spin_force.setValue(10.0)
    tab._spin_dim.setValue(7.0)
    # 2. 录入 5 条数据并保存
    for f, d in [(10.0, 7.0), (9.5, 7.2), (10.8, 6.8), (9.0, 7.1), (10.2, 6.9)]:
        tab._spin_force.setValue(f)
        tab._spin_dim.setValue(d)
        tab._add_sample()
    assert tab._table.rowCount() == 5
    tab._edit_batch_name.setText("冒烟测试批次")
    tab._save()
    assert tab._table.rowCount() == 0            # 保存后表格清空
    batches = list_batches(conn)
    assert len(batches) == 1 and batches[0].sample_count == 5

    # 3. 分析 Tab：统计与 Weibull
    ana = win.analysis_tab
    ana.refresh()
    assert ana._combo.count() == 2               # 未保存项 + 1 个批次
    ana._combo.setCurrentIndex(1)
    assert ana._stats_table.item(0, 1).text() == "5"      # N=5
    assert ana._lbl_m.text().startswith("Weibull 模数 m = "), ana._lbl_m.text()
    assert ana._lbl_sigma0.text().startswith("特征强度 σ₀ = "), ana._lbl_sigma0.text()
    # Weibull 图上应包含拟合直线方程标注
    canvas_texts = [t.get_text() for ax in ana._canvas.fig.axes for t in ax.texts]
    assert any("拟合直线方程" in t and "y = " in t for t in canvas_texts), canvas_texts
    # 图形操作工具栏按钮已中文化
    toolbar_texts = [a.text() for a in ana._toolbar.actions() if a.text()]
    assert "复位" in toolbar_texts and "保存图像" in toolbar_texts, toolbar_texts
    # 「子图」与「设置」使用中文对话框
    from fiber_tensile.ui.weibull_plot import ChineseNavigationToolbar
    assert isinstance(ana._toolbar, ChineseNavigationToolbar)
    from fiber_tensile.ui.plot_dialogs import AxesEditDialog, SubplotDialog
    dlg = SubplotDialog(ana._canvas.fig)
    assert dlg.windowTitle() == "子图布局设置" and len(dlg._spins) == 6
    dlg.close()
    dlg2 = AxesEditDialog(ana._canvas.fig.axes[0])
    assert dlg2.windowTitle() == "图形设置"
    dlg2.close()

    # 4. 导出两种报告（走与 UI 按钮相同的底层函数）
    batch = get_batch(conn, batches[0].id)
    strengths = get_strengths(conn, batches[0].id)
    stats, weibull = batch_statistics(strengths), weibull_fit(strengths)
    xlsx_path = os.path.join(tempfile.gettempdir(), "smoke_report.xlsx")
    pdf_path = os.path.join(tempfile.gettempdir(), "smoke_report.pdf")
    export_excel_report(xlsx_path, batch, stats, weibull)
    export_pdf_report(pdf_path, batch, stats, weibull)
    assert os.path.getsize(xlsx_path) > 1000
    assert open(pdf_path, "rb").read(5) == b"%PDF-"

    # 5. 历史 Tab：列表与明细
    hist = win.history_tab
    hist.refresh()
    assert hist._batch_table.rowCount() == 1
    hist._batch_table.selectRow(0)
    assert hist._detail_table.rowCount() == 5

    # 6. 界面偏好：默认单位读写、窗口几何保存
    from fiber_tensile.ui import prefs
    prefs.set_default_force_unit("N")
    assert prefs.default_force_unit() == "N"
    prefs.save_geometry(win.saveGeometry())
    assert prefs.load_geometry() is not None
    prefs.set_last_dir(tempfile.gettempdir())
    assert prefs.last_dir() == tempfile.gettempdir()

    # 7. 表面能模块：OWRK 计算保存 + 报告导出
    st = win.surface_tab
    st._radio_methods["owrk"].setChecked(True)
    assert st._btn_add_row.text() == "添加液体"
    # 公式以规范数学形式展示（真上下标 HTML），并有符号说明
    eq = st._lbl_equations.text()
    assert "<sub>S</sub>" in eq and "cosθ" in eq and "符号说明" in eq, eq
    assert st._table.horizontalHeaderItem(1).text() == "接触角 θ（度）"
    # Wu 法除号以分子/分母分数形式展示（分数线为 border-top）
    st._radio_methods["wu"].setChecked(True)
    eq_wu = st._lbl_equations.text()
    assert "border-top" in eq_wu and "<sub>S</sub>" in eq_wu, eq_wu
    st._radio_methods["owrk"].setChecked(True)
    assert "色散分量" in st._table.horizontalHeaderItem(3).text()
    assert "色散分量" in st._history.horizontalHeaderItem(2).text()
    st._edit_sample_name.setText("冒烟-PTFE")
    st._add_row()                                            # 第一次点击 → 默认水
    assert st._table.cellWidget(0, 0).currentText() == "水"
    assert st._table.item(0, 2).text() == "72.8"             # 参数已自动填充
    st._table.item(0, 1).setText("108")
    st._add_row()                                            # 第二次点击 → 自动换下一种液体
    assert st._table.cellWidget(1, 0).currentText() == "二碘甲烷"
    assert st._table.item(1, 2).text() == "50.8"
    st._table.item(1, 1).setText("77")
    st._add_row()                                            # 第三次 → 乙二醇
    assert st._table.cellWidget(2, 0).currentText() == "乙二醇"
    st._table.removeRow(2)                                   # 删掉多余行，保留两种液体
    st._save()
    assert st._history.rowCount() == 1
    # 结果标签与表头中的 γ 上下标以真上下标（富文本）显示
    gt = st._lbl_gt.text()
    assert "总表面能（" in gt and "19.50" in gt and "<sub>S</sub>" in gt, gt
    gd = st._lbl_gd.text()
    assert "色散分量（" in gd and "<sup>d</sup>" in gd, gd
    assert "<sup>d</sup>" in st._table.horizontalHeaderItem(3).text()
    assert st._per_table.rowCount() == 2
    process_text = st._txt_process.toPlainText()
    assert "计算过程（OWRK" in process_text and "最小二乘" in process_text, process_text
    # 过程内公式带真上标（Qt 序列化为 vertical-align:super）
    assert "vertical-align" in st._txt_process.toHtml()
    from fiber_tensile.surface_energy.ui import to_rich
    assert to_rich("γ_S^d") == "γ<sub>S</sub><sup>d</sup>"
    assert "γ<sub>" in to_rich("γ_SL")

    from fiber_tensile.surface_energy.exporters import (
        export_excel_report as se_xlsx, export_pdf_report as se_pdf)
    from fiber_tensile.surface_energy.repository import get_measurement
    mid = st._history_rows[0]["id"]
    row, points = get_measurement(conn, mid)
    se_path = os.path.join(tempfile.gettempdir(), "smoke_se.xlsx")
    se_pdf_path = os.path.join(tempfile.gettempdir(), "smoke_se.pdf")
    se_xlsx(se_path, row["sample_name"], row["method"], points)
    se_pdf(se_pdf_path, row["sample_name"], row["method"], points)
    assert os.path.getsize(se_path) > 1000
    assert open(se_pdf_path, "rb").read(5) == b"%PDF-"

    # 8. Zisman 法：γ_c 与拟合图（图包含临界表面张力标注）
    st._radio_methods["zisman"].setChecked(True)
    st._table.setRowCount(0)
    for gamma_l, cos_t in ((30.0, 0.8), (50.0, 0.4), (70.0, 0.0)):
        r = st._table.rowCount()
        st._table.insertRow(r)
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems([l["name"] for l in st._liquid_library()])
        st._table.setCellWidget(r, 0, combo)
        st._table.setItem(r, 1, QTableWidgetItem(f"{math.degrees(math.acos(cos_t)):g}"))
        st._table.setItem(r, 2, QTableWidgetItem(f"{gamma_l:g}"))
        st._table.setItem(r, 3, QTableWidgetItem(""))
        st._table.setItem(r, 4, QTableWidgetItem(""))
    st._save()
    assert st._history.rowCount() == 2
    assert "20.00" in st._lbl_gc.text(), st._lbl_gc.text()
    canvas_texts = [t.get_text() for ax in st._canvas.fig.axes for t in ax.texts]
    assert any("临界表面张力" in t for t in canvas_texts), canvas_texts
    assert "直线拟合" in st._txt_process.toPlainText()

    # 9. 模块导航栏：三个模块可切换并记忆，模块名过长自动换行
    assert win._nav.count() == 3
    assert win._nav.item(0).text() == "纤维拉伸强度分析模块"
    assert win._nav.item(1).text() == "接触角表面能模块"
    assert win._nav.item(2).text() == "复合材料基础计算模块"
    assert "多功能计算平台" in win.windowTitle()
    assert win._nav.wordWrap() is True
    # 各模块界面区块之间有可拖拽分隔条（QSplitter）
    from PySide6.QtWidgets import QSplitter
    for tab in (win.entry_tab, win.analysis_tab, win.history_tab, win.surface_tab,
                win.composites_tab):
        assert tab.findChild(QSplitter) is not None, type(tab).__name__

    # 10. 单丝曲线分析：平台校正（含 0.5mm 平台的合成曲线）
    ct = win.curve_tab
    ct._spin_diameter.setValue(5.4)
    ct._spin_gauge.setValue(25.0)
    import numpy as np
    from fiber_tensile.curve_analysis.core import analyze_curve
    k = 230e9 * (np.pi * (5.4e-6) ** 2 / 4) / 0.025 / 1000.0   # N/mm
    x = np.linspace(0, 0.95, 200)
    f = np.where(x <= 0.5, 0.0, k * (x - 0.5))
    ct._analyze(list(x), list(f))
    assert ct._lbl_e.text().startswith("弹性模量 E = 230.00 GPa"), ct._lbl_e.text()
    assert "1.800%" in ct._lbl_eps.text(), ct._lbl_eps.text()
    assert "平台" in ct._txt_process.toPlainText()
    ct._edit_sample_name.setText("冒烟-曲线")
    ct._save()
    assert ct._history.rowCount() == 1

    # 11. 复合材料基础计算：混合法则 + 体积分数（酸解法）
    cm = win.composites_tab
    cm._rom_vf.setValue(0.6)
    cm._edit_sample_name.setText("冒烟-ROM")
    cm._save_rom()
    assert cm._history.rowCount() == 1
    assert "139.40" in cm._rom_lbl.text() and "纵向模量" in cm._rom_lbl.text(), \
        cm._rom_lbl.text()
    assert "纵向模量" in cm._history.horizontalHeaderItem(2).text()
    cm._vf_radio_acid.setChecked(True)
    cm._vf_sample.setText("冒烟-VF")
    cm._vf_wf.setValue(0.65)
    cm._vf_rhoc.setValue(1.5)
    cm._save_vf()
    assert cm._history.rowCount() == 2
    vf_text = cm._vf_lbl.text()
    assert "纤维体积分数" in vf_text and "0.5587" in vf_text, vf_text
    # 孔隙率以百分比明确显示
    assert "孔隙率" in vf_text and "%" in vf_text, vf_text
    assert "孔隙率" in cm._history.horizontalHeaderItem(9).text()
    # 历史表列宽按表头内容自适应（防止长表头被裁切）
    assert cm._history.horizontalHeader().sectionSize(2) > 80
    assert st._history.horizontalHeader().sectionSize(2) > 80
    win._nav.setCurrentRow(1)
    assert win._stack.currentIndex() == 1
    win._nav.setCurrentRow(0)
    assert win._stack.currentIndex() == 0
    from fiber_tensile.ui import prefs
    prefs.set_last_module(1)
    assert prefs.last_module() == 1

    print("SMOKE OK：录入/统计/Weibull/历史/日志/偏好/表面能/模块导航 全部通过")
    QTimer.singleShot(300, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
