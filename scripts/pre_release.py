#!/usr/bin/env python3
"""Run local pre-release checks before publishing from GitHub."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=check)


def _print_cmd(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")


def _require_tool(module_name: str) -> bool:
    spec = import_spec(module_name)
    if spec is None:
        print(
            f"Missing Python module '{module_name}'. Install release tools first:",
            file=sys.stderr,
        )
        print("  python -m pip install --upgrade build twine", file=sys.stderr)
        return False
    return True


def import_spec(module_name: str):
    import importlib.util

    return importlib.util.find_spec(module_name)


def read_project_version() -> str:
    with PYPROJECT.open("rb") as f:
        data = tomllib.load(f)
    return str(data["project"]["version"])


def normalize_tag(tag: str) -> str:
    return tag[1:] if tag.startswith("v") else tag


def ensure_git_clean() -> bool:
    # Refresh index metadata so porcelain output is reliable.
    _run(["git", "update-index", "-q", "--refresh"], check=False)
    result = _run(["git", "status", "--porcelain"], check=False)
    if result.returncode != 0:
        print("Failed to check git status.", file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)
        return False
    if result.stdout.strip():
        print("Working tree is not clean. Commit/stash changes before release.", file=sys.stderr)
        return False
    return True


def ensure_git_tag_absent(tag: str) -> bool:
    result = _run(["git", "tag", "--list", tag], check=False)
    if result.returncode != 0:
        print("Failed to check existing git tags.", file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)
        return False
    if result.stdout.strip():
        print(f"Tag '{tag}' already exists locally.", file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tag",
        default="",
        help="Expected release tag (example: v0.1.0). If set, must match pyproject version.",
    )
    args = parser.parse_args()

    if not ensure_git_clean():
        return 1

    version = read_project_version()
    expected_tag = args.tag.strip()
    if expected_tag:
        if normalize_tag(expected_tag) != version:
            print(
                f"Tag/version mismatch: tag '{expected_tag}' != pyproject version '{version}'",
                file=sys.stderr,
            )
            return 1
        if not ensure_git_tag_absent(expected_tag):
            return 1

    if not _require_tool("build") or not _require_tool("twine"):
        return 1

    dist_dir = ROOT / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    build_cmd = [sys.executable, "-m", "build"]
    _print_cmd(build_cmd)
    build = _run(build_cmd, check=False)
    if build.returncode != 0:
        print(build.stdout, end="")
        print(build.stderr, file=sys.stderr, end="")
        return build.returncode

    twine_cmd = [sys.executable, "-m", "twine", "check", "dist/*"]
    _print_cmd(twine_cmd)
    twine = _run(twine_cmd, check=False)
    if twine.returncode != 0:
        print(twine.stdout, end="")
        print(twine.stderr, file=sys.stderr, end="")
        return twine.returncode

    print()
    print("Pre-release checks passed.")
    print(f"- Version: {version}")
    if expected_tag:
        print(f"- Tag: {expected_tag}")
    print("- Dist artifacts rebuilt and validated with twine.")
    print()
    print("Next step: create/publish the GitHub Release to trigger PyPI workflow.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
