from __future__ import annotations

from dataclasses import dataclass
import unittest

from phoenixgithub.tools.git_utils import compute_uncovered_paths, get_changed_paths, get_default_branch
from phoenixgithub.tools.path_utils import (
    extract_image_urls_from_texts,
    infer_image_extension,
    looks_like_image_url,
)


@dataclass
class _Branch:
    name: str


class _Git:
    def __init__(self, porcelain: str = "", raise_error: bool = False) -> None:
        self._porcelain = porcelain
        self._raise_error = raise_error

    def status(self, *_args: str) -> str:
        if self._raise_error:
            raise RuntimeError("status failed")
        return self._porcelain


class _Repo:
    def __init__(self, branches: list[str], porcelain: str = "", raise_error: bool = False) -> None:
        self.branches = [_Branch(name=b) for b in branches]
        self.git = _Git(porcelain=porcelain, raise_error=raise_error)


class GitUtilsTests(unittest.TestCase):
    def test_get_default_branch_prefers_main(self) -> None:
        repo = _Repo(branches=["feature/a", "main", "master"])
        self.assertEqual(get_default_branch(repo), "main")

    def test_get_default_branch_falls_back_to_master_then_first(self) -> None:
        repo_master = _Repo(branches=["feature/a", "master"])
        self.assertEqual(get_default_branch(repo_master), "master")

        repo_first = _Repo(branches=["develop", "feature/a"])
        self.assertEqual(get_default_branch(repo_first), "develop")

    def test_get_default_branch_falls_back_to_main_when_no_branches(self) -> None:
        repo = _Repo(branches=[])
        self.assertEqual(get_default_branch(repo), "main")

    def test_get_changed_paths_parses_porcelain_and_renames(self) -> None:
        porcelain = "\n".join(
            [
                " M src/app.py",
                "?? docs/",
                "R  old/name.py -> new/name.py",
            ]
        )
        repo = _Repo(branches=["main"], porcelain=porcelain)
        self.assertEqual(get_changed_paths(repo), {"src/app.py", "docs/", "new/name.py"})

    def test_get_changed_paths_returns_empty_on_git_error(self) -> None:
        repo = _Repo(branches=["main"], raise_error=True)
        self.assertEqual(get_changed_paths(repo), set())

    def test_compute_uncovered_paths_respects_directory_coverage(self) -> None:
        changed = {"index.html", "css/", "css/styles.css", "js/app.js"}
        requested = {"index.html", "css/styles.css", "js/app.js"}
        self.assertEqual(compute_uncovered_paths(changed, requested), set())

    def test_compute_uncovered_paths_flags_real_omissions(self) -> None:
        changed = {"index.html", "css/", "css/styles.css", "js/app.js", "README.md"}
        requested = {"index.html", "css/styles.css"}
        self.assertEqual(compute_uncovered_paths(changed, requested), {"js/app.js", "README.md"})


class PathUtilsTests(unittest.TestCase):
    def test_looks_like_image_url_and_extension_inference(self) -> None:
        self.assertTrue(looks_like_image_url("https://example.com/image.png"))
        self.assertTrue(looks_like_image_url("https://raw.githubusercontent.com/user/repo/assets/1"))
        self.assertFalse(looks_like_image_url("https://example.com/file.txt"))

        self.assertEqual(infer_image_extension("https://example.com/a.jpeg", ""), ".jpeg")
        self.assertEqual(infer_image_extension("https://example.com/no-ext", "image/webp"), ".webp")
        self.assertEqual(infer_image_extension("https://example.com/no-ext", "application/octet-stream"), ".png")

    def test_extract_image_urls_from_texts_deduplicates_and_filters(self) -> None:
        texts = [
            "See ![img](https://example.com/a.png) and text https://example.com/readme.txt",
            "Again https://example.com/a.png plus https://example.com/b.webp",
        ]
        self.assertEqual(
            extract_image_urls_from_texts(texts),
            [
                "https://example.com/a.png",
                "https://example.com/b.webp",
            ],
        )


if __name__ == "__main__":
    unittest.main()

