#!/usr/bin/env python3
"""Reset local runtime state for the currently configured target repo."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from phoenixgithub.config import Config


def _rm_path(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return True


def main() -> int:
    config = Config.from_env()
    workspace_dir = Path(config.workspace_dir)
    clone_dir = workspace_dir / config.github.repo_name
    runs_dir = workspace_dir / "runs"
    state_file = Path(config.state_file)

    removed: list[str] = []
    if _rm_path(clone_dir):
        removed.append(str(clone_dir))
    if _rm_path(runs_dir):
        removed.append(str(runs_dir))
    if _rm_path(state_file):
        removed.append(str(state_file))

    if removed:
        print("Reset runtime state:")
        for item in removed:
            print(f"- {item}")
    else:
        print("No runtime state to clear.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
