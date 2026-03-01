# Releasing PhoenixGitHub

This document is for maintainers publishing `phoenixgithub` to PyPI.

## Prerequisites

- PyPI account with permission to publish the package
- PyPI API token (recommended) for `__token__`
- Clean git working tree
- Local environment with Python `3.11+`

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
