SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c

ifeq ($(wildcard .env),.env)
include .env
export
endif
VIRTUAL_ENV := $(CURDIR)/.venv
PROJECT_NAME := $(shell grep '^name = ' pyproject.toml | sed -E 's/name = "(.*)"/\1/')

# The "?" is used to make the variable optional, so that it can be overridden by the user.
PYTHON_VERSION ?= 3.13
LINT_PYTHON_VERSION ?=
# Note: VENV_* variables include quotes to handle paths with spaces (e.g., "My Projects/pipelex")
VENV_PYTHON := "$(VIRTUAL_ENV)/bin/python"
VENV_PYTEST := "$(VIRTUAL_ENV)/bin/pytest"
VENV_RUFF := "$(VIRTUAL_ENV)/bin/ruff"
VENV_PYRIGHT := "$(VIRTUAL_ENV)/bin/pyright"
VENV_MYPY := "$(VIRTUAL_ENV)/bin/mypy"
VENV_PIPELEX := "$(VIRTUAL_ENV)/bin/pipelex"
VENV_MKDOCS := "$(VIRTUAL_ENV)/bin/mkdocs"
VENV_MIKE := "$(VIRTUAL_ENV)/bin/mike"
VENV_PYLINT := "$(VIRTUAL_ENV)/bin/pylint"
VENV_PLXT := RUST_LOG=warn "$(VIRTUAL_ENV)/bin/plxt"
VENV_PIPELEX_DEV := "$(VIRTUAL_ENV)/bin/pipelex-dev"
SKELETON_DIR := "$(HOME)/.pipelex-skeleton/"

UV_MIN_VERSION = $(shell grep -m1 'required-version' pyproject.toml | sed -E 's/.*= *"([^<>=, ]+).*/\1/')

USUAL_PYTEST_MARKERS := "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api"

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
make lock                     - Refresh uv.lock without updating anything
make install                  - Create local virtualenv & install all dependencies
make update                   - Upgrade dependencies via uv
make validate                 - Run the setup sequence to validate the config and libraries
make build                    - Build the wheels

make format                   - format with ruff and plxt
make lint                     - lint with ruff and plxt
make ruff-format              - format with ruff format
make ruff-lint                - lint with ruff check
make pyright                  - Check types with pyright
make mypy                     - Check types with mypy
make plxt-format              - Format MTHDS/TOML/PLX files with plxt
make plxt-lint                - Lint MTHDS/TOML/PLX files with plxt

make rules                    - Install agent rules for contributing to Pipelex
make up-kit-configs           - Update kit configs from .pipelex/
make ukc                      - Shorthand -> up-kit-configs
make check-config-sync        - Verify .pipelex and pipelex/kit/configs are in sync
make ccs                      - Shorthand -> check-config-sync
make check-rules              - Verify installed agent rules match kit templates
make check-urls               - Check all URLs in pipelex/urls.py for broken links (quiet)
make cu                       - Check URLs with verbose output (shows details)
make generate-mthds-schema    - Generate JSON Schema for .mthds files
make gms                      - Shorthand -> generate-mthds-schema
make check-mthds-schema       - Check MTHDS JSON Schema is up-to-date
make cms                      - Shorthand -> check-mthds-schema
make update-gateway-models    - Update gateway models reference
make ugm                      - Shorthand -> update-gateway-models
make check-gateway-models     - Check gateway models reference is up-to-date
make cgm                      - Shorthand -> check-gateway-models
make regenerate-test-models   - Regenerate test model fixtures from backend configs
make rtm                      - Shorthand -> regenerate-test-models
make insert-skeleton          - Insert skeleton from $(SKELETON_DIR)

make up                       - Shorthand -> generate-mthds-schema update-gateway-models up-kit-configs rules
make cleanenv                 - Remove virtual env and lock files
make cleanderived             - Remove extraneous compiled files, caches, logs, etc.
make cleanall                 - Remove all -> cleanenv + cleanderived

make merge-check-ruff-lint    - Run ruff merge check without updating files
make merge-check-ruff-format  - Run ruff merge check without updating files
make merge-check-mypy         - Run mypy merge check without updating files
make merge-check-pyright	  - Run pyright merge check without updating files
make merge-check-plxt-format  - Run plxt format check without modifying files
make merge-check-plxt-lint    - Run plxt lint check

make v                        - Shorthand -> validate
make codex-tests              - Run tests for Codex (exit on first failure) (no inference, no codex_disabled)
make gha-tests		          - Run tests for github actions (exit on first failure) (no inference, no gha_disabled)
make test                     - Run unit tests (no inference)
make test-xdist               - Run unit tests with xdist (no inference)
make agent-test               - Run unit tests, silent on success, output on failure (for AI agents)
make t                        - Shorthand -> test-xdist
make test-quiet               - Run unit tests without prints (no inference)
make tq                       - Shorthand -> test-quiet
make test-with-prints         - Run tests with prints (no inference)
make tp                       - Shorthand -> test-with-prints
make tb                       - Shorthand -> `make test-with-prints TEST=test_boot`
make test-inference           - Run unit tests only for inference (with prints)
make ti                       - Shorthand -> test-inference
make ticc                     - Shorthand -> test config coverage (all Portkey configs)
make tip                      - Shorthand -> test-inference-with-prints (parallelized inference tests)
make test-llm			      - Run unit tests only for llm (with prints)
make tl                       - Shorthand -> test-llm
make test-extract             - Run unit tests only for extract (with prints)
make te                       - Shorthand -> test-extract
make test-img-gen             - Run unit tests only for img_gen (with prints)
make test-g					  - Shorthand -> test-img-gen
make test-temporal            - Run temporal tests (SRV=local|testing MODE=live REG=isolated)
make ttm                      - Shorthand -> test-temporal

make check-unused-imports     - Check for unused imports without fixing
make fix-unused-imports       - Fix unused imports with ruff
make fui                      - Shorthand -> fix-unused-imports
make check-TODOs              - Check for TODOs

make docs                     - Serve documentation locally with mkdocs
make docs-check               - Check documentation build with mkdocs
make docs-serve-versioned     - Serve versioned docs locally with mike
make docs-list                - List deployed documentation versions
make docs-deploy VERSION=x.y.z - Deploy docs as version x.y.z (local, no push)
make docs-deploy-stable       - Deploy stable docs with 'latest' alias (CI only)
make docs-deploy-specific-version         - Deploy docs for the current version with 'pre-release' alias (CI only)
make docs-deploy-root          - Deploy root assets (404.html, robots.txt, index.html) to gh-pages
make docs-delete VERSION=x.y.z - Delete a deployed documentation version

make serve-graph              - Start HTTP server to view ReactFlow graphs (PORT=8765, DIR=temp/test_outputs)
make stop-graph-server        - Stop the graph viewer HTTP server
make view-graph               - Start server and open ReactFlow graph in browser

make temporal-server          - Start a local Temporal dev server (requires 'temporal' CLI)
make ts                       - Shorthand -> temporal-server
make temporal-stop            - Kill the local Temporal dev server (port 7233)
make tstop                    - Shorthand -> temporal-stop
make temporal-worker          - Start a Temporal worker (separate process)
make tw                       - Shorthand -> temporal-worker
make temporal-run             - Run a pipe through Temporal (real LLM calls)
make trun                     - Shorthand -> temporal-run
make temporal-run-dry         - Run a pipe through Temporal (dry run, no LLM)
make trund                    - Shorthand -> temporal-run-dry

make check                    - Shorthand -> format lint mypy
make c                        - Shorthand -> check
make cc                       - Shorthand -> cleanderived check
make li                       - Shorthand -> lock install

make test-count               - Count the number of tests
make check-test-badge         - Check if the test count matches the badge value

make test-durations           - Show slowest tests with xdist (TOP=30, MIN=0.5)
make td                       - Shorthand -> test-durations
make test-durations-serial    - Show slowest tests without xdist (TOP=30, MIN=0.5)
make tds                      - Shorthand -> test-durations-serial
make test-time                - Timed test run with xdist (wall clock)
make tt                       - Shorthand -> test-time
make test-time-serial         - Timed test run without xdist (wall clock)
make tts                      - Shorthand -> test-time-serial

endef
export HELP

.PHONY: \
	all help env env-verbose check-uv check-uv-verbose lock install update build \
	format lint ruff-format ruff-lint pyright mypy pylint plxt plxt-format plxt-lint \
    rules up-kit-configs ukc check-config-sync ccs check-rules check-urls cu insert-skeleton \
	cleanderived cleanenv cleanall \
	test test-xdist t test-quiet tq test-with-prints tp test-inference ti \
	test-llm tl test-img-gen tg test-extract te test-temporal ttm codex-tests gha-tests \
	run-all-tests run-manual-trigger-gha-tests run-gha_disabled-tests \
	validate v check c cc agent-check agent-test \
	test-durations td test-durations-serial tds test-time tt test-time-serial tts \
	merge-check-ruff-lint merge-check-ruff-format merge-check-mypy merge-check-pyright merge-check-plxt-format merge-check-plxt-lint \
	li check-unused-imports fix-unused-imports check-TODOs check-uv \
	docs docs-check docs-serve-versioned docs-list docs-deploy docs-deploy-stable docs-deploy-specific-version docs-delete \
	generate-mthds-schema generate-mthds-schema-quiet gms check-mthds-schema cms \
	update-gateway-models update-gateway-models-quiet ugm check-gateway-models cgm up \
	test-count check-test-badge \
	serve-graph serve-graph-bg stop-graph-server view-graph sg vg \
	temporal-server ts temporal-stop tstop temporal-worker tw temporal-worker-router twr temporal-worker-runner twn \
	temporal-run trun temporal-run-dry trund \
	docs-deploy-root

all help:
	@echo "$$HELP"


##########################################################################################
### SETUP
##########################################################################################

# Quiet check-uv: only shows output if uv is missing (needs install)
check-uv:
	@command -v uv >/dev/null 2>&1 || { \
		echo ""; \
		echo "=== [$(PROJECT_NAME)] ===== (check-uv) ====== Ensuring uv ≥ $(UV_MIN_VERSION) =========="; \
		echo "uv not found – installing latest …"; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	}
	@uv self update >/dev/null 2>&1 || true

# Verbose check-uv: always shows output (for setup commands)
check-uv-verbose:
	$(call PRINT_TITLE,"Ensuring uv ≥ $(UV_MIN_VERSION)")
	@command -v uv >/dev/null 2>&1 || { \
		echo "uv not found – installing latest …"; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	}
	@uv self update >/dev/null 2>&1 || true

# Quiet env: only shows output if venv needs to be created
env: check-uv
	@if [ ! -d "$(VIRTUAL_ENV)" ]; then \
		echo ""; \
		echo "=== [$(PROJECT_NAME)] ===== (env) ====== Creating virtual environment ================="; \
		echo "Creating Python virtual env in \`${VIRTUAL_ENV}\`"; \
		uv venv "$(VIRTUAL_ENV)" --python $(PYTHON_VERSION); \
		echo "Using Python: $$($(VENV_PYTHON) --version) from $$(readlink $(VENV_PYTHON) 2>/dev/null || echo $(VENV_PYTHON))"; \
	fi

# Verbose env: always shows output (for setup commands like install, lock, update)
env-verbose: check-uv-verbose
	$(call PRINT_TITLE,"Creating virtual environment")
	@if [ ! -d "$(VIRTUAL_ENV)" ]; then \
		echo "Creating Python virtual env in \`${VIRTUAL_ENV}\`"; \
		uv venv "$(VIRTUAL_ENV)" --python $(PYTHON_VERSION); \
	else \
		echo "Python virtual env already exists in \`${VIRTUAL_ENV}\`"; \
	fi
	@echo "Using Python: $$($(VENV_PYTHON) --version) from $$(readlink $(VENV_PYTHON) 2>/dev/null || echo $(VENV_PYTHON))"

install: env-verbose
	$(call PRINT_TITLE,"Installing dependencies")
	@. "$(VIRTUAL_ENV)/bin/activate" && \
	uv sync --all-extras && \
	echo "Installed Pipelex dependencies in ${VIRTUAL_ENV} with all extras.";
	@$(MAKE) --silent regenerate-test-models-quiet

lock: env
	$(call PRINT_TITLE,"Resolving dependencies without update")
	@uv lock && \
	echo uv lock without update;

plxt: env ## Rebuild and reinstall plxt CLI from local vscode-pipelex source
	$(call PRINT_TITLE,"Reinstalling plxt from source")
	@. "$(VIRTUAL_ENV)/bin/activate" && \
	uv sync --all-extras --reinstall-package pipelex-tools && \
	echo "Reinstalled plxt in ${VIRTUAL_ENV}";

update: env
	$(call PRINT_TITLE,"Updating all dependencies")
	@uv lock --upgrade && \
	uv sync --all-extras && \
	echo "Updated dependencies in ${VIRTUAL_ENV}";

validate: env
	$(call PRINT_TITLE,"Running setup sequence")
	$(VENV_PIPELEX) validate --all

build: env
	$(call PRINT_TITLE,"Building the wheels")
	@uv build

rules: env
	$(call PRINT_TITLE,"Installing agent rules for contributing to Pipelex")
	$(VENV_PIPELEX_DEV) kit rules --set all

check-rules: env
	$(call PRINT_TITLE,"Checking installed agent rules against templates")
	$(VENV_PIPELEX_DEV) check-rules --quiet

check-urls: env
	$(call PRINT_TITLE,"Checking URLs in pipelex/urls.py for broken links")
	$(VENV_PIPELEX_DEV) check-urls --quiet

cu: env
	$(call PRINT_TITLE,"Checking URLs in pipelex/urls.py for broken links with detailed output")
	$(VENV_PIPELEX_DEV) check-urls

up-kit-configs:
	$(call PRINT_TITLE,"Updating kit configs from .pipelex/")
	@rsync -av --delete \
		--exclude='.DS_Store' \
		--exclude='pipelex_service.toml' \
		--exclude='pipelex_override.toml' \
		--exclude='telemetry_override.toml' \
		--exclude='storage' \
		--exclude='temporal-payload-store' \
		--exclude='traces' \
		--exclude='x_custom_llm_deck.toml' \
		--exclude='x_custom_extract_deck.toml' \
		--exclude='mthds_schema.json' \
		.pipelex/ pipelex/kit/configs/

ukc: up-kit-configs
	@echo "> done: ukc = up-kit-configs"

check-config-sync: env
	$(call PRINT_TITLE,"Checking config sync between .pipelex and pipelex/kit/configs")
	$(VENV_PIPELEX_DEV) check-config-sync --quiet

ccs: check-config-sync
	@echo "> done: ccs = check-config-sync"

generate-mthds-schema: env
	$(call PRINT_TITLE,"Generating MTHDS JSON Schema")
	$(VENV_PIPELEX_DEV) generate-mthds-schema

generate-mthds-schema-quiet: env
	$(VENV_PIPELEX_DEV) generate-mthds-schema --quiet

gms: generate-mthds-schema
	@echo "> done: gms = generate-mthds-schema"

check-mthds-schema: env
	$(call PRINT_TITLE,"Checking MTHDS JSON Schema is up-to-date")
	$(VENV_PIPELEX_DEV) check-mthds-schema --quiet

cms: check-mthds-schema
	@echo "> done: cms = check-mthds-schema"

update-gateway-models: env
	$(call PRINT_TITLE,"Updating gateway models reference")
	$(VENV_PIPELEX_DEV) update-gateway-models

update-gateway-models-quiet: env
	$(VENV_PIPELEX_DEV) update-gateway-models --quiet

ugm: update-gateway-models
	@echo "> done: ugm = update-gateway-models"

check-gateway-models: env
	$(call PRINT_TITLE,"Checking gateway models reference is up-to-date")
	$(VENV_PIPELEX_DEV) check-gateway-models --quiet

cgm: check-gateway-models
	@echo "> done: cgm = check-gateway-models"

sync-main-config: env
	$(call PRINT_TITLE,"Syncing main config to kit and project configs")
	$(VENV_PIPELEX_DEV) sync-main-config --quiet

smc: sync-main-config
	@echo "> done: smc = sync-main-config"

smc-dry: env
	$(call PRINT_TITLE,Previewing main config sync - dry run)
	$(VENV_PIPELEX_DEV) sync-main-config --dry-run

# Support PROF as shorthand for TEST_PROFILE
ifdef PROF
TEST_PROFILE := $(PROF)
endif
TEST_PROFILE ?= dev

regenerate-test-models: env
	$(call PRINT_TITLE,"Regenerating test model fixtures")
	$(VENV_PIPELEX_DEV) preprocess-test-models --generate-fixtures --profile $(TEST_PROFILE)

rtm: regenerate-test-models
	@echo "> done: rtm = regenerate-test-models"

regenerate-test-models-quiet: env
	$(call PRINT_TITLE,"Regenerating test model fixtures")
	@$(VENV_PIPELEX_DEV) preprocess-test-models --generate-fixtures --profile $(TEST_PROFILE) > /dev/null 2>&1

rtm-full: env
	$(call PRINT_TITLE,"Regenerating test model fixtures with full profile")
	$(VENV_PIPELEX_DEV) preprocess-test-models --generate-fixtures --profile full

insert-skeleton:
	@if [ ! -d $(SKELETON_DIR) ]; then \
			echo "Error: Skeleton directory $(SKELETON_DIR) not found"; \
			exit 1; \
	fi
	@cp -rn $(SKELETON_DIR). .
	@echo "Skeleton files inserted from $(SKELETON_DIR)"

##########################################################################################
### CLEANING
##########################################################################################

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
	rm -f tests/integration/pipelex/fixtures/_generated_model_sets.py && \
	rm -f .pipelex-dev/model_availability.json && \
	rm -rf derived/ && \
	echo "Cleaned up derived files and directories";

cleanenv:
	$(call PRINT_TITLE,"Erasing virtual environment")
	find . -name 'uv.lock' -delete && \
	rm -rf "$(VIRTUAL_ENV)" && \
	echo "Cleaned up virtual env and dependency lock files";

cleanconfig:
	$(call PRINT_TITLE,"Erasing config files and directories")
	@find . -type d -wholename './.pipelex' -exec rm -rf {} + && \
	echo "Cleaned up .pipelex";

cleanall: cleanderived cleanenv cleanconfig
	@echo "Cleaned up all derived files and directories";

##########################################################################################
### TESTING
##########################################################################################

codex-tests: env
	$(call PRINT_TITLE,"Unit testing for Codex")
	@echo "• Regenerating test model fixtures with ci profile"
	$(VENV_PIPELEX_DEV) preprocess-test-models --generate-fixtures --profile ci
	@echo "• Running unit tests for Codex (excluding inference and codex_disabled)"
	$(VENV_PYTEST) -n auto --exitfirst -m "(dry_runnable or not inference) and not (pipelex_api or codex_disabled)" || [ $$? = 5 ]

gha-tests: env
	$(call PRINT_TITLE,"Unit testing for github actions")
	@echo "• Regenerating test model fixtures with ci profile"
	$(VENV_PIPELEX_DEV) preprocess-test-models --generate-fixtures --profile ci
	@echo "• Running unit tests for github actions (excluding inference and gha_disabled)"
	$(VENV_PYTEST) -n auto --max-worker-restart=2 --timeout=180 --timeout-method=thread --tb=short -m "(dry_runnable or not inference) and not (gha_disabled or pipelex_api)" || [ $$? = 5 ]

run-all-tests: env
	$(call PRINT_TITLE,"Running all unit tests")
	@echo "• Regenerating test model fixtures"
	$(VENV_PIPELEX_DEV) preprocess-test-models --generate-fixtures --profile $(TEST_PROFILE)
	@echo "• Running all unit tests"
	$(VENV_PYTEST) -n auto --exitfirst --quiet

run-manual-trigger-gha-tests: env
	$(call PRINT_TITLE,"Running GHA tests")
	@echo "• Regenerating test model fixtures with ci profile"
	$(VENV_PIPELEX_DEV) preprocess-test-models --generate-fixtures --profile ci
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
		if [ "$(TEST)" = "LF" ] || [ "$(TEST)" = "lf" ]; then \
			$(VENV_PYTEST) -s -m $(USUAL_PYTEST_MARKERS) -o log_cli=true -o log_level=WARNING --lf $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		else \
			$(VENV_PYTEST) -s -m $(USUAL_PYTEST_MARKERS) -o log_cli=true -o log_level=WARNING -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		fi; \
	else \
		$(VENV_PYTEST) -s -m $(USUAL_PYTEST_MARKERS) -o log_cli=true -o log_level=WARNING $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

test-xdist: env
	$(call PRINT_TITLE,"Unit testing without prints but displaying logs via pytest for WARNING level and above")
	@echo "• Running unit tests"
	@if [ -n "$(TEST)" ]; then \
		if [ "$(TEST)" = "LF" ] || [ "$(TEST)" = "lf" ]; then \
			$(VENV_PYTEST) -n auto -m $(USUAL_PYTEST_MARKERS) -o log_level=WARNING --lf $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		else \
			$(VENV_PYTEST) -n auto -m $(USUAL_PYTEST_MARKERS) -o log_level=WARNING -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		fi; \
	else \
		$(VENV_PYTEST) -n auto -m $(USUAL_PYTEST_MARKERS) -o log_level=WARNING $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

t: test-xdist
	@echo "> done: t = test-xdist"

test-quiet: env
	$(call PRINT_TITLE,"Unit testing without prints but displaying logs via pytest for WARNING level and above")
	@echo "• Running unit tests"
	@if [ -n "$(TEST)" ]; then \
		if [ "$(TEST)" = "LF" ] || [ "$(TEST)" = "lf" ]; then \
			$(VENV_PYTEST) -m $(USUAL_PYTEST_MARKERS) -o log_cli=true -o log_level=WARNING --lf $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		else \
			$(VENV_PYTEST) -m $(USUAL_PYTEST_MARKERS) -o log_cli=true -o log_level=WARNING -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		fi; \
	else \
		$(VENV_PYTEST) -m $(USUAL_PYTEST_MARKERS) -o log_cli=true -o log_level=WARNING $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

tq: test-quiet
	@echo "> done: tq = test-quiet"

test-with-prints: env
	$(call PRINT_TITLE,"Unit testing with prints and our rich logs")
	@echo "• Running unit tests"
	@if [ -n "$(TEST)" ]; then \
		if [ "$(TEST)" = "LF" ] || [ "$(TEST)" = "lf" ]; then \
			$(VENV_PYTEST) -s -m $(USUAL_PYTEST_MARKERS) --lf $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		else \
			$(VENV_PYTEST) -s -m $(USUAL_PYTEST_MARKERS) -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		fi; \
	else \
		$(VENV_PYTEST) -s -m $(USUAL_PYTEST_MARKERS) $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

tp: test-with-prints
	@echo "> done: tp = test-with-prints"

tb: env
	$(call PRINT_TITLE,"Unit testing a simple boot")
	@echo "• Running unit test test_boot"
	$(VENV_PYTEST) -s -m $(USUAL_PYTEST_MARKERS) -k "test_boot" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,)));

test-inference-with-prints: env
	$(call PRINT_TITLE,"Unit testing")
	@if [ "$(origin TEST_PROFILE)" = "command line" ] || [ "$(origin PROF)" = "command line" ]; then \
		echo "• Regenerating test model fixtures with profile: $(TEST_PROFILE)"; \
		$(VENV_PIPELEX_DEV) preprocess-test-models --generate-fixtures --profile $(TEST_PROFILE); \
	fi
	@if [ -n "$(TEST)" ]; then \
		if [ "$(TEST)" = "LF" ] || [ "$(TEST)" = "lf" ]; then \
			$(VENV_PYTEST) --pipe-run-mode live -m "inference" -s -rfE --lf $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		else \
			$(VENV_PYTEST) --pipe-run-mode live -m "inference" -s -rfE -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		fi; \
	else \
		$(VENV_PYTEST) --pipe-run-mode live -m "inference" -s -rfE $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

test-inference-fast: env
	$(call PRINT_TITLE,"Unit testing")
	@if [ "$(origin TEST_PROFILE)" = "command line" ] || [ "$(origin PROF)" = "command line" ]; then \
		echo "• Regenerating test model fixtures with profile: $(TEST_PROFILE)"; \
		$(VENV_PIPELEX_DEV) preprocess-test-models --generate-fixtures --profile $(TEST_PROFILE); \
	fi
	@if [ -n "$(TEST)" ]; then \
		if [ "$(TEST)" = "LF" ] || [ "$(TEST)" = "lf" ]; then \
			$(VENV_PYTEST) -n auto --pipe-run-mode live -m "inference" -s -rfE --lf $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		else \
			$(VENV_PYTEST) -n auto --pipe-run-mode live -m "inference" -s -rfE -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		fi; \
	else \
		$(VENV_PYTEST) -n auto --pipe-run-mode live -m "inference" -s -rfE $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

tip: test-inference-with-prints
	@echo "> done: tip = test-inference-with-prints"

ti: test-inference-fast
	@echo "> done: ti-fast = test-inference-fast"

ticc: env
	$(call PRINT_TITLE,"Config coverage inference testing")
	@$(VENV_PIPELEX_DEV) preprocess-test-models --generate-fixtures --profile all_configs_gw --quiet
	$(VENV_PYTEST) -n auto --pipe-run-mode live -m "inference" -s -rfE -k "TestConfigCoverage" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,)))
	@echo "> done: ticc = test-inference config coverage (all Portkey configs)"

ti-dry: env
	$(call PRINT_TITLE,"Unit testing")
	@if [ -n "$(TEST)" ]; then \
		if [ "$(TEST)" = "LF" ] || [ "$(TEST)" = "lf" ]; then \
			$(VENV_PYTEST) --pipe-run-mode dry --exitfirst -m "inference" -s -rfE --lf $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		else \
			$(VENV_PYTEST) --pipe-run-mode dry --exitfirst -m "inference" -s -rfE -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		fi; \
	else \
		$(VENV_PYTEST) --pipe-run-mode dry --exitfirst -m "inference" -s -rfE $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

test-llm: env
	$(call PRINT_TITLE,"Unit testing LLM")
	@if [ "$(origin TEST_PROFILE)" = "command line" ] || [ "$(origin PROF)" = "command line" ]; then \
		echo "• Regenerating test model fixtures with profile: $(TEST_PROFILE)"; \
		$(VENV_PIPELEX_DEV) preprocess-test-models --generate-fixtures --profile $(TEST_PROFILE); \
	fi
	@if [ -n "$(TEST)" ]; then \
		if [ "$(TEST)" = "LF" ] || [ "$(TEST)" = "lf" ]; then \
			$(VENV_PYTEST) --pipe-run-mode live --exitfirst -m "llm" -s --lf $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		else \
			$(VENV_PYTEST) --pipe-run-mode live --exitfirst -m "llm" -s -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		fi; \
	else \
		$(VENV_PYTEST) --pipe-run-mode live --exitfirst -m "llm" -s $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

tl: test-llm
	@echo "> done: tl = test-llm"

test-extract: env
	$(call PRINT_TITLE,"Unit testing Extract")
	@if [ "$(origin TEST_PROFILE)" = "command line" ] || [ "$(origin PROF)" = "command line" ]; then \
		echo "• Regenerating test model fixtures with profile: $(TEST_PROFILE)"; \
		$(VENV_PIPELEX_DEV) preprocess-test-models --generate-fixtures --profile $(TEST_PROFILE); \
	fi
	@if [ -n "$(TEST)" ]; then \
		if [ "$(TEST)" = "LF" ] || [ "$(TEST)" = "lf" ]; then \
			$(VENV_PYTEST) --pipe-run-mode live --exitfirst -m "extract" -s --lf $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		else \
			$(VENV_PYTEST) --pipe-run-mode live --exitfirst -m "extract" -s -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		fi; \
	else \
		$(VENV_PYTEST) --pipe-run-mode live --exitfirst -m "extract" -s $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

te: test-extract
	@echo "> done: te = test-extract"

test-img-gen: env
	$(call PRINT_TITLE,"Unit testing Image Generation")
	@if [ "$(origin TEST_PROFILE)" = "command line" ] || [ "$(origin PROF)" = "command line" ]; then \
		echo "• Regenerating test model fixtures with profile: $(TEST_PROFILE)"; \
		$(VENV_PIPELEX_DEV) preprocess-test-models --generate-fixtures --profile $(TEST_PROFILE); \
	fi
	@if [ -n "$(TEST)" ]; then \
		if [ "$(TEST)" = "LF" ] || [ "$(TEST)" = "lf" ]; then \
			$(VENV_PYTEST) --pipe-run-mode live --exitfirst -m "img_gen" -s --lf $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		else \
			$(VENV_PYTEST) --pipe-run-mode live --exitfirst -m "img_gen" -s -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		fi; \
	else \
		$(VENV_PYTEST) --pipe-run-mode live --exitfirst -m "img_gen" -s $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

tg: test-img-gen
	@echo "> done: tg = test-img-gen"

SRV ?=
MODE ?=
REG ?=
TEMPORAL_PYTEST_MARKERS := $(if $(filter live,$(MODE)),"temporal","temporal and (dry_runnable or not inference)")
TEMPORAL_TESTS_DIR := tests/integration/pipelex/temporal/

test-temporal: env
	$(call PRINT_TITLE,"Unit testing Temporal")
	@if [ -n "$(TEST)" ]; then \
		if [ "$(TEST)" = "LF" ] || [ "$(TEST)" = "lf" ]; then \
			$(VENV_PYTEST) --exitfirst -m $(TEMPORAL_PYTEST_MARKERS) -s --lf \
				$(if $(SRV),--temporal-server $(SRV),) \
				$(if $(REG),--class-registry $(REG),) \
				$(if $(filter live,$(MODE)),--pipe-run-mode live,) \
				$(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))) \
				$(TEMPORAL_TESTS_DIR); \
		else \
			$(VENV_PYTEST) --exitfirst -m $(TEMPORAL_PYTEST_MARKERS) -s -k "$(TEST)" \
				$(if $(SRV),--temporal-server $(SRV),) \
				$(if $(REG),--class-registry $(REG),) \
				$(if $(filter live,$(MODE)),--pipe-run-mode live,) \
				$(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))) \
				$(TEMPORAL_TESTS_DIR); \
		fi; \
	else \
		$(VENV_PYTEST) --exitfirst -m $(TEMPORAL_PYTEST_MARKERS) -s \
			$(if $(SRV),--temporal-server $(SRV),) \
			$(if $(REG),--class-registry $(REG),) \
			$(if $(filter live,$(MODE)),--pipe-run-mode live,) \
			$(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))) \
			$(TEMPORAL_TESTS_DIR); \
	fi

ttm: test-temporal
	@echo "> done: ttm = test-temporal"

test-pipelex-api: env
	$(call PRINT_TITLE,"Unit testing")
	@if [ -n "$(TEST)" ]; then \
		if [ "$(TEST)" = "LF" ] || [ "$(TEST)" = "lf" ]; then \
			$(VENV_PYTEST) --exitfirst -m "pipelex_api" -s --lf $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		else \
			$(VENV_PYTEST) --exitfirst -m "pipelex_api" -s -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
		fi; \
	else \
		$(VENV_PYTEST) --exitfirst -m "pipelex_api" -s $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

ta: test-pipelex-api
	@echo "> done: ta = test-pipelex-api"

agent-test: env
	@echo "• Running unit tests..."
	@tmpfile=$$(mktemp); \
	$(VENV_PYTEST) -n auto -m $(USUAL_PYTEST_MARKERS) -o log_level=WARNING --tb=short -q > "$$tmpfile" 2>&1; \
	exit_code=$$?; \
	if [ $$exit_code -ne 0 ]; then grep -vE '\[\s*[0-9]+%\]\s*$$' "$$tmpfile"; fi; \
	rm -f "$$tmpfile"; \
	if [ $$exit_code -eq 0 ]; then echo "• All tests passed."; fi; \
	exit $$exit_code

##########################################################################################
### TEST DIAGNOSTICS
##########################################################################################

TOP ?= 30
MIN ?= 0.5

test-durations: env
	$(call PRINT_TITLE,"Slowest tests - xdist - top=$(TOP) min=$(MIN)s")
	$(VENV_PYTEST) -n auto -m $(USUAL_PYTEST_MARKERS) -o log_level=WARNING --durations=$(TOP) --durations-min=$(MIN) --tb=no -q

td: test-durations
	@echo "> done: td = test-durations"

test-durations-serial: env
	$(call PRINT_TITLE,"Slowest tests - serial - top=$(TOP) min=$(MIN)s")
	$(VENV_PYTEST) -p no:xdist -m $(USUAL_PYTEST_MARKERS) -o log_level=WARNING --durations=$(TOP) --durations-min=$(MIN) --tb=no -q

tds: test-durations-serial
	@echo "> done: tds = test-durations-serial"

test-time: env
	$(call PRINT_TITLE,"Timed test run - xdist")
	@time $(VENV_PYTEST) -n auto -m $(USUAL_PYTEST_MARKERS) -o log_level=WARNING --tb=no -q --no-header 2>&1 | tail -1

tt: test-time
	@echo "> done: tt = test-time"

test-time-serial: env
	$(call PRINT_TITLE,"Timed test run - serial")
	@time $(VENV_PYTEST) -p no:xdist -m $(USUAL_PYTEST_MARKERS) -o log_level=WARNING --tb=no -q --no-header 2>&1 | tail -1

tts: test-time-serial
	@echo "> done: tts = test-time-serial"

cov: env
	$(call PRINT_TITLE,"Unit testing with coverage")
	@echo "• Running unit tests with coverage"
	@if [ -n "$(TEST)" ]; then \
		if [ "$(TEST)" = "LF" ] || [ "$(TEST)" = "lf" ]; then \
			$(VENV_PYTEST) --cov=$(if $(PKG),$(PKG),pipelex) --lf $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
		else \
			$(VENV_PYTEST) --cov=$(if $(PKG),$(PKG),pipelex) -k "$(TEST)" $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
		fi; \
	else \
		$(VENV_PYTEST) --cov=$(if $(PKG),$(PKG),pipelex) $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
	fi

cov-missing: env
	$(call PRINT_TITLE,"Unit testing with coverage and missing lines")
	@echo "• Running unit tests with coverage and missing lines"
	@if [ -n "$(TEST)" ]; then \
		if [ "$(TEST)" = "LF" ] || [ "$(TEST)" = "lf" ]; then \
			$(VENV_PYTEST) --cov=$(if $(PKG),$(PKG),pipelex) --cov-report=term-missing --lf $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
		else \
			$(VENV_PYTEST) --cov=$(if $(PKG),$(PKG),pipelex) --cov-report=term-missing -k "$(TEST)" $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
		fi; \
	else \
		$(VENV_PYTEST) --cov=$(if $(PKG),$(PKG),pipelex) --cov-report=term-missing $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
	fi

cm: cov-missing
	@echo "> done: cm = cov-missing"

##########################################################################################
### FORMATTING, LINTING, AND TYPECHECKING
##########################################################################################

ruff-format: env
	$(call PRINT_TITLE,"Formatting with ruff")
	$(VENV_RUFF) format . --config pyproject.toml

ruff-lint: env
	$(call PRINT_TITLE,"Linting with ruff")
	$(VENV_RUFF) check . --fix --config pyproject.toml

plxt-format: env
	$(call PRINT_TITLE,"Formatting MTHDS/TOML with plxt")
	$(VENV_PLXT) fmt

plxt-lint: env
	$(call PRINT_TITLE,"Linting MTHDS/TOML with plxt")
	$(VENV_PLXT) lint

format: ruff-format plxt-format
	@echo "> done: format = ruff-format plxt-format"

lint: ruff-lint plxt-lint
	@echo "> done: lint = ruff-lint plxt-lint"

pyright: env
	$(call PRINT_TITLE,"Typechecking with pyright")
	$(VENV_PYRIGHT) --pythonpath $(VENV_PYTHON) --project pyproject.toml

mypy: env
	$(call PRINT_TITLE,"Typechecking with mypy")
	$(VENV_MYPY) --config-file pyproject.toml

pylint: env
	$(call PRINT_TITLE,"Linting with pylint")
	$(VENV_PYLINT) --rcfile pyproject.toml pipelex tests


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
	$(VENV_PYRIGHT) --pythonpath $(VENV_PYTHON) --project pyproject.toml $(if $(LINT_PYTHON_VERSION),--pythonversion $(LINT_PYTHON_VERSION))

merge-check-mypy: env
	$(call PRINT_TITLE,"Typechecking with mypy")
	$(VENV_MYPY) --config-file pyproject.toml $(if $(LINT_PYTHON_VERSION),--python-version $(LINT_PYTHON_VERSION))

merge-check-pylint: env
	$(call PRINT_TITLE,"Linting with pylint")
	$(VENV_PYLINT) --rcfile pyproject.toml .

merge-check-plxt-format: env
	$(call PRINT_TITLE,"Checking MTHDS/TOML formatting with plxt")
	$(VENV_PLXT) fmt --check

merge-check-plxt-lint: env
	$(call PRINT_TITLE,"Linting MTHDS/TOML with plxt")
	$(VENV_PLXT) lint

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
### DOCUMENTATION
##########################################################################################

# Extract version from pyproject.toml for docs deployment
DOCS_VERSION := $(shell grep -m1 '^version = ' pyproject.toml | sed -E 's/version = "(.*)"/\1/')
SITE_DOMAIN := $(shell cat docs/CNAME 2>/dev/null | tr -d '[:space:]')

# Authoritative robots.txt for the domain root (docs.pipelex.com/robots.txt).
# Deployed by docs-deploy-root. Note: docs/robots.txt is a no-op — it only
# lands at /latest/robots.txt, which crawlers ignore per RFC 9309.
#
# Targeted Disallow: block versioned paths and non-content pages, allow
# everything else (root-level files like /sitemap.xml, /llms.txt are
# implicitly allowed).
define ROOT_ROBOTS_TXT
User-agent: *
Allow: /latest/
Allow: /sitemap.xml
Allow: /llms.txt
Allow: /llms-full.txt
Disallow: /0.
Disallow: /pre-release/
Disallow: /404.html

Sitemap: https://$(SITE_DOMAIN)/sitemap.xml
endef
export ROOT_ROBOTS_TXT

docs: env
	$(call PRINT_TITLE,"Serving documentation with mkdocs")
	$(VENV_MKDOCS) serve -a 127.0.0.1:8000 -f "$(CURDIR)/mkdocs.yml" --watch "$(CURDIR)/docs" -s

docs-check: env
	$(call PRINT_TITLE,"Checking documentation build with mkdocs")
	$(VENV_MKDOCS) build --strict

docs-serve-versioned: export PATH := $(VIRTUAL_ENV)/bin:$(PATH)
docs-serve-versioned: env
	$(call PRINT_TITLE,"Serving versioned documentation with mike")
	$(VENV_MIKE) serve

docs-list: export PATH := $(VIRTUAL_ENV)/bin:$(PATH)
docs-list: env
	$(call PRINT_TITLE,"Listing deployed documentation versions")
	$(VENV_MIKE) list

docs-deploy: export PATH := $(VIRTUAL_ENV)/bin:$(PATH)
docs-deploy: env
	$(call PRINT_TITLE,"Deploying documentation version $(if $(VERSION),$(VERSION),$(DOCS_VERSION))")
	$(VENV_MIKE) deploy $(if $(VERSION),$(VERSION),$(DOCS_VERSION))

docs-deploy-stable: export PATH := $(VIRTUAL_ENV)/bin:$(PATH)
docs-deploy-stable: env
	$(call PRINT_TITLE,"Deploying stable documentation $(DOCS_VERSION) with latest alias")
	$(VENV_MIKE) deploy --push --update-aliases $(DOCS_VERSION) latest
	$(VENV_MIKE) set-default --push latest
	$(MAKE) docs-deploy-root

docs-deploy-specific-version-pre-release: export PATH := $(VIRTUAL_ENV)/bin:$(PATH)
docs-deploy-specific-version-pre-release: env
	$(call PRINT_TITLE,"Deploying documentation $(DOCS_VERSION) with pre-release alias")
	$(VENV_MIKE) deploy --push --update-aliases $(DOCS_VERSION) pre-release
	$(MAKE) docs-deploy-root

# Deploy root assets (404.html, robots.txt, index.html, sitemap.xml) to gh-pages.
# The root sitemap is generated from latest/sitemap.xml (not $(DOCS_VERSION)/) so
# that pre-release deploys don't overwrite it with pages not served at /latest/.
# Mike does NOT rewrite sitemap URLs for aliases — latest/sitemap.xml contains
# versioned URLs like /0.20.9/page/, identical to the version directory. The sed
# rewrites any semver path segment (including pre-release suffixes like -rc1) to /latest/.
# WARNING: Do NOT insert comments inside the shell continuation chain below.
# Lines starting with # after a \ continuation become shell comments that silently
# truncate the command.
docs-deploy-root:
ifeq ($(SITE_DOMAIN),)
	$(error SITE_DOMAIN is empty — docs/CNAME is missing or blank. Cannot generate root assets with valid URLs)
endif
	$(call PRINT_TITLE,"Deploying root assets to gh-pages")
	@git fetch origin gh-pages:gh-pages 2>/dev/null || true; \
	TMPDIR=$$(mktemp -d); \
	trap "cd '$(CURDIR)'; git worktree remove '$$TMPDIR' 2>/dev/null || true; rm -rf '$$TMPDIR'" EXIT; \
	git worktree add "$$TMPDIR" gh-pages && \
	cp docs/404.html "$$TMPDIR/404.html" && \
	echo "$$ROOT_ROBOTS_TXT" > "$$TMPDIR/robots.txt" && \
	sed 's/__SITE_DOMAIN__/$(SITE_DOMAIN)/g' docs/root-index.html > "$$TMPDIR/index.html" && \
	sed 's|/[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*[^/]*/|/latest/|g' "$$TMPDIR/latest/sitemap.xml" > "$$TMPDIR/sitemap.xml" && \
	if [ -f "$$TMPDIR/latest/llms.txt" ]; then cp "$$TMPDIR/latest/llms.txt" "$$TMPDIR/llms.txt"; fi && \
	if [ -f "$$TMPDIR/latest/llms-full.txt" ]; then cp "$$TMPDIR/latest/llms-full.txt" "$$TMPDIR/llms-full.txt"; fi && \
	cd "$$TMPDIR" && \
	git add 404.html robots.txt index.html sitemap.xml && \
	(git add -A llms.txt llms-full.txt 2>/dev/null || true) && \
	(git diff --cached --quiet || git commit -m "Update root assets (404.html, robots.txt, index.html, sitemap.xml, llms.txt)") && \
	git push origin gh-pages

docs-delete: export PATH := $(VIRTUAL_ENV)/bin:$(PATH)
docs-delete: env
ifndef VERSION
	$(error VERSION is required. Usage: make docs-delete VERSION=x.y.z)
endif
	$(call PRINT_TITLE,"Deleting documentation version $(VERSION)")
	$(VENV_MIKE) delete --push $(VERSION)

##########################################################################################
### GRAPH VIEWER
##########################################################################################

GRAPH_SERVER_PORT ?= 8765
GRAPH_SERVER_DIR ?= temp/test_outputs

serve-graph:
	$(call PRINT_TITLE,"Starting HTTP server for ReactFlow graphs on port $(GRAPH_SERVER_PORT)")
	@pkill -f "python3 -m http.server $(GRAPH_SERVER_PORT)" 2>/dev/null || true
	@echo "Serving $(GRAPH_SERVER_DIR) at http://localhost:$(GRAPH_SERVER_PORT)"
	@echo "Press Ctrl+C to stop the server"
	@cd "$(CURDIR)" && python3 -m http.server $(GRAPH_SERVER_PORT) --directory $(GRAPH_SERVER_DIR)

serve-graph-bg:
	$(call PRINT_TITLE,"Starting HTTP server for ReactFlow graphs on port $(GRAPH_SERVER_PORT) (background)")
	@pkill -f "python3 -m http.server $(GRAPH_SERVER_PORT)" 2>/dev/null || true
	@cd "$(CURDIR)" && python3 -m http.server $(GRAPH_SERVER_PORT) --directory $(GRAPH_SERVER_DIR) &
	@echo "Server running at http://localhost:$(GRAPH_SERVER_PORT)"
	@echo "Run 'make stop-graph-server' to stop"

stop-graph-server:
	$(call PRINT_TITLE,"Stopping graph viewer HTTP server")
	@pkill -f "python3 -m http.server $(GRAPH_SERVER_PORT)" 2>/dev/null && echo "Server stopped" || echo "No server running on port $(GRAPH_SERVER_PORT)"

view-graph:
	$(call PRINT_TITLE,"Opening ReactFlow graph viewer")
	@pkill -f "python3 -m http.server $(GRAPH_SERVER_PORT)" 2>/dev/null || true
	@cd "$(CURDIR)" && python3 -m http.server $(GRAPH_SERVER_PORT) --directory $(GRAPH_SERVER_DIR) &
	@sleep 1
	@open "http://localhost:$(GRAPH_SERVER_PORT)"
	@echo "Server running at http://localhost:$(GRAPH_SERVER_PORT)"
	@echo "Run 'make stop-graph-server' to stop"

sg: serve-graph
	@echo "> done: sg = serve-graph"

vg: view-graph
	@echo "> done: vg = view-graph"

temporal-server:
	$(call PRINT_TITLE,"Starting local Temporal dev server")
	@if ! command -v temporal >/dev/null 2>&1; then \
		echo "Error: 'temporal' CLI not found. Install it with: brew install temporal"; \
		exit 1; \
	fi
	@echo "• Temporal Web UI will be available at http://localhost:8233"
	@echo "• Temporal gRPC service at localhost:7233"
	@echo "• Press Ctrl+C to stop"
	temporal server start-dev

ts: temporal-server

temporal-stop:
	$(call PRINT_TITLE,"Stopping local Temporal dev server")
	@PID=$$(lsof -tiTCP:7233 -sTCP:LISTEN 2>/dev/null); \
	if [ -z "$$PID" ]; then \
		echo "• No process found on port 7233"; \
	else \
		kill $$PID && echo "• Killed Temporal server (PID $$PID)"; \
	fi

tstop: temporal-stop

TEMPORAL_BUNDLE ?= tests/integration/pipelex/pipes/controller/pipe_sequence/pipe_sequence_1.mthds
TEMPORAL_PIPE ?= simple_text_sequence
TEMPORAL_LIB ?=

TEMPORAL_SCOPE ?=

temporal-worker: env
	$(call PRINT_TITLE,"Starting Temporal worker$(if $(TEMPORAL_SCOPE), (scope: $(TEMPORAL_SCOPE)),)")
	$(if $(TEMPORAL_LIB),PIPELEXPATH=$(TEMPORAL_LIB),) $(VENV_PYTHON) -m pipelex.temporal.worker_cli --is-not-sandboxed \
		$(if $(TEMPORAL_SCOPE),--scope $(TEMPORAL_SCOPE),)

tw: temporal-worker

temporal-worker-router: env
	$(MAKE) temporal-worker TEMPORAL_SCOPE=router

twr: temporal-worker-router

temporal-worker-runner: env
	$(MAKE) temporal-worker TEMPORAL_SCOPE=runner

twn: temporal-worker-runner

temporal-run: env
	$(call PRINT_TITLE,"Running pipe through Temporal")
	$(VENV_PIPELEX) run bundle $(TEMPORAL_BUNDLE) --temporal --mock-inputs --no-logo --graph \
		$(if $(TEMPORAL_PIPE),--pipe $(TEMPORAL_PIPE),)

trun: temporal-run

temporal-run-dry: env
	$(call PRINT_TITLE,"Running pipe through Temporal - dry run")
	$(VENV_PIPELEX) run bundle $(TEMPORAL_BUNDLE) --temporal --dry-run --mock-inputs --no-logo --graph \
		$(if $(TEMPORAL_PIPE),--pipe $(TEMPORAL_PIPE),)

trund: temporal-run-dry

##########################################################################################
### GRAPH UI ASSET SYNC (from mthds-ui)
##########################################################################################

##########################################################################################
### SHORTHANDS
##########################################################################################

c: format lint pyright mypy
	@echo "> done: c = check"

cc: cleanderived regenerate-test-models-quiet generate-mthds-schema-quiet update-gateway-models-quiet c
	@echo "> done: cc = cleanderived regenerate-test-models generate-mthds-schema update-gateway-models format lint pyright mypy"

up: generate-mthds-schema-quiet update-gateway-models-quiet up-kit-configs rules
	@echo "> done: up = generate-mthds-schema update-gateway-models up-kit-configs rules"

check: cc check-unused-imports check-config-sync check-rules check-urls check-gateway-models check-mthds-schema pylint
	@echo "> done: check"

agent-check: fix-unused-imports format lint pyright mypy
	@echo "> done: agent-check"

v: validate
	@echo "> done: v = validate"

li: lock install
	@echo "> done: lock install"


##########################################################################################
### TEST BADGE
##########################################################################################

## Print the number of collected pytest tests (just the integer)
test-count: env
	@COUNT=$$($(VENV_PYTEST) --collect-only --disable-warnings -q | awk 'NF' | wc -l | tr -d ' '); \
	echo $$COUNT

## Compare current test count vs .badges/tests.json -> .message; fail if mismatch
check-test-badge: env
	@EXPECTED=$$($(VENV_PYTHON) -c 'import json;print(int(json.load(open(".badges/tests.json"))["message"]))'); \
	ACTUAL=$$($(VENV_PYTEST) --collect-only --disable-warnings -q | awk 'NF' | wc -l | tr -d ' '); \
	if [ "$$EXPECTED" != "$$ACTUAL" ]; then \
		echo "❌ Test count mismatch: badge=$$EXPECTED, actual=$$ACTUAL"; \
		exit 1; \
	else \
		echo "✅ Test count matches: $$ACTUAL"; \
	fi
