import zipfile

import pytest
from scripts import release as release_tool

from scripts.release import (APP_NAME, APP_VERSION, NAMES, local_assets,
                             prepare, sha256, verify_assets)


@pytest.fixture
def dist(tmp_path):
    folder = tmp_path / APP_NAME
    folder.mkdir()
    (folder / f"{APP_NAME}.exe").write_bytes(b"folder executable")
    (folder / "_internal").mkdir()
    (folder / "_internal" / "library.dll").write_bytes(b"dependency")
    (tmp_path / f"{APP_NAME}单文件版.exe").write_bytes(b"portable executable")
    return tmp_path


def test_prepare_preserves_chinese_executable_inside_versioned_zip(dist):
    output = prepare(dist)
    paths = local_assets(output)
    with zipfile.ZipFile(paths[0]) as archive:
        assert archive.testzip() is None
        assert archive.read(f"{APP_NAME}/{APP_NAME}.exe") == b"folder executable"
        assert archive.read(f"{APP_NAME}/_internal/library.dll") == b"dependency"
    assert paths[1].read_bytes() == b"portable executable"
    with pytest.raises(ValueError, match="已存在"):
        prepare(dist)


def test_prepare_rejects_user_data(dist):
    (dist / APP_NAME / "private.db").write_bytes(b"private")
    with pytest.raises(ValueError, match="用户数据"):
        prepare(dist)


def test_prepare_requires_both_builds(dist):
    (dist / f"{APP_NAME}单文件版.exe").unlink()
    with pytest.raises(ValueError, match="缺少"):
        prepare(dist)


def test_local_checksum_detects_modified_asset(dist):
    output = prepare(dist)
    (output / NAMES[1]).write_bytes(b"modified")
    with pytest.raises(ValueError, match="校验"):
        local_assets(output)


def test_upload_refuses_existing_remote_assets(dist, monkeypatch):
    prepare(dist)
    monkeypatch.setattr("sys.argv", ["release.py", "upload", "--dist", str(dist)])
    monkeypatch.setattr(release_tool, "remote_release", lambda repo: {"assets": [{"name": "old.zip"}]})
    def forbidden(*args, **kwargs):
        pytest.fail("Existing release must not be modified")
    monkeypatch.setattr(release_tool.subprocess, "run", forbidden)
    with pytest.raises(ValueError, match="已有附件"):
        release_tool.main()


@pytest.mark.parametrize("fault", [None, "name", "size", "digest", "state", "extra", "tag"])
def test_verify_remote_assets(dist, fault):
    paths = local_assets(prepare(dist))
    release = {"tagName": f"v{APP_VERSION}", "assets": [
        {"name": p.name, "size": p.stat().st_size,
         "digest": f"sha256:{sha256(p)}", "state": "uploaded"} for p in paths]}
    if fault in {"name", "size", "digest", "state"}:
        release["assets"][0][fault] = "incorrect"
    elif fault == "extra":
        release["assets"].append(dict(release["assets"][0]))
    elif fault == "tag":
        release["tagName"] = "v0.0.0"
    if fault:
        with pytest.raises(ValueError):
            verify_assets(paths, release)
    else:
        verify_assets(paths, release)
