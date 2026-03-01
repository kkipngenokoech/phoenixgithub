.PHONY: install status watch run-issue labels setup-actions reset-state
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
