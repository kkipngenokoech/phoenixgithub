.PHONY: install status watch run-issue labels setup-actions reset-state clean-repo-state clean-workspace-all onboard pre-release release
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

pre-release:
	@$(PYTHON) scripts/pre_release.py $(if $(TAG),--tag $(TAG),)

release:
	@if [ -z "$(TAG)" ]; then \
		echo "Usage: make release TAG=vX.Y.Z [NOTES='Release notes text']"; \
		exit 1; \
	fi
	@command -v gh >/dev/null 2>&1 || { \
		echo "GitHub CLI (gh) is required. Install from https://cli.github.com/"; \
		exit 1; \
	}
	@gh auth status >/dev/null 2>&1 || { \
		echo "GitHub CLI is not authenticated. Run: gh auth login"; \
		exit 1; \
	}
	@$(MAKE) pre-release TAG="$(TAG)"
	@gh release create "$(TAG)" --title "$(TAG)" $(if $(NOTES),--notes "$(NOTES)",--generate-notes)
	@echo "Release $(TAG) created. GitHub Actions will publish to PyPI."
