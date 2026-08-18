#!/usr/bin/env python3
"""Install local skill folders with timestamped backups."""

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path


def validate_skill(source):
    if not source.is_dir() or not (source / "SKILL.md").is_file():
        raise ValueError(f"Not an installable skill directory: {source}")
    if source.name.startswith("."):
        raise ValueError(f"Hidden directory cannot be installed as a skill: {source}")


def install(sources, destination):
    destination.mkdir(parents=True, exist_ok=True)
    backup = destination / (
        ".game-skill-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    )
    installed = []
    backed_up = []
    for source in sources:
        source = source.resolve()
        validate_skill(source)
        target = destination / source.name
        if target.exists():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copytree(target, backup / source.name)
            backed_up.append(source.name)
            shutil.rmtree(target)
        shutil.copytree(source, target)
        installed.append(source.name)
    return {
        "destination": str(destination.resolve()),
        "backup": str(backup.resolve()) if backed_up else None,
        "installed": installed,
        "backedUp": backed_up,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="+", type=Path)
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path(
            os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
        ) / "skills",
    )
    args = parser.parse_args()
    print(json.dumps(install(args.source, args.dest), indent=2))


if __name__ == "__main__":
    main()
