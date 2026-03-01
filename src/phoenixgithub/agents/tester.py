"""Tester agent — runs tests and reports results.

Role: testing (read + run). Cannot modify code.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from phoenixgithub.agents.base import BaseAgent

logger = logging.getLogger(__name__)


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

    def __init__(self, llm, test_command: str = "pytest --import-mode=importlib") -> None:
        super().__init__(llm)
        self.test_command = test_command

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        clone_path = context["clone_path"]

        # Run the test suite
        test_output = self._run_tests(clone_path)

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

        raw = self.invoke(prompt)

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
        logger.info(f"Running: {self.test_command} in {cwd}")
        try:
            proc = subprocess.run(
                self.test_command.split(),
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=300,
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
