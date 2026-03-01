.PHONY: install status watch run-issue labels setup-actions reset-state clean-repo-state clean-workspace-all onboard
PYTHON ?= .venv/bin/python

install:
	pip install -e .

status:
	phoenixgithub status

watch:
	phoenixgithub watch

run-issue:
	@if [ -z "$(ISSUE)" ]; then \
		echo "Usage: make run-issue ISSUE=<number>"; \
		exit 1; \
	fi
	phoenixgithub run-issue "$(ISSUE)"

labels:
	$(PYTHON) scripts/create_labels.py

setup-actions:
	$(PYTHON) scripts/install_merge_done_workflow.py

reset-state:
	rm -f .watcher-state.json
	@echo "Watcher state reset (.watcher-state.json removed)"

clean-repo-state:
	@$(PYTHON) scripts/reset_repo_state.py

clean-workspace-all:
	@echo "Removing entire local workspace directory (./workspace)..."
	@rm -rf ./workspace
	@echo "Workspace cleared."

onboard:
	@echo "Onboarding repo from .env (GITHUB_REPO)..."
	@$(MAKE) clean-workspace-all
	@$(MAKE) clean-repo-state
	@$(PYTHON) scripts/create_labels.py
	@$(PYTHON) scripts/install_merge_done_workflow.py
	@phoenixgithub status
	@echo "Onboarding complete. Next: make watch"
