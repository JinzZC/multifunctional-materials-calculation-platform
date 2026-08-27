import os

from scripts.build import _build_environment


def test_build_environment_removes_foreign_icu_directory(tmp_path, monkeypatch):
    foreign = tmp_path / "foreign"
    ordinary = tmp_path / "ordinary"
    foreign.mkdir()
    ordinary.mkdir()
    (foreign / "icuuc.dll").write_bytes(b"not a system ICU")

    monkeypatch.setenv("WINDIR", str(tmp_path / "Windows"))
    monkeypatch.setenv("PATH", os.pathsep.join((str(foreign), str(ordinary))))

    cleaned = _build_environment()["PATH"].split(os.pathsep)

    assert str(foreign) not in cleaned
    assert str(ordinary) in cleaned
