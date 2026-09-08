"""UI behavior on synthetic data only; no real QSettings or database."""

import os
from threading import Event

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from fiber_tensile.data.db import open_database
from fiber_tensile.mechanical.core import Spec, analyze
from fiber_tensile.mechanical import ui


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    instance = QApplication.instance() or QApplication([])
    yield instance


@pytest.fixture
def tab(app, tmp_path, monkeypatch):
    conn = open_database(str(tmp_path / "ui.db"))
    widget = ui.MechanicalTab(conn)
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(args[-1]))
    widget._test_errors = errors
    yield widget
    widget.shutdown()
    widget.close()
    widget.deleteLater()
    app.processEvents()
    conn.close()


def add(tab, name="合成试样"):
    x = np.linspace(0, .02, 101).tolist()
    f = [v * 60000 for v in x]
    entry = {"name": name, "spec": Spec(), "x": x, "force": f, "result": analyze(x, f, Spec())}
    tab._add_entry(entry)
    return entry


def test_parameter_changes_block_stale_save_and_failed_fit_keeps_snapshot(tab):
    entry = add(tab)
    tab._table.selectRow(0)
    tab._lo.setValue(50)
    assert tab._dirty and not tab._save_button.isEnabled()
    tab._save()
    assert not tab._history_rows
    tab._recalculate()
    assert tab._test_errors
    assert tab._entries[0]["spec"] == entry["spec"]
    assert tab._dirty
    tab._lo.setValue(.1)
    tab._recalculate()
    assert not tab._dirty
    assert tab._entries[0]["spec"].fit_lo == .1
    tab._save()
    assert len(tab._history_rows) == 1


def test_tensile_only_controls(tab):
    assert {tab._source.itemData(i) for i in range(tab._source.count())} == {"strain", "extension", "crosshead"}
    assert set(tab._dims) == {"width_mm", "thickness_mm", "diameter_mm", "area_mm2", "gauge_mm"}
    assert tab._spec().mode == "tensile"


def test_saved_snapshot_not_overwritten_by_refitting(tab):
    add(tab)
    tab._table.selectRow(0)
    tab._save()
    original = tab._entries[0]["saved_id"]
    tab._target.setValue(.5)
    tab._recalculate()
    assert tab.has_unsaved()
    tab._save()
    assert len(tab._history_rows) == 2
    assert tab._entries[0]["saved_id"] != original


def test_unit_source_cannot_reinterpret_existing_curve(tab):
    add(tab)
    tab._table.selectRow(0)
    tab._source.setCurrentIndex(tab._source.findData("extension"))
    tab._recalculate()
    assert "变形来源" in tab._test_errors[-1]
    assert tab._entries[0]["spec"].source == "strain"


def test_manual_fracture_requires_per_sample_confirmation(tab):
    add(tab, "a")
    add(tab, "b")
    tab._table.selectAll()
    tab._fracture.setValue(101)
    tab._recalculate()
    assert "逐条" in tab._test_errors[-1]
    tab._table.clearSelection()
    tab._table.selectRow(0)
    tab._fracture.setValue(101)
    tab._recalculate()
    assert tab._entries[0]["result"].fracture_strain_pct == pytest.approx(2)


def test_cancel_finishes_current_file_and_skips_remaining(app, monkeypatch):
    entered, release = Event(), Event()
    calls, entries = [], []
    def read(path, **kwargs):
        calls.append(path)
        entered.set()
        assert release.wait(3)
        x = np.linspace(0, .01, 101)
        return x.tolist(), (x * 60000).tolist(), {}
    monkeypatch.setattr(ui, "read_curve", read)
    worker = ui.ImportWorker(["a", "b"], Spec(), {}, {"remark": "", "test_date": ""})
    worker.item.connect(entries.append)
    worker.start()
    try:
        assert entered.wait(3)
        worker.requestInterruption()
    finally:
        release.set()
        assert worker.wait(3000)
    app.processEvents()
    assert calls == ["a"]
    assert len(entries) == 1
