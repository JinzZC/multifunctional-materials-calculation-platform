"""Prepare versioned assets, upload without replacement, and verify a release.

Usage: py -3 scripts/release.py prepare|upload|verify
Requires existing build outputs; never starts the application or opens its DB.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fiber_tensile.config import APP_NAME, APP_VERSION

REPO = "JinzZC/multifunctional-materials-calculation-platform"
PREFIX = f"multifunctional-materials-calculation-platform-v{APP_VERSION}-windows-x64"
NAMES = (f"{PREFIX}.zip", f"{PREFIX}-portable.exe", "SHA256SUMS.txt")


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare(dist):
    dist = Path(dist)
    folder = dist / APP_NAME
    portable = dist / f"{APP_NAME}单文件版.exe"
    if not (folder / f"{APP_NAME}.exe").is_file() or not portable.is_file():
        raise ValueError("缺少构建产物，请先运行 py -3 scripts/build.py")
    files = sorted(folder.rglob("*"))
    for path in files:
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"发布目录不能包含链接：{path}")
        if path.is_file() and (path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".log", ".ini"}
                               or path.name.endswith(("-wal", "-shm"))):
            raise ValueError(f"发布目录包含用户数据或设置：{path}")
    destination = dist / f"release-v{APP_VERSION}"
    if destination.exists():
        raise ValueError(f"输出目录已存在，请检查后另行保存：{destination}")
    with tempfile.TemporaryDirectory(prefix="release-", dir=dist) as staging:
        stage = Path(staging)
        with zipfile.ZipFile(stage / NAMES[0], "w", zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                if path.is_file():
                    archive.write(path, path.relative_to(dist))
        shutil.copy2(portable, stage / NAMES[1])
        (stage / NAMES[2]).write_text(
            "".join(f"{sha256(stage / name)}  {name}\n" for name in NAMES[:2]),
            encoding="utf-8",
        )
        shutil.move(str(stage), str(destination))
    return destination


def local_assets(directory):
    directory = Path(directory)
    if {p.name for p in directory.iterdir()} != set(NAMES):
        raise ValueError("发布目录必须恰好包含 ZIP、便携 EXE 和 SHA256SUMS.txt")
    paths = [directory / name for name in NAMES]
    if any(not path.is_file() or path.stat().st_size == 0 for path in paths):
        raise ValueError("附件缺失或为空")
    expected = "".join(f"{sha256(path)}  {path.name}\n" for path in paths[:2])
    if paths[2].read_text(encoding="utf-8") != expected:
        raise ValueError("本地附件与校验文件不一致，请重新准备发布文件")
    return paths


def remote_release(repo):
    result = subprocess.run(
        ["gh", "release", "view", f"v{APP_VERSION}", "--repo", repo,
         "--json", "tagName,assets"], check=True, capture_output=True, text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def verify_assets(paths, release):
    if release.get("tagName") != f"v{APP_VERSION}":
        raise ValueError("远程标签与应用版本不一致")
    assets = release["assets"]
    if len(assets) != len(NAMES) or {a["name"] for a in assets} != set(NAMES):
        raise ValueError("远程附件名称或数量不符合预期")
    by_name = {a["name"]: a for a in assets}
    for path in paths:
        asset = by_name[path.name]
        if (asset.get("state") != "uploaded"
                or asset.get("size") != path.stat().st_size
                or asset.get("digest") != f"sha256:{sha256(path)}"):
            raise ValueError(f"远程附件未完成上传、大小或 SHA-256 不一致：{path.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "upload", "verify"))
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--repo", default=REPO)
    args = parser.parse_args()
    if args.action == "prepare":
        print(prepare(args.dist))
        return
    paths = local_assets(args.dist / f"release-v{APP_VERSION}")
    release = remote_release(args.repo)
    if args.action == "upload":
        if release["assets"]:
            raise ValueError("目标发布已有附件，停止上传以避免替换或混用已有版本")
        subprocess.run(["gh", "release", "upload", f"v{APP_VERSION}",
                        *map(str, paths), "--repo", args.repo], check=True)
        release = remote_release(args.repo)
    verify_assets(paths, release)
    print("Release verified: names, count, sizes and SHA-256 match.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Release failed: {exc}", file=sys.stderr)
        sys.exit(1)
