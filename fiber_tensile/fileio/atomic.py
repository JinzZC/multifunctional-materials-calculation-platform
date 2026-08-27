"""同目录临时文件写入与原子替换，避免导出失败损坏已有文件。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable


def atomic_write(path: str | os.PathLike, writer: Callable[[str], None]) -> None:
    """让 writer 写入临时路径，成功后原子替换目标文件。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    os.close(fd)
    try:
        writer(temporary)
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
