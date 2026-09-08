import os
from pathlib import Path
import tempfile

from fiber_tensile.config import default_db_path
from fiber_tensile.data.db import open_database
from fiber_tensile.ui.prefs import _settings


def test_default_database_and_settings_are_temporary():
    root = Path(tempfile.gettempdir()).resolve()
    assert root.name.startswith("fiber-test-")
    path = Path(default_db_path()).resolve()
    assert path.is_relative_to(root)
    assert Path(os.environ["LOCALAPPDATA"]).is_relative_to(root)
    settings = _settings()
    assert Path(settings.fileName()).resolve().is_relative_to(root)
    conn = open_database(str(path))
    try:
        assert conn.execute("PRAGMA database_list").fetchone()[2] == str(path)
    finally:
        conn.close()
