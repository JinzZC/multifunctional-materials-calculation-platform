"""Opt-in packaged verification with synthetic inputs and isolated user state."""

import json
from pathlib import Path


def run(output_path):
    from scripts.test_environment import isolated_environment

    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with isolated_environment() as root:
        import logging
        import numpy as np
        from PySide6.QtWidgets import QApplication
        from .config import APP_VERSION, default_db_path
        from .data.db import open_database
        from .ui.main_window import MainWindow
        from .ui.prefs import _settings
        from .mechanical.core import Spec, analyze
        from .mechanical.exporters import export_excel, export_pdf, export_csv
        from .mechanical.repository import save_entries, load_entry

        app = QApplication([])
        conn = open_database(default_db_path())
        win = None
        try:
            assert Path(_settings().fileName()).resolve().is_relative_to(root)
            win = MainWindow(conn)
            win.show()
            win._nav.setCurrentRow(5)
            app.processEvents()
            assert win._nav.count() == 6
            x = np.linspace(0, .02, 201).tolist()
            force = [v * 60000 for v in x]
            spec = Spec(fracture_point=201)
            result = analyze(x, force, spec)
            assert abs(result.modulus_gpa - 3) < 1e-9
            entry = dict(name="打包合成验证", x=x, force=force, spec=spec, result=result)
            record_id = save_entries(conn, [entry])[0]
            entry = load_entry(conn, record_id)
            win.mechanical_tab._add_entry(entry)
            win.mechanical_tab._table.selectRow(0)
            app.processEvents()
            for extension, exporter in (("xlsx", export_excel), ("pdf", export_pdf), ("csv", export_csv)):
                path = root / f"report.{extension}"
                exporter(path, [entry])
                assert path.stat().st_size > 100
            checks = dict(version=APP_VERSION, navigation=6, modulus_gpa=result.modulus_gpa,
                          database_isolated=True, settings_isolated=True,
                          exports=["xlsx", "pdf", "csv"], history=True)
            output.write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            if win is not None:
                win.close()
            conn.close()
            logging.shutdown()
    return 0
