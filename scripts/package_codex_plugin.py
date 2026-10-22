#!/usr/bin/env python3
"""Package the Codex skills with the existing shared Claude processing helpers."""

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def package(destination):
    destination = Path(destination).resolve()
    manifest = json.loads((ROOT / "plugin.json").read_text())
    required = [ROOT / name for name in ("plugin.json", "LICENSE", "NOTICE", "CODEX.md")]
    directories = [
        ROOT / "skills",
        ROOT / "claude-plugin/skills/ocrdeskew/scripts",
        ROOT / "claude-plugin/skills/ocrdeskew/reference",
    ]
    files = list(required)
    for directory in directories:
        files.extend(
            path for path in directory.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
            and path.suffix not in (".pyc", ".pyo")
        )
    if destination in files:
        raise ValueError("Choose an archive path outside the plugin source files")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            archive.write(path, path.relative_to(ROOT).as_posix())
    print(f"Packaged {manifest['name']} {manifest['version']} -> {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Destination ZIP path")
    package(parser.parse_args().out)
