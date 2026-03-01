# Releasing PhoenixGitHub

This document is for maintainers publishing `phoenixgithub` to PyPI.

## Prerequisites

- PyPI account with permission to publish the package
- Clean git working tree
- Local environment with Python `3.11+`

## GitHub release automation

This repository includes `.github/workflows/publish-pypi.yml` to publish from GitHub Actions using PyPI Trusted Publishing (OIDC).

### One-time setup

1. In PyPI account settings, add a Trusted Publisher (or Pending Publisher) for this GitHub workflow:
   - Project name: `phoenixgithub`
   - Owner: your GitHub username or org
   - Repository: this repository name
   - Workflow file: `publish-pypi.yml`
2. Ensure package name on PyPI is `phoenixgithub`.
3. Ensure `version` in `pyproject.toml` is bumped for each release.

### Triggering publish from GitHub

- Recommended: create a GitHub Release (`published`) for the new version tag.
- Optional: run the `Publish to PyPI` workflow manually from Actions (`workflow_dispatch`).

The workflow builds distributions, runs `twine check`, then uploads to PyPI via OIDC.

Install release tooling:

```bash
python -m pip install --upgrade build twine
```

## 1) Prepare the release

1. Ensure tests/checks pass locally.
2. Update `version` in `pyproject.toml`.
3. Update `README.md` and user-facing docs if behavior changed.

Optional but recommended:

1. Commit changes and create a release tag.

## 2) Build package artifacts

```bash
python -m build
```

This creates:

- `dist/*.tar.gz` (source distribution)
- `dist/*.whl` (wheel)

## 3) Validate artifacts

```bash
python -m twine check dist/*
```

## 4) Upload to TestPyPI (recommended)

```bash
python -m twine upload --repository testpypi dist/*
```

Sanity-check install from TestPyPI:

```bash
python -m pip install --index-url https://test.pypi.org/simple/ phoenixgithub
phoenixgithub --help
```

## 5) Upload to PyPI

```bash
python -m twine upload dist/*
```

## 6) Verify published package

```bash
python -m pip install -U phoenixgithub
phoenixgithub --help
```

## 7) Post-release checklist

- Create release notes/changelog entry.
- Announce the release.
- Confirm docs reference the latest version.
