"""Coder agent — implements changes according to the plan.

Role: coding (read + write). Can modify files.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from phoenixgithub.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class CoderAgent(BaseAgent):
    role = "coder"
    system_prompt = """You are an expert software engineer. You receive an implementation plan
and must produce the exact file changes needed.

For each step, respond with valid JSON matching this schema:
{
    "changes": [
        {
            "file_path": "relative/path/to/file.py",
            "action": "modify" | "create",
            "content": "the complete new file content"
        }
    ],
    "commit_message": "feat: concise description of what changed"
}

Rules:
- Write the COMPLETE file content for each changed file — no placeholders or ellipsis.
- Follow existing code style and conventions.
- Add appropriate imports.
- Do NOT add unnecessary comments explaining the change.
- Handle edge cases.
- Respond ONLY with the JSON object, no markdown fences."""

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        clone_path = context["clone_path"]
        plan = context["plan"]
        issue_title = context["issue_title"]
        issue_body = context["issue_body"]

        # If we have feedback from a failed verify-reject-retry, include it
        verify_feedback = context.get("verify_feedback", "")

        files_context = self._read_files_for_plan(clone_path, plan)

        feedback_section = ""
        if verify_feedback:
            feedback_section = (
                f"\n\n## Previous Attempt Failed\n"
                f"The following feedback was received. Fix these issues:\n{verify_feedback}\n"
            )

        prompt = (
            f"## Task\n"
            f"**Issue:** {issue_title}\n"
            f"**Description:** {issue_body}\n\n"
            f"## Implementation Plan\n```json\n{json.dumps(plan, indent=2)}\n```\n\n"
            f"## Current File Contents\n{files_context}"
            f"{feedback_section}\n\n"
            f"Produce the file changes as JSON."
        )

        raw = self.invoke(prompt)
        logger.info(f"Coder response length: {len(raw)} chars")

        try:
            result = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        except json.JSONDecodeError:
            logger.error(f"Coder returned invalid JSON:\n{raw[:500]}")
            return {"changes": [], "commit_message": "failed to parse coder output", "error": raw[:500]}

        # Apply changes to disk
        changes = result.get("changes", [])
        applied: list[str] = []
        for change in changes:
            file_path = change.get("file_path", "")
            content = change.get("content", "")
            if not file_path or not content:
                continue

            full_path = Path(clone_path) / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            applied.append(file_path)
            logger.info(f"Wrote: {file_path} ({len(content)} chars)")

        return {
            "changes": changes,
            "applied_files": applied,
            "commit_message": result.get("commit_message", f"feat: implement #{context.get('issue_number', '?')}"),
        }

    def _read_files_for_plan(self, clone_path: str, plan: dict) -> str:
        """Read files referenced in the plan so the coder has full context."""
        files_to_read = plan.get("files_to_modify", []) + plan.get("files_to_create", [])
        root = Path(clone_path)
        chunks: list[str] = []

        for rel_path in files_to_read:
            full = root / rel_path
            if full.exists():
                try:
                    content = full.read_text(errors="replace")
                    chunks.append(f"### {rel_path} (existing)\n```\n{content}\n```")
                except Exception:
                    chunks.append(f"### {rel_path}\n(could not read)")
            else:
                chunks.append(f"### {rel_path}\n(new file — does not exist yet)")

        return "\n\n".join(chunks) if chunks else "(no files to show)"
