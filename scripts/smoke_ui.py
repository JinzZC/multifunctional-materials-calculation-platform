"""UI 冒烟测试：无人工交互验证全流程，随后自动退出。

运行方式（本机必须用 py 启动器）：
    py -3 scripts/smoke_ui.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

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
    tab._spin_diameter.setValue(7.0)
    assert expected in tab._lbl_preview.text(), f"预览不符：{tab._lbl_preview.text()}"
    # 1b. 模式切换：纺织模式 10 cN / 2 dtex → 5 cN/dtex
    tab._radio_textile.setChecked(True)
    tab._spin_force.setValue(10.0)
    tab._spin_dtex.setValue(2.0)
    assert "5.0000 cN/dtex" in tab._lbl_preview.text(), f"纺织预览不符：{tab._lbl_preview.text()}"
    tab._radio_filament.setChecked(True)
    tab._spin_force.setValue(10.0)
    tab._spin_diameter.setValue(7.0)
    # 2. 录入 5 条数据并保存
    for f, d in [(10.0, 7.0), (9.5, 7.2), (10.8, 6.8), (9.0, 7.1), (10.2, 6.9)]:
        tab._spin_force.setValue(f)
        tab._spin_diameter.setValue(d)
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

    print("SMOKE OK：录入/保存/统计/Weibull/报告导出/历史明细/日志/偏好 全部通过")
    QTimer.singleShot(300, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
