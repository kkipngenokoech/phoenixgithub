"""Orchestrator — runs the full pipeline: plan → implement → test → PR.

The orchestrator never implements code itself. It only dispatches to agents
and manages the verify-reject-retry loop.
"""

from __future__ import annotations

import logging
from typing import Any

from phoenixgithub.agents.coder import CoderAgent
from phoenixgithub.agents.planner import PlannerAgent
from phoenixgithub.agents.pr_agent import PRAgent
from phoenixgithub.agents.tester import TesterAgent
from phoenixgithub.config import Config
from phoenixgithub.github_client import GitHubClient
from phoenixgithub.models import Run, RunStatus, StepID
from phoenixgithub.provider import create_llm
from phoenixgithub.state import StateManager

logger = logging.getLogger(__name__)


class Orchestrator:
    """Executes a run: PLAN → IMPLEMENT → TEST → PR with retry loop."""

    def __init__(self, config: Config, github: GitHubClient, state: StateManager) -> None:
        self.config = config
        self.github = github
        self.state = state

        llm = create_llm(config.llm)
        self.planner = PlannerAgent(llm)
        self.coder = CoderAgent(llm)
        self.tester = TesterAgent(llm, test_command=config.agent.test_command)
        self.pr_agent = PRAgent(llm)

    def execute(self, run: Run) -> Run:
        """Execute the full pipeline for a run. Returns updated run."""
        run.status = RunStatus.RUNNING
        self.state.save_run(run)

        issue_number = run.issues[0]
        issue = self.github.get_issue(issue_number)

        context: dict[str, Any] = {
            "issue_number": issue_number,
            "issue_title": issue.title,
            "issue_body": issue.body or "",
            "branch_name": run.branch_name,
        }

        try:
            # 1. Clone and branch
            clone_path = self.github.ensure_clone(self.config.workspace_dir)
            repo = self.github.create_branch(clone_path, run.branch_name)
            context["clone_path"] = clone_path

            # 2. PLAN
            run = self._step_plan(run, context)
            if run.status == RunStatus.FAILED:
                return self._finalize_failure(run, issue_number)

            # 3. IMPLEMENT + TEST (with retry loop)
            run = self._step_implement_and_test(run, context)
            if run.status == RunStatus.FAILED:
                return self._finalize_failure(run, issue_number)

            # 4. Commit & Push
            commit_msg = context.get("commit_message", f"feat: implement #{issue_number}")
            sha = self.github.commit_and_push(
                clone_path, run.branch_name, commit_msg, context.get("applied_files")
            )
            logger.info(f"Committed: {sha[:8]}")

            # 5. CREATE PR
            run = self._step_pr(run, context)
            if run.status == RunStatus.FAILED:
                return self._finalize_failure(run, issue_number)

            # 6. Success
            run.status = RunStatus.SUCCEEDED
            self.state.save_run(run)
            self.state.mark_run_finished(run.run_id)

            self.github.transition_label(
                issue_number,
                self.config.labels.in_progress,
                self.config.labels.review,
            )
            self.github.comment_on_issue(
                issue_number,
                f"✅ **Phoenix AI** created a PR for review.\n\n"
                f"**PR:** {run.pr_url}\n"
                f"**Branch:** `{run.branch_name}`\n\n"
                f"Please review and merge when ready.",
            )

            logger.info(f"Run {run.run_id} succeeded — PR: {run.pr_url}")
            return run

        except Exception as e:
            logger.error(f"Run {run.run_id} failed: {e}", exc_info=True)
            run.status = RunStatus.FAILED
            run.error = str(e)
            self.state.save_run(run)
            return self._finalize_failure(run, issue_number)

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def _step_plan(self, run: Run, context: dict) -> Run:
        logger.info(f"[{run.run_id}] PLAN — analyzing issue #{context['issue_number']}")
        run.set_step_running(StepID.PLAN)
        self.state.save_run(run)

        try:
            outputs = self.planner.run(context)
            context.update(outputs)
            run.set_step_done(StepID.PLAN, outputs)

            plan = outputs.get("plan", {})
            self.github.comment_on_issue(
                context["issue_number"],
                f"📋 **Plan ready**\n\n"
                f"**Approach:** {plan.get('approach', 'N/A')}\n"
                f"**Files:** {', '.join(plan.get('files_to_modify', []))}\n"
                f"**Risk:** {plan.get('risk_level', 'unknown')}",
            )
        except Exception as e:
            run.set_step_failed(StepID.PLAN, str(e))
            run.status = RunStatus.FAILED
            run.error = f"Plan failed: {e}"

        self.state.save_run(run)
        return run

    def _step_implement_and_test(self, run: Run, context: dict) -> Run:
        """Implement + test with verify-reject-retry loop."""
        max_retries = self.config.agent.max_retries

        for attempt in range(1, max_retries + 1):
            logger.info(f"[{run.run_id}] IMPLEMENT (attempt {attempt}/{max_retries})")
            run.set_step_running(StepID.IMPLEMENT)
            self.state.save_run(run)

            try:
                coder_outputs = self.coder.run(context)
                context.update(coder_outputs)

                if not coder_outputs.get("applied_files"):
                    run.set_step_failed(StepID.IMPLEMENT, "Coder produced no file changes")
                    run.status = RunStatus.FAILED
                    run.error = "No changes produced"
                    self.state.save_run(run)
                    return run

                run.set_step_done(StepID.IMPLEMENT, {
                    "applied_files": coder_outputs.get("applied_files", []),
                    "attempt": attempt,
                })
            except Exception as e:
                run.set_step_failed(StepID.IMPLEMENT, str(e))
                run.status = RunStatus.FAILED
                run.error = f"Implementation failed: {e}"
                self.state.save_run(run)
                return run

            # TEST
            logger.info(f"[{run.run_id}] TEST (attempt {attempt}/{max_retries})")
            run.set_step_running(StepID.TEST)
            self.state.save_run(run)

            try:
                test_outputs = self.tester.run(context)
                context.update(test_outputs)

                if test_outputs.get("test_passed"):
                    run.set_step_done(StepID.TEST, test_outputs)
                    self.state.save_run(run)
                    logger.info(f"[{run.run_id}] Tests passed on attempt {attempt}")
                    return run

                # Tests failed — feed back to coder for retry
                feedback = test_outputs.get("feedback", "Tests failed — see output")
                context["verify_feedback"] = feedback
                logger.warning(f"[{run.run_id}] Tests failed (attempt {attempt}): {feedback[:200]}")
                run.step(StepID.TEST).retries += 1

            except Exception as e:
                run.set_step_failed(StepID.TEST, str(e))
                run.status = RunStatus.FAILED
                run.error = f"Testing failed: {e}"
                self.state.save_run(run)
                return run

        # Exhausted retries
        run.set_step_failed(StepID.TEST, f"Tests failed after {max_retries} attempts")
        run.status = RunStatus.FAILED
        run.error = f"Tests failed after {max_retries} retries"
        self.state.save_run(run)
        return run

    def _step_pr(self, run: Run, context: dict) -> Run:
        logger.info(f"[{run.run_id}] PR — creating pull request")
        run.set_step_running(StepID.PR)
        self.state.save_run(run)

        try:
            pr_outputs = self.pr_agent.run(context)
            context.update(pr_outputs)

            pr = self.github.create_pull_request(
                branch_name=run.branch_name,
                title=pr_outputs["pr_title"],
                body=pr_outputs["pr_body"],
                issue_numbers=run.issues,
                labels=[self.config.labels.review],
            )
            run.pr_number = pr.number
            run.pr_url = pr.html_url
            run.set_step_done(StepID.PR, {"pr_number": pr.number, "pr_url": pr.html_url})

        except Exception as e:
            run.set_step_failed(StepID.PR, str(e))
            run.status = RunStatus.FAILED
            run.error = f"PR creation failed: {e}"

        self.state.save_run(run)
        return run

    # ------------------------------------------------------------------
    # Failure handling
    # ------------------------------------------------------------------

    def _finalize_failure(self, run: Run, issue_number: int) -> Run:
        self.state.mark_run_finished(run.run_id)
        try:
            self.github.transition_label(
                issue_number,
                self.config.labels.in_progress,
                self.config.labels.failed,
            )
            self.github.comment_on_issue(
                issue_number,
                f"❌ **Phoenix AI** failed to complete this issue.\n\n"
                f"**Error:** {run.error}\n"
                f"**Run ID:** `{run.run_id}`\n\n"
                f"You can re-trigger by changing the label to `{self.config.labels.ready}`.",
            )
        except Exception as e:
            logger.error(f"Failed to update issue on failure: {e}")
        return run
