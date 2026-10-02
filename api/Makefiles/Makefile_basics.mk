ifeq ($(wildcard .env),.env)
include .env
export
endif
VIRTUAL_ENV := $(CURDIR)/.venv
PROJECT_NAME := $(shell grep '^name = ' pyproject.toml | sed -E 's/name = "(.*)"/\1/')

# This directory is a member of the uv workspace rooted at the repository root, which holds the one
# `uv.lock`. uv would sync a member into the workspace root's `.venv`, pipelex's own environment, so
# every uv command here is pointed at this member's own `.venv` instead: the server is tested with
# exactly the dependencies it declares (pipelex with the server's extras, and without `cli`), and
# pipelex is installed from the workspace in editable mode, so an edit to the library reaches this
# environment without a reinstall.
export UV_PROJECT_ENVIRONMENT := $(VIRTUAL_ENV)
WORKSPACE_ROOT := $(abspath $(CURDIR)/..)

# The "?" is used to make the variable optional, so that it can be overridden by the user.
PYTHON_VERSION ?= 3.13
# The Python version pyright and mypy check against, when it is not the environment's own: the root's
# pre-main gate (`lint-fresh-check.yml`) checks every supported version from one 3.11 environment.
LINT_PYTHON_VERSION ?=
# Where `make build` writes the pipelex-api wheel and sdist, and where `make check-lockstep-pin` reads them.
DIST_DIR ?= dist
VENV_PYTHON := $(VIRTUAL_ENV)/bin/python
VENV_PYTEST := $(VIRTUAL_ENV)/bin/pytest
VENV_RUFF := $(VIRTUAL_ENV)/bin/ruff
VENV_PYRIGHT := $(VIRTUAL_ENV)/bin/pyright
VENV_MYPY := $(VIRTUAL_ENV)/bin/mypy
VENV_PIPELEX := $(VIRTUAL_ENV)/bin/pipelex
VENV_PYLINT := $(VIRTUAL_ENV)/bin/pylint

UV_MIN_VERSION = $(shell grep -m1 'required-version' $(WORKSPACE_ROOT)/pyproject.toml | sed -E 's/.*= *"([^<>=, ]+).*/\1/')

USUAL_PYTEST_MARKERS := "(dry_runnable or not (inference or llm or img_gen or ocr)) and not (needs_output or pipelex_api)"

define PRINT_TITLE
    $(eval PROJECT_PART := [$(PROJECT_NAME)])
    $(eval TARGET_PART := ($@))
    $(eval MESSAGE_PART := $(1))
    $(if $(MESSAGE_PART),\
        $(eval FULL_TITLE := === $(PROJECT_PART) ===== $(TARGET_PART) ====== $(MESSAGE_PART) ),\
        $(eval FULL_TITLE := === $(PROJECT_PART) ===== $(TARGET_PART) ====== )\
    )
    $(eval TITLE_LENGTH := $(shell echo -n "$(FULL_TITLE)" | wc -c | tr -d ' '))
    $(eval PADDING_LENGTH := $(shell echo $$((126 - $(TITLE_LENGTH)))))
    $(eval PADDING := $(shell printf '%*s' $(PADDING_LENGTH) '' | tr ' ' '='))
    $(eval PADDED_TITLE := $(FULL_TITLE)$(PADDING))
    @echo ""
    @echo "$(PADDED_TITLE)"
endef

define HELP
Manage $(PROJECT_NAME) located in $(CURDIR).
Usage:

make env                      - Create python virtual env
make lock                     - Refresh the workspace uv.lock (at the repository root) without updating anything
make install                  - Create local virtualenv & install all dependencies
make build                    - Build the pipelex-api wheel and sdist into $(DIST_DIR)
make check-lockstep-pin       - Check that the built distributions pin pipelex to this version (after make build)

make format                   - format with ruff format
make lint                     - lint with ruff check
make pyright                  - Check types with pyright
make mypy                     - Check types with mypy

make cleanenv                 - Remove virtual env and lock files
make cleanderived             - Remove extraneous compiled files, caches, logs, etc.
make cleanall                 - Remove all -> cleanenv + cleanderived

make merge-check-ruff-lint    - Run ruff merge check without updating files
make merge-check-ruff-format  - Run ruff merge check without updating files
make merge-check-mypy         - Run mypy merge check without updating files
make merge-check-pyright	  - Run pyright merge check without updating files

make codex-tests              - Run tests for Codex (exit on first failure) (no inference, no codex_disabled)
make gha-tests		          - Run tests for github actions (exit on first failure) (no inference, no gha_disabled)
make test                     - Run unit tests (no inference)
make test-xdist               - Run unit tests with xdist (no inference)
make t                        - Shorthand -> test-xdist
make test-quiet               - Run unit tests without prints (no inference)
make tq                       - Shorthand -> test-quiet
make test-with-prints         - Run tests with prints (no inference)
make tp                       - Shorthand -> test-with-prints
make test-inference           - Run unit tests only for inference (with prints)
make ti                       - Shorthand -> test-inference
make tip                      - Shorthand -> test-inference-with-prints (parallelized inference tests)
make test-ocr                 - Run unit tests only for ocr (with prints)
make to                       - Shorthand -> test-ocr
make test-img-gen             - Run unit tests only for img_gen (with prints)
make test-g					  - Shorthand -> test-img-gen

make check-unused-imports     - Check for unused imports without fixing
make fix-unused-imports       - Fix unused imports with ruff
make fui                      - Shorthand -> fix-unused-imports
make check-TODOs              - Check for TODOs

make openapi-export           - Export the FastAPI OpenAPI schema to the docs site's docs/api-server/openapi/pipelex-api.openapi.yaml
make openapi-check            - Fail if the committed OpenAPI artifact drifts from the app

make kit-sync                 - Re-sync the vendored .pipelex/inference/ tree from the pipelex kit of this repository
make kit-check                - Fail if the vendored .pipelex/inference/ tree drifts from the pipelex kit of this repository

make agent-check              - Install, then fix-unused-imports format lint pyright mypy openapi-check kit-check (for AI agents)
make agent-test               - Install, then run unit tests, silent on success, output on failure (for AI agents)

make check                    - Shorthand -> format lint mypy
make c                        - Shorthand -> check
make cc                       - Shorthand -> cleanderived check
make li                       - Shorthand -> lock install

endef
export HELP

.PHONY: \
	all help env lock install build check-lockstep-pin \
	format lint pyright mypy pylint \
	cleanderived cleanenv cleanall \
	agent-check agent-test \
	test test-xdist t test-quiet tq test-with-prints tp test-inference ti \
	test-img-gen tg test-ocr to codex-tests gha-tests \
	run-all-tests run-manual-trigger-gha-tests run-gha_disabled-tests \
	check c cc \
	merge-check-ruff-lint merge-check-ruff-format merge-check-mypy merge-check-pyright \
	li check-unused-imports fix-unused-imports check-uv check-TODOs \
	openapi-export openapi-check \
	kit-sync kit-check \
	test-count check-test-badge

# `help` is owned by the root Makefile, which composes this $$HELP block with
# $$HELP_LOCAL and $$HELP_DEPLOY_API. Defining `help` here too (this file is
# `-include`d after the root target) would override it and hide those sections —
# so this rule binds only `all`.
all:
	@echo "$$HELP"


##########################################################################################
### SETUP
##########################################################################################

check-uv:
	$(call PRINT_TITLE,"Ensuring uv ≥ $(UV_MIN_VERSION)")
	@command -v uv >/dev/null 2>&1 || { \
		echo "uv not found – installing latest …"; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	}
	@uv self update >/dev/null 2>&1 || true


env: check-uv
	$(call PRINT_TITLE,"Creating virtual environment")
	@if [ ! -d $(VIRTUAL_ENV) ]; then \
		echo "Creating Python virtual env in \`${VIRTUAL_ENV}\`"; \
		uv venv $(VIRTUAL_ENV) --python $(PYTHON_VERSION); \
	else \
		echo "Python virtual env already exists in \`${VIRTUAL_ENV}\`"; \
	fi
	@echo "Using Python: $$($(VENV_PYTHON) --version) from $$(which $$(readlink -f $(VENV_PYTHON)))"

# `uv sync` from this directory syncs this member (pipelex-api) with all of its own extras, and
# pipelex with the extras the member's dependency names; upgrading dependencies is done for the whole
# workspace from the repository root.
install: env
	$(call PRINT_TITLE,"Installing dependencies")
	@uv sync --all-extras && \
	echo "Installed pipelex-api dependencies in ${VIRTUAL_ENV} with all extras.";

lock: env
	$(call PRINT_TITLE,"Resolving dependencies without update")
	@uv lock && \
	echo uv lock without update;

# The metadata hook (`hatch_build.py`) pins pipelex to this version in what it builds; the check below is
# what the release workflow runs on its own build before uploading it.
build: env
	$(call PRINT_TITLE,"Building the pipelex-api wheel and sdist")
	@rm -f $(DIST_DIR)/pipelex_api-*
	@uv build --package pipelex-api --out-dir $(DIST_DIR)

check-lockstep-pin:
	$(call PRINT_TITLE,"Checking the lockstep pin in the distributions in $(DIST_DIR)")
	@python3 scripts/check_lockstep_pin.py $(DIST_DIR)

##############################################################################################
############################      Cleaning                        ############################
##############################################################################################

cleanderived:
	$(call PRINT_TITLE,"Erasing derived files and directories")
	@find . -name '.coverage' -delete && \
	find . -wholename '**/*.pyc' -delete && \
	find . -type d -wholename '__pycache__' -exec rm -rf {} + && \
	find . -type d -wholename './.cache' -exec rm -rf {} + && \
	find . -type d -wholename './.mypy_cache' -exec rm -rf {} + && \
	find . -type d -wholename './.ruff_cache' -exec rm -rf {} + && \
	find . -type d -wholename '.pytest_cache' -exec rm -rf {} + && \
	find . -type d -wholename '**/.pytest_cache' -exec rm -rf {} + && \
	find . -type d -wholename './logs/*.log' -exec rm -rf {} + && \
	find . -type d -wholename './.reports/*' -exec rm -rf {} + && \
	echo "Cleaned up derived files and directories";

cleanenv:
	$(call PRINT_TITLE,"Erasing virtual environment")
	rm -rf "$(VIRTUAL_ENV)" && \
	echo "Cleaned up virtual env";

cleanall: cleanderived cleanenv
	@echo "Cleaned up all derived files and directories";

##########################################################################################
### TESTING
##########################################################################################

codex-tests: env
	$(call PRINT_TITLE,"Unit testing for Codex")
	@echo "• Running unit tests for Codex (excluding inference and codex_disabled)"
	$(VENV_PYTEST) --exitfirst --disable-inference -m "(dry_runnable or not inference) and not (needs_output or pipelex_api or codex_disabled)" || [ $$? = 5 ]

gha-tests: env
	$(call PRINT_TITLE,"Unit testing for github actions")
	@echo "• Running unit tests for github actions (excluding inference and gha_disabled)"
	$(VENV_PYTEST) --exitfirst --quiet --disable-inference -m "(dry_runnable or not inference) and not (gha_disabled or pipelex_api)" || [ $$? = 5 ]

run-all-tests: env
	$(call PRINT_TITLE,"Running all unit tests")
	@echo "• Running all unit tests"
	$(VENV_PYTEST) -n auto --exitfirst --quiet

run-manual-trigger-gha-tests: env
	$(call PRINT_TITLE,"Running GHA tests")
	@echo "• Running GHA unit tests for inference, llm, and not gha_disabled"
	$(VENV_PYTEST) --exitfirst --quiet -m "not (gha_disabled or pipelex_api) and (inference or llm)" || [ $$? = 5 ]

run-gha_disabled-tests: env
	$(call PRINT_TITLE,"Running GHA disabled tests")
	@echo "• Running GHA disabled unit tests"
	$(VENV_PYTEST) --exitfirst --quiet -m "gha_disabled" || [ $$? = 5 ]

test: env
	$(call PRINT_TITLE,"Unit testing without prints but displaying logs via pytest for WARNING level and above")
	@echo "• Running unit tests"
	@if [ -n "$(TEST)" ]; then \
		$(VENV_PYTEST) -s -m $(USUAL_PYTEST_MARKERS) -o log_cli=true -o log_level=WARNING -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	else \
		$(VENV_PYTEST) -s -m $(USUAL_PYTEST_MARKERS) -o log_cli=true -o log_level=WARNING $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

test-xdist: env
	$(call PRINT_TITLE,"Unit testing without prints but displaying logs via pytest for WARNING level and above")
	@echo "• Running unit tests"
	@if [ -n "$(TEST)" ]; then \
		$(VENV_PYTEST) -n auto -m $(USUAL_PYTEST_MARKERS) -o log_level=WARNING -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	else \
		$(VENV_PYTEST) -n auto -m $(USUAL_PYTEST_MARKERS) -o log_level=WARNING $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

t: test-xdist
	@echo "> done: t = test-xdist"

test-quiet: env
	$(call PRINT_TITLE,"Unit testing without prints but displaying logs via pytest for WARNING level and above")
	@echo "• Running unit tests"
	@if [ -n "$(TEST)" ]; then \
		$(VENV_PYTEST) -m $(USUAL_PYTEST_MARKERS) -o log_cli=true -o log_level=WARNING -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	else \
		$(VENV_PYTEST) -m $(USUAL_PYTEST_MARKERS) -o log_cli=true -o log_level=WARNING $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

tq: test-quiet
	@echo "> done: tq = test-quiet"

test-with-prints: env
	$(call PRINT_TITLE,"Unit testing with prints and our rich logs")
	@echo "• Running unit tests"
	@if [ -n "$(TEST)" ]; then \
		$(VENV_PYTEST) -s -m $(USUAL_PYTEST_MARKERS) -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	else \
		$(VENV_PYTEST) -s -m $(USUAL_PYTEST_MARKERS) $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

tp: test-with-prints
	@echo "> done: tp = test-with-prints"

test-inference-with-prints: env
	$(call PRINT_TITLE,"Unit testing")
	@if [ -n "$(TEST)" ]; then \
		$(VENV_PYTEST) --pipe-run-mode live -m "inference and not img_gen" -s -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	else \
		$(VENV_PYTEST) --pipe-run-mode live -m "inference and not img_gen" -s $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

test-inference-fast: env
	$(call PRINT_TITLE,"Unit testing")
	@if [ -n "$(TEST)" ]; then \
		$(VENV_PYTEST) -n auto --pipe-run-mode live -m "inference and not img_gen" -s -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	else \
		$(VENV_PYTEST) -n auto --pipe-run-mode live -m "inference and not img_gen" -s $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

tip: test-inference-with-prints
	@echo "> done: tip = test-inference-with-prints"

ti: test-inference-fast
	@echo "> done: ti-fast = test-inference-fast"

ti-dry: env
	$(call PRINT_TITLE,"Unit testing")
	@if [ -n "$(TEST)" ]; then \
		$(VENV_PYTEST) --pipe-run-mode dry --exitfirst -m "inference and not img_gen" -s -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	else \
		$(VENV_PYTEST) --pipe-run-mode dry --exitfirst -m "inference and not img_gen" -s $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

cov: env
	$(call PRINT_TITLE,"Unit testing with coverage")
	@echo "• Running unit tests with coverage"
	@if [ -n "$(TEST)" ]; then \
		$(VENV_PYTEST) --cov=$(if $(PKG),$(PKG),pipelex) -k "$(TEST)" $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
	else \
		$(VENV_PYTEST) --cov=$(if $(PKG),$(PKG),pipelex) $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
	fi

cov-missing: env
	$(call PRINT_TITLE,"Unit testing with coverage and missing lines")
	@echo "• Running unit tests with coverage and missing lines"
	@if [ -n "$(TEST)" ]; then \
		$(VENV_PYTEST) --cov=$(if $(PKG),$(PKG),pipelex) --cov-report=term-missing -k "$(TEST)" $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
	else \
		$(VENV_PYTEST) --cov=$(if $(PKG),$(PKG),pipelex) --cov-report=term-missing $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
	fi

cm: cov-missing
	@echo "> done: cm = cov-missing"

############################################################################################
############################               Linting              ############################
############################################################################################

format: env
	$(call PRINT_TITLE,"Formatting with ruff")
	$(VENV_RUFF) format . --config pyproject.toml

lint: env
	$(call PRINT_TITLE,"Linting with ruff")
	$(VENV_RUFF) check . --fix --config pyproject.toml

pyright: env
	$(call PRINT_TITLE,"Typechecking with pyright")
	$(VENV_PYRIGHT) --pythonpath $(VENV_PYTHON) --project pyproject.toml

mypy: env
	$(call PRINT_TITLE,"Typechecking with mypy")
	$(VENV_MYPY) --config-file pyproject.toml

pylint: env
	$(call PRINT_TITLE,"Linting with pylint")
	$(VENV_PYLINT) --rcfile pyproject.toml pipelex_api tests


##########################################################################################
### MERGE CHECKS
##########################################################################################

merge-check-ruff-format: env
	$(call PRINT_TITLE,"Formatting with ruff")
	$(VENV_RUFF) format --check . --config pyproject.toml

merge-check-ruff-lint: env check-unused-imports
	$(call PRINT_TITLE,"Linting with ruff without fixing files")
	$(VENV_RUFF) check . --config pyproject.toml

merge-check-pyright: env
	$(call PRINT_TITLE,"Typechecking with pyright")
	$(VENV_PYRIGHT) --pythonpath $(VIRTUAL_ENV)/bin/python3 $(if $(LINT_PYTHON_VERSION),--pythonversion $(LINT_PYTHON_VERSION))

merge-check-mypy: env
	$(call PRINT_TITLE,"Typechecking with mypy")
	$(VENV_MYPY) --config-file pyproject.toml $(if $(LINT_PYTHON_VERSION),--python-version $(LINT_PYTHON_VERSION))

merge-check-pylint: env
	$(call PRINT_TITLE,"Linting with pylint")
	$(VENV_PYLINT) --rcfile pyproject.toml .

##########################################################################################
### RUN API
##########################################################################################

run: install
	$(call PRINT_TITLE,"Running API server with uvicorn")
	$(VIRTUAL_ENV)/bin/uvicorn pipelex_api.main:app --reload --log-level debug --port 8081

##########################################################################################
### MISCELLANEOUS
##########################################################################################

check-unused-imports: env
	$(call PRINT_TITLE,"Checking for unused imports without fixing")
	$(VENV_RUFF) check --select=F401 --no-fix .

fix-unused-imports: env
	$(call PRINT_TITLE,"Fixing unused imports")
	$(VENV_RUFF) check --select=F401 --fix .

fui: fix-unused-imports
	@echo "> done: fui = fix-unused-imports"

check-TODOs: env
	$(call PRINT_TITLE,"Checking for TODOs")
	@$(VENV_RUFF) check --select=TD -v .


##########################################################################################
### SHORTHANDS
##########################################################################################

# The drift gates ride along, so a pipelex change that moves the server's wire or the kit fails here,
# in the same change: the OpenAPI artifact and the vendored inference tree both follow the pipelex of
# this commit. `install` comes first because both gates, like the type checkers, must see the
# environment the lock describes, and it makes a fresh worktree's first run provision itself.
agent-check: install fix-unused-imports format lint pyright mypy openapi-check kit-check
	@echo "> done: agent-check"

agent-test: install
	@echo "• Running unit tests..."
	@tmpfile=$$(mktemp); \
	$(VENV_PYTEST) -n auto -m $(USUAL_PYTEST_MARKERS) -o log_level=WARNING --tb=short -q > "$$tmpfile" 2>&1; \
	exit_code=$$?; \
	if [ $$exit_code -ne 0 ]; then grep -vE '\[\s*[0-9]+%\]\s*$$' "$$tmpfile"; fi; \
	rm -f "$$tmpfile"; \
	if [ $$exit_code -eq 0 ]; then echo "• All tests passed."; fi; \
	exit $$exit_code

c: format lint pyright mypy
	@echo "> done: c = check"

cc: cleanderived c
	@echo "> done: cc = cleanderived format lint pyright mypy"

check: cc check-unused-imports pylint openapi-check kit-check
	@echo "> done: check"

li: lock install
	@echo "> done: lock install"

##########################################################################################
### OPENAPI ARTIFACT
##########################################################################################

# The server's pages are part of the pipelex docs site (`docs/api-server/` at the repository root, served by
# the root `make docs`), and the artifact sits among them, so the site publishes it beside the pages that link it.
OPENAPI_ARTIFACT := $(WORKSPACE_ROOT)/docs/api-server/openapi/pipelex-api.openapi.yaml

# These depend on `install` (not `env`) on purpose: `env` only ensures the venv
# directory exists, it never runs `uv sync`. The schema is generated from whatever
# is actually installed in .venv, so without a sync the export/check validates the
# committed artifact against a drifted venv and silently passes where a fresh install
# would see the real drift. pipelex itself is an editable install from the workspace,
# so its models reach the artifact as soon as they change, and `openapi-check` in
# `agent-check` fails the change that moved them when the gate runs.
openapi-export: install
	$(call PRINT_TITLE,"Exporting OpenAPI schema to $(OPENAPI_ARTIFACT)")
	$(VENV_PYTHON) scripts/export_openapi.py $(OPENAPI_ARTIFACT)

openapi-check: install
	$(call PRINT_TITLE,"Checking committed OpenAPI artifact against the app")
	$(VENV_PYTHON) scripts/export_openapi.py --check $(OPENAPI_ARTIFACT)

##########################################################################################
### VENDORED PIPELEX KIT
##########################################################################################

VENDORED_CONFIG_DIR := .pipelex

# The image serves the models `.pipelex/inference/` declares, and pipelex never reads its own
# package's kit once that tree exists, so a kit change reaches the server only when this tree moves
# with it. The root `make up-kit-configs` (`ukc`), the step a kit change already takes, runs the same
# sync, and `kit-check` in `agent-check` fails a change that left the tree behind. The rules (what is
# mirrored, what stays this image's own choice) are in scripts/sync_vendored_kit.py, and the reason
# the tree stays committed rather than generated when the image is built is in CLAUDE.md.
kit-sync: install
	$(call PRINT_TITLE,"Re-syncing $(VENDORED_CONFIG_DIR)/inference/ from the pipelex kit")
	$(VENV_PYTHON) scripts/sync_vendored_kit.py $(VENDORED_CONFIG_DIR)

kit-check: install
	$(call PRINT_TITLE,"Checking $(VENDORED_CONFIG_DIR)/inference/ against the pipelex kit")
	$(VENV_PYTHON) scripts/sync_vendored_kit.py --check $(VENDORED_CONFIG_DIR)
