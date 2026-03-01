"""Tester agent — runs tests and reports results.

Role: testing (read + run). Cannot modify code.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from phoenixgithub.agents.base import BaseAgent

logger = logging.getLogger(__name__)
ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


class TesterAgent(BaseAgent):
    role = "tester"
    system_prompt = """You are a QA engineer. You receive test output and must produce a
structured verdict.

Respond with valid JSON:
{
    "passed": true | false,
    "summary": "Brief description of results",
    "failures": [
        {
            "test_name": "test_something",
            "error": "AssertionError: expected X got Y"
        }
    ],
    "feedback": "If tests failed, explain what the coder should fix. Be specific."
}

Respond ONLY with the JSON object, no markdown fences."""

    def __init__(
        self,
        llm,
        test_command: str = "pytest --import-mode=importlib --rootdir=.",
        allow_no_tests: bool = False,
        validation_profile: str = "auto",
    ) -> None:
        super().__init__(llm)
        self.test_command = test_command
        self.allow_no_tests = allow_no_tests
        self.validation_profile = validation_profile.lower().strip()

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        clone_path = context["clone_path"]

        # Run the test suite
        test_output = self._run_tests(clone_path)

        if self.allow_no_tests and self._is_no_tests_collected(test_output):
            logger.info("No tests collected (pytest exit 5) and ALLOW_NO_TESTS enabled — treating as pass")
            return {
                "test_passed": True,
                "test_output": test_output,
                "feedback": "",
                "test_verdict": {"passed": True, "summary": "No tests collected; allowed by configuration."},
            }

        if test_output["exit_code"] == 0 and "passed" in test_output.get("stdout", ""):
            logger.info("Tests passed — skipping LLM analysis")
            return {
                "test_passed": True,
                "test_output": test_output,
                "feedback": "",
            }

        # If tests failed or are ambiguous, ask the LLM to analyze
        prompt = (
            f"## Test Output\n"
            f"**Exit code:** {test_output['exit_code']}\n\n"
            f"**stdout:**\n```\n{test_output.get('stdout', '')[:8000]}\n```\n\n"
            f"**stderr:**\n```\n{test_output.get('stderr', '')[:4000]}\n```\n\n"
            f"Analyze the test results and produce the verdict JSON."
        )

        repo_tag = str(context.get("repo", "unknown")).replace("/", "__")
        issue_tag = f"issue:{context.get('issue_number', 'unknown')}"
        run_tag = f"run:{context.get('run_id', 'unknown')}"
        attempt_tag = f"attempt:{context.get('step_attempt', 'unknown')}"
        raw = self.invoke(
            prompt,
            trace_name="tester.analyze",
            trace_tags=["phoenixgithub", "tester", "analyze", f"repo:{repo_tag}", issue_tag, run_tag, attempt_tag],
            trace_metadata={
                "agent": self.role,
                "run_id": context.get("run_id"),
                "issue_number": context.get("issue_number"),
                "repo": context.get("repo"),
                "branch_name": context.get("branch_name"),
                "step": "test",
                "attempt": context.get("step_attempt"),
                "test_exit_code": test_output.get("exit_code"),
            },
        )

        try:
            verdict = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        except json.JSONDecodeError:
            verdict = {
                "passed": test_output["exit_code"] == 0,
                "summary": "Could not parse test analysis",
                "failures": [],
                "feedback": raw[:1000],
            }

        return {
            "test_passed": verdict.get("passed", False),
            "test_output": test_output,
            "test_verdict": verdict,
            "feedback": verdict.get("feedback", ""),
        }

    def _run_tests(self, cwd: str) -> dict:
        """Execute the test command and capture output."""
        profile = self._resolve_profile(cwd)
        if profile == "frontend":
            return self._run_frontend_checks(cwd)
        if profile == "generic":
            return self._run_generic_checks(cwd)
        # default: python profile

        resolved_cwd = str(Path(cwd).resolve())
        raw_parts = shlex.split(self.test_command)
        inline_env: dict[str, str] = {}
        cmd: list[str] = []
        for idx, part in enumerate(raw_parts):
            # Support shell-like inline env prefixes such as:
            # PYTHONPATH=. pytest -q
            if not cmd and ENV_ASSIGNMENT_RE.match(part):
                key, value = part.split("=", 1)
                inline_env[key] = value
                continue
            cmd = raw_parts[idx:]
            break

        if not cmd:
            return {"exit_code": -1, "stdout": "", "stderr": f"Invalid TEST_COMMAND: {self.test_command}"}

        if cmd and cmd[0] == "pytest" and not any(part.startswith("--rootdir") for part in cmd[1:]):
            cmd.append("--rootdir=.")

        env = os.environ.copy()
        env.update(inline_env)
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{resolved_cwd}:{existing}" if existing else resolved_cwd

        logger.info(f"Running: {' '.join(cmd)} in {resolved_cwd}")
        try:
            proc = subprocess.run(
                cmd,
                cwd=resolved_cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if proc.returncode != 0:
                stderr_head = (proc.stderr or "")[:400].replace("\n", " ")
                stdout_head = (proc.stdout or "")[:400].replace("\n", " ")
                logger.warning(
                    "Test command failed with exit %s; stderr head: %s; stdout head: %s",
                    proc.returncode,
                    stderr_head,
                    stdout_head,
                )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": "Test execution timed out (300s)"}
        except FileNotFoundError:
            return {"exit_code": -1, "stdout": "", "stderr": f"Command not found: {self.test_command}"}

    def _is_no_tests_collected(self, test_output: dict[str, Any]) -> bool:
        if test_output.get("exit_code") != 5:
            return False
        text = f"{test_output.get('stdout', '')}\n{test_output.get('stderr', '')}".lower()
        return "no tests ran" in text or "collected 0 items" in text

    def _resolve_profile(self, cwd: str) -> str:
        if self.validation_profile in {"python", "frontend", "generic"}:
            return self.validation_profile
        # auto-detect
        root = Path(cwd)
        if (root / "package.json").exists():
            return "frontend"
        return "python"

    def _run_frontend_checks(self, cwd: str) -> dict:
        """Frontend-friendly checks: prefer npm test/build/lint if available."""
        root = Path(cwd)
        pkg = root / "package.json"
        if not pkg.exists():
            return {"exit_code": 0, "stdout": "No package.json; frontend checks skipped.", "stderr": ""}

        try:
            data = json.loads(pkg.read_text())
            scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
        except Exception:
            scripts = {}

        chosen: list[list[str]] = []
        if isinstance(scripts, dict):
            if "test" in scripts:
                chosen.append(["npm", "run", "test", "--", "--runInBand"])
            elif "build" in scripts:
                chosen.append(["npm", "run", "build"])
            elif "lint" in scripts:
                chosen.append(["npm", "run", "lint"])

        if not chosen:
            # Minimal static fallback for static-only frontends.
            has_index = (root / "index.html").exists()
            has_assets = any((root / d).exists() for d in ("css", "js", "src", "public"))
            ok = has_index or has_assets
            return {
                "exit_code": 0 if ok else 1,
                "stdout": "Static frontend fallback checks passed." if ok else "",
                "stderr": "" if ok else "No frontend scripts and no obvious frontend assets found.",
            }

        outputs: list[str] = []
        for cmd in chosen:
            try:
                logger.info(f"Running frontend check: {' '.join(cmd)} in {cwd}")
                proc = subprocess.run(
                    cmd,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                outputs.append(proc.stdout)
                if proc.returncode != 0:
                    return {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
            except FileNotFoundError:
                return {"exit_code": -1, "stdout": "", "stderr": "npm not found for frontend validation."}
            except subprocess.TimeoutExpired:
                return {"exit_code": -1, "stdout": "", "stderr": "Frontend validation timed out (300s)."}

        return {"exit_code": 0, "stdout": "\n".join(outputs), "stderr": ""}

    def _run_generic_checks(self, cwd: str) -> dict:
        """Generic fallback checks for repos without runnable tests."""
        root = Path(cwd)
        if any((root / p).exists() for p in ("README.md", "index.html", "src", "app", "main.py")):
            return {"exit_code": 0, "stdout": "Generic sanity checks passed.", "stderr": ""}
        return {"exit_code": 1, "stdout": "", "stderr": "Generic sanity checks failed: repository appears empty."}
