"""Planner agent — reads issue + codebase, produces implementation plan.

Role: analysis (read-only). Cannot modify code.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from phoenixgithub.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    role = "planner"
    system_prompt = """You are a senior software architect. Your job is to read a GitHub issue
and the relevant codebase, then produce a concrete implementation plan.

You MUST respond with valid JSON matching this schema:
{
    "summary": "One-sentence summary of the change",
    "approach": "High-level approach description",
    "files_to_modify": ["path/to/file1.py", "path/to/file2.py"],
    "files_to_create": ["path/to/new_file.py"],
    "steps": [
        {
            "step_id": 1,
            "description": "What to do",
            "target_file": "path/to/file.py",
            "action": "modify or create"
        }
    ],
    "test_strategy": "How to verify the changes work",
    "risk_level": "low | medium | high"
}

Rules:
- Be specific about file paths (relative to repo root).
- Keep steps ordered by dependency — things that must happen first go first.
- Consider edge cases and backwards compatibility.
- Only include files that actually need changes.
- Respond ONLY with the JSON object, no markdown fences."""

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        clone_path = context["clone_path"]
        issue_title = context["issue_title"]
        issue_body = context["issue_body"]
        issue_image_paths: list[str] = context.get("issue_image_paths", [])
        issue_image_urls: list[str] = context.get("issue_image_urls", [])
        revision_notes = context.get("revision_notes", "")
        trigger_label = context.get("trigger_label", "")
        issue_comments: list[dict[str, str]] = context.get("issue_comments", [])

        file_tree = self._scan_tree(clone_path)

        relevant_code = self._read_relevant_files(clone_path)
        visual_context = self._analyze_screenshots(
            issue_title,
            issue_body,
            issue_image_paths,
            repo=context.get("repo"),
            issue_number=context.get("issue_number"),
            run_id=context.get("run_id"),
        )
        image_urls_text = "\n".join(f"- {u}" for u in issue_image_urls) if issue_image_urls else "(none)"
        comments_text = "\n".join(
            f"- @{c.get('author', 'unknown')}: {(c.get('body') or '')[:300]}"
            for c in issue_comments[-12:]
        ) or "(none)"
        revise_instruction = ""
        if trigger_label == "ai:revise":
            revise_instruction = (
                "You are in revise mode. Prioritize the latest human feedback and "
                "apply the smallest targeted change set needed to resolve it. "
                "Do not redesign unrelated parts."
            )

        prompt = (
            f"## GitHub Issue\n"
            f"**Title:** {issue_title}\n"
            f"**Description:**\n{issue_body}\n\n"
            f"## Trigger Context\n"
            f"Trigger label: {trigger_label}\n"
            f"{revise_instruction}\n\n"
            f"## Issue Discussion (recent comments)\n{comments_text}\n\n"
            f"## Revision Directives\n{revision_notes or '(none)'}\n\n"
            f"## Issue Image URLs\n{image_urls_text}\n\n"
            f"## Visual Context Extracted From Screenshots\n{visual_context}\n\n"
            f"## Repository Structure\n```\n{file_tree}\n```\n\n"
            f"## Key Source Files\n{relevant_code}\n\n"
            f"Produce the implementation plan as JSON."
        )

        trace_meta = {
            "agent": self.role,
            "run_id": context.get("run_id"),
            "issue_number": context.get("issue_number"),
            "repo": context.get("repo"),
            "branch_name": context.get("branch_name"),
            "step": "plan",
            "image_count": len(issue_image_paths),
            "image_url_count": len(issue_image_urls),
        }
        repo_tag = str(context.get("repo", "unknown")).replace("/", "__")
        issue_tag = f"issue:{context.get('issue_number', 'unknown')}"
        run_tag = f"run:{context.get('run_id', 'unknown')}"
        raw = self.invoke(
            prompt,
            trace_name="planner.plan",
            trace_tags=["phoenixgithub", "planner", "plan", f"repo:{repo_tag}", issue_tag, run_tag],
            trace_metadata=trace_meta,
        )
        logger.info(f"Planner response length: {len(raw)} chars")

        try:
            plan = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        except json.JSONDecodeError:
            logger.error(f"Planner returned invalid JSON:\n{raw[:500]}")
            plan = {
                "summary": issue_title,
                "approach": raw[:1000],
                "files_to_modify": [],
                "files_to_create": [],
                "steps": [],
                "test_strategy": "manual",
                "risk_level": "medium",
            }

        return {"plan": plan, "visual_context": visual_context}

    def _analyze_screenshots(
        self,
        issue_title: str,
        issue_body: str,
        image_paths: list[str],
        *,
        repo: str | None,
        issue_number: int | None,
        run_id: str | None,
    ) -> str:
        if not image_paths:
            return "(no screenshots provided)"

        try:
            prompt = (
                "Analyze the attached screenshots from a GitHub issue.\n\n"
                f"Issue title: {issue_title}\n"
                f"Issue body: {issue_body[:2000]}\n\n"
                "Return concise plain text with:\n"
                "1) Visible UI/state facts\n"
                "2) Errors/messages shown\n"
                "3) Concrete implementation requirements implied by the screenshots\n"
                "4) Any ambiguity that still needs clarification\n"
            )
            analysis = self.invoke_with_images(
                prompt,
                image_paths[:6],
                trace_name="planner.vision",
                trace_tags=[
                    "phoenixgithub",
                    "planner",
                    "vision",
                    f"repo:{str(repo or 'unknown').replace('/', '__')}",
                    f"issue:{issue_number or 'unknown'}",
                    f"run:{run_id or 'unknown'}",
                ],
                trace_metadata={
                    "agent": self.role,
                    "step": "plan_vision",
                    "image_count": len(image_paths[:6]),
                },
            )
            return analysis.strip()[:8000]
        except Exception as e:
            logger.warning(f"Screenshot analysis failed: {e}")
            return "(screenshot analysis unavailable)"

    def _scan_tree(self, root: str, max_depth: int = 3) -> str:
        lines: list[str] = []
        root_path = Path(root)
        skip = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", ".mypy_cache"}

        def walk(p: Path, depth: int, prefix: str = "") -> None:
            if depth > max_depth:
                return
            entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name))
            for i, entry in enumerate(entries):
                if entry.name in skip:
                    continue
                connector = "└── " if i == len(entries) - 1 else "├── "
                lines.append(f"{prefix}{connector}{entry.name}")
                if entry.is_dir():
                    ext = "    " if i == len(entries) - 1 else "│   "
                    walk(entry, depth + 1, prefix + ext)

        lines.append(root_path.name + "/")
        walk(root_path, 0)
        return "\n".join(lines[:200])

    def _read_relevant_files(self, root: str, max_files: int = 15) -> str:
        """Read Python/JS/TS source files, skipping tests and configs."""
        root_path = Path(root)
        code_exts = {".py", ".js", ".ts", ".tsx", ".jsx"}
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv"}
        chunks: list[str] = []
        count = 0

        for f in sorted(root_path.rglob("*")):
            if count >= max_files:
                break
            if not f.is_file() or f.suffix not in code_exts:
                continue
            if any(sd in f.parts for sd in skip_dirs):
                continue
            try:
                content = f.read_text(errors="replace")
                rel = f.relative_to(root_path)
                if len(content) > 5000:
                    content = content[:5000] + "\n... (truncated)"
                chunks.append(f"### {rel}\n```\n{content}\n```")
                count += 1
            except Exception:
                continue

        return "\n\n".join(chunks) if chunks else "(no source files found)"
