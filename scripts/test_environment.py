"""Process-wide test isolation; enter before importing application modules."""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def isolated_environment():
    # Some third-party libraries retain handles until process exit on Windows.
    with tempfile.TemporaryDirectory(prefix="fiber-test-", ignore_cleanup_errors=True) as folder:
        root = Path(folder).resolve()
        values = {
            "FT_DB_PATH": str(root / "default.db"),
            "LOCALAPPDATA": str(root / "local"),
            "APPDATA": str(root / "roaming"),
            "MPLCONFIGDIR": str(root / "matplotlib"),
            "TEMP": folder,
            "TMP": folder,
        }
        previous = {key: os.environ.get(key) for key in values}
        old_tempdir = tempfile.tempdir
        os.environ.update(values)
        tempfile.tempdir = folder
        try:
            from PySide6.QtCore import QSettings

            QSettings.setDefaultFormat(QSettings.IniFormat)
            for scope in (QSettings.UserScope, QSettings.SystemScope):
                QSettings.setPath(QSettings.IniFormat, scope, str(root / "settings"))
            yield root
        finally:
            tempfile.tempdir = old_tempdir
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
