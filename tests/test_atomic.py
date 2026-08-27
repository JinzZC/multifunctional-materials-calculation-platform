"""导出原子写入工具测试。"""

from pathlib import Path

import pytest

from fiber_tensile.fileio.atomic import atomic_write


def test_atomic_write_replaces_target_only_after_success(tmp_path):
    target = tmp_path / "report.bin"
    target.write_bytes(b"old")
    atomic_write(target, lambda temporary: Path(temporary).write_bytes(b"new"))
    assert target.read_bytes() == b"new"


def test_atomic_write_preserves_existing_file_on_failure(tmp_path):
    target = tmp_path / "report.bin"
    target.write_bytes(b"old")

    def broken_writer(temporary):
        with open(temporary, "wb") as stream:
            stream.write(b"partial")
        raise RuntimeError("模拟导出失败")

    with pytest.raises(RuntimeError):
        atomic_write(target, broken_writer)
    assert target.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [target]
