ifeq ($(wildcard .env),.env)
include .env
export
endif
VIRTUAL_ENV := $(CURDIR)/.venv
PROJECT_NAME := $(shell grep '^name = ' pyproject.toml | sed -E 's/name = "(.*)"/\1/')

# The "?" is used to make the variable optional, so that it can be overridden by the user.
PYTHON_VERSION ?= 3.11
VENV_PYTHON := $(VIRTUAL_ENV)/bin/python
VENV_PYTEST := $(VIRTUAL_ENV)/bin/pytest
VENV_RUFF := $(VIRTUAL_ENV)/bin/ruff
VENV_PYRIGHT := $(VIRTUAL_ENV)/bin/pyright
VENV_MYPY := $(VIRTUAL_ENV)/bin/mypy
VENV_PIPELEX := $(VIRTUAL_ENV)/bin/pipelex

UV_MIN_VERSION = $(shell grep -m1 'required-version' pyproject.toml | sed -E 's/.*= *"([^<>=, ]+).*/\1/')

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

make format                   - format with ruff format
make lint                     - lint with ruff check
make pyright                  - Check types with pyright
make mypy                     - Check types with mypy

make cleanenv                 - Remove virtual env and lock files
make cleanderived             - Remove extraneous compiled files, caches, logs, etc.
make cleanlibraries           - Remove pipelex_libraries
make cleanall                 - Remove all -> cleanenv + cleanderived + cleanlibraries
make reinitlibraries          - Remove pipelex_libraries and init libraries again

make merge-check-ruff-lint    - Run ruff merge check without updating files
make merge-check-ruff-format  - Run ruff merge check without updating files
make merge-check-mypy         - Run mypy merge check without updating files
make merge-check-pyright	  - Run pyright merge check without updating files

make rl                       - Shorthand -> reinitlibraries
make v                        - Shorthand -> validate
make init                     - Run `pipelex init-libraries` and `pipelex init-config`
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
make test-ocr                 - Run unit tests only for ocr (with prints)
make to                       - Shorthand -> test-ocr
make test-imgg                - Run unit tests only for imgg (with prints)
make test-g					  - Shorthand -> test-imgg

make check                    - Shorthand -> format lint mypy
make c                        - Shorthand -> check
make cc                       - Shorthand -> cleanderived check
make li                       - Shorthand -> lock install
make check-unused-imports     - Check for unused imports without fixing
make fix-unused-imports       - Fix unused imports with ruff

endef
export HELP

.PHONY: \
	all help env lock install update build \
	format lint pyright mypy \
	cleanderived cleanenv cleanlibraries cleanall \
	test test-xdist t test-quiet tq test-with-prints tp test-inference ti \
	test-imgg tg test-ocr to codex-tests gha-tests \
	run-all-tests run-manual-trigger-gha-tests run-gha_disabled-tests \
	validate v check c cc \
	merge-check-ruff-lint merge-check-ruff-format merge-check-mypy merge-check-pyright \
	li check-unused-imports fix-unused-imports check-uv check-TODOs

all help:
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

init: env
	$(call PRINT_TITLE,"Running pipelex init-libraries and init-config")
	$(VENV_PIPELEX) init-libraries
	$(VENV_PIPELEX) init-config

install: env
	$(call PRINT_TITLE,"Installing dependencies")
	@. $(VIRTUAL_ENV)/bin/activate && \
	uv sync --all-extras && \
	$(VENV_PIPELEX) init-libraries && \
	$(VENV_PIPELEX) init-config && \
	echo "Installed Pipelex dependencies in ${VIRTUAL_ENV} with all extras and initialized Pipelex";

lock: env
	$(call PRINT_TITLE,"Resolving dependencies without update")
	@uv lock && \
	echo uv lock without update;

update: env
	$(call PRINT_TITLE,"Updating all dependencies")
	@uv lock --upgrade && \
	uv sync --all-extras && \
	echo "Updated dependencies in ${VIRTUAL_ENV}";

validate: env
	$(call PRINT_TITLE,"Running setup sequence")
	$(VENV_PIPELEX) validate

build: env
	$(call PRINT_TITLE,"Building the wheels")
	@uv build

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
	find . -name 'uv.lock' -delete && \
	find . -type d -wholename './.venv' -exec rm -rf {} + && \
	echo "Cleaned up virtual env and dependency lock files";

cleanlibraries:
	$(call PRINT_TITLE,"Erasing derived files and directories")
	@find . -type d -wholename './pipelex_libraries' -exec rm -rf {} + && \
	echo "Cleaned up pipelex_libraries";

reinitlibraries: cleanlibraries init
	@echo "Reinitialized pipelex_libraries";

rl: reinitlibraries
	@echo "> done: rl = reinitlibraries"

cleanall: cleanderived cleanenv cleanlibraries
	@echo "Cleaned up all derived files and directories";

##########################################################################################
### TESTING
##########################################################################################

codex-tests: env
	$(call PRINT_TITLE,"Unit testing for Codex")
	@echo "• Running unit tests for Codex (excluding inference and codex_disabled)"
	$(VENV_PYTEST) --exitfirst --quiet -m "not (inference or codex_disabled or pipelex_api)" || [ $$? = 5 ]

gha-tests: env
	$(call PRINT_TITLE,"Unit testing for github actions")
	@echo "• Running unit tests for github actions (excluding inference and gha_disabled)"
	$(VENV_PYTEST) --exitfirst --quiet -m "not (inference or gha_disabled or pipelex_api)" || [ $$? = 5 ]

run-all-tests: env
	$(call PRINT_TITLE,"Running all unit tests")
	@echo "• Running all unit tests"
	$(VENV_PYTEST) --exitfirst --quiet

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
		$(VENV_PYTEST) -s -o log_cli=true -o log_level=WARNING -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	else \
		$(VENV_PYTEST) -s -o log_cli=true -o log_level=WARNING $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

test-xdist: env
	$(call PRINT_TITLE,"Unit testing without prints but displaying logs via pytest for WARNING level and above")
	@echo "• Running unit tests"
	@if [ -n "$(TEST)" ]; then \
		$(VENV_PYTEST) -n auto -o log_level=WARNING -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	else \
		$(VENV_PYTEST) -n auto -o log_level=WARNING $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

t: test-xdist
	@echo "> done: t = test-xdist"

test-quiet: env
	$(call PRINT_TITLE,"Unit testing without prints but displaying logs via pytest for WARNING level and above")
	@echo "• Running unit tests"
	@if [ -n "$(TEST)" ]; then \
		$(VENV_PYTEST) -o log_cli=true -o log_level=WARNING -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	else \
		$(VENV_PYTEST) -o log_cli=true -o log_level=WARNING $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

tq: test-quiet
	@echo "> done: tq = test-quiet"

test-with-prints: env
	$(call PRINT_TITLE,"Unit testing with prints and our rich logs")
	@echo "• Running unit tests"
	@if [ -n "$(TEST)" ]; then \
		$(VENV_PYTEST) -s -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	else \
		$(VENV_PYTEST) -s $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

tp: test-with-prints
	@echo "> done: tp = test-with-prints"

test-inference: env
	$(call PRINT_TITLE,"Unit testing")
	@if [ -n "$(TEST)" ]; then \
		$(VENV_PYTEST) --exitfirst -m "inference and not imgg" -s -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	else \
		$(VENV_PYTEST) --exitfirst -m "inference and not imgg" -s $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

ti: test-inference
	@echo "> done: ti = test-inference"

test-ocr: env
	$(call PRINT_TITLE,"Unit testing ocr")
	@if [ -n "$(TEST)" ]; then \
		$(VENV_PYTEST) --exitfirst -m "ocr" -s -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	else \
		$(VENV_PYTEST) --exitfirst -m "ocr" -s $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

to: test-ocr
	@echo "> done: to = test-ocr"

test-imgg: env
	$(call PRINT_TITLE,"Unit testing")
	@if [ -n "$(TEST)" ]; then \
		$(VENV_PYTEST) --exitfirst -m "imgg" -s -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	else \
		$(VENV_PYTEST) --exitfirst -m "imgg" -s $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

tg: test-imgg
	@echo "> done: tg = test-imgg"

test-pipelex-api: env
	$(call PRINT_TITLE,"Unit testing")
	@if [ -n "$(TEST)" ]; then \
		$(VENV_PYTEST) --exitfirst -m "pipelex_api" -s -k "$(TEST)" $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	else \
		$(VENV_PYTEST) --exitfirst -m "pipelex_api" -s $(if $(filter 1,$(VERBOSE)),-v,$(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,))); \
	fi

ta: test-pipelex-api
	@echo "> done: ta = test-pipelex-api"

############################################################################################
############################               Linting              ############################
############################################################################################

format: env
	$(call PRINT_TITLE,"Formatting with ruff")
	$(VENV_RUFF) format .

lint: env
	$(call PRINT_TITLE,"Linting with ruff")
	$(VENV_RUFF) check . --fix

pyright: env
	$(call PRINT_TITLE,"Typechecking with pyright")
	$(VENV_PYRIGHT) --pythonpath $(VIRTUAL_ENV)/bin/python3  && \
	echo "Done typechecking with pyright — disregard warning about latest version, it's giving us false positives"

mypy: env
	$(call PRINT_TITLE,"Typechecking with mypy")
	$(VENV_MYPY)


##########################################################################################
### MERGE CHECKS
##########################################################################################

merge-check-ruff-format: env
	$(call PRINT_TITLE,"Formatting with ruff")
	$(VENV_RUFF) format --check .

merge-check-ruff-lint: env check-unused-imports
	$(call PRINT_TITLE,"Linting with ruff without fixing files")
	$(VENV_RUFF) check .

merge-check-pyright: env
	$(call PRINT_TITLE,"Typechecking with pyright")
	$(VENV_PYRIGHT) --pythonpath $(VIRTUAL_ENV)/bin/python3

merge-check-mypy: env
	$(call PRINT_TITLE,"Typechecking with mypy")
	$(VENV_MYPY) --config-file pyproject.toml

##########################################################################################
### SHORTHANDS
##########################################################################################

check-unused-imports: env
	$(call PRINT_TITLE,"Checking for unused imports without fixing")
	$(VENV_RUFF) check --select=F401 --no-fix .

c: init format lint pyright mypy
	@echo "> done: c = check"

cc: init cleanderived c
	@echo "> done: cc = init cleanderived init format lint pyright mypy"

check: cc check-unused-imports
	@echo "> done: check"

v: init validate
	@echo "> done: v = validate"

li: lock install
	@echo "> done: lock install"

check-TODOs: env
	$(call PRINT_TITLE,"Checking for TODOs")
	$(VENV_RUFF) check --select=TD -v .

fix-unused-imports: env
	$(call PRINT_TITLE,"Fixing unused imports")
	$(VENV_RUFF) check --select=F401 --fix -v .
