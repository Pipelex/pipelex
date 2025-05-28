ifeq ($(wildcard .env),.env)
include .env
export
endif
VIRTUAL_ENV := $(CURDIR)/.venv
LOCAL_PYTHON := $(VIRTUAL_ENV)/bin/python3.11
PROJECT_NAME := $(shell grep '^name = ' pyproject.toml | sed -E 's/name = "(.*)"/\1/')

LOCAL_PYTEST := $(VIRTUAL_ENV)/bin/pytest

define GET_UV_VERSION
$(shell awk '/^\[tool.uv\]/{f=1;next} f==1&&/^required-version/{print $$3;exit}' pyproject.toml | tr -d '"')
endef

define PRINT_TITLE
    $(eval PADDED_PROJECT_NAME := $(shell printf '%-15s' "[$(PROJECT_NAME)] " | sed 's/ /=/g'))
    $(eval PADDED_TARGET_NAME := $(shell printf '%-15s' "($@) " | sed 's/ /=/g'))
    $(if $(1),\
		$(eval TITLE := $(shell printf '%s' "=== $(PADDED_PROJECT_NAME) $(PADDED_TARGET_NAME)" | sed 's/[[:space:]]/ /g')$(shell echo " $(1) " | sed 's/[[:space:]]/ /g')),\
		$(eval TITLE := $(shell printf '%s' "=== $(PADDED_PROJECT_NAME) $(PADDED_TARGET_NAME)" | sed 's/[[:space:]]/ /g'))\
	)
	$(eval PADDED_TITLE := $(shell printf '%-126s' "$(TITLE)" | sed 's/ /=/g'))
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
make run-setup                - Run the setup sequence
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
make s                        - Shorthand -> run-setup
make init                     - Run pipelex init
make runtests		          - Run tests for github actions (exit on first failure) (no inference)
make test                     - Run unit tests (no inference)
make test-with-prints         - Run tests with prints (no inference)
make t                        - Shorthand -> test-with-prints
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

.PHONY: all help env lock install update format lint pyright mypy build cleanderived cleanenv run-setup s runtests test test-with-prints t test-inference ti test-imgg tg test-ocr to check cc li merge-check-ruff-lint merge-check-ruff-format merge-check-mypy check-unused-imports fix-unused-imports test-name bump-version check-uv get-uv-version

all help:
	@echo "$$HELP"


##########################################################################################
### SETUP
##########################################################################################

check-uv:
	$(call PRINT_TITLE,"Checking UV version")
	@UV_VERSION=$(GET_UV_VERSION); \
	if [ -z "$$UV_VERSION" ]; then \
		echo "Error: UV version not found in pyproject.toml"; \
		exit 1; \
	fi; \
	echo "UV_VERSION: $$UV_VERSION"; \
	if ! command -v uv >/dev/null 2>&1; then \
		echo "Installing UV version $$UV_VERSION"; \
		curl -LsSf https://astral.sh/uv/$$UV_VERSION/install.sh | sh; \
	elif [ "$$(uv --version | cut -d ' ' -f 2)" != "$$UV_VERSION" ]; then \
		echo "Updating UV to version $$UV_VERSION"; \
		curl -LsSf https://astral.sh/uv/$$UV_VERSION/install.sh | sh; \
	else \
		echo "UV version $$UV_VERSION is already installed"; \
	fi

CURRENT_VERSION := $(shell grep '^version = ' pyproject.toml | sed -E 's/version = "(.*)"/\1/')
NEXT_VERSION := $(shell echo $(CURRENT_VERSION) | awk -F. '{$$NF = $$NF + 1;} 1' | sed 's/ /./g')

get-uv-version:
	@UV_VERSION=$(GET_UV_VERSION); \
	if [ -z "$$UV_VERSION" ]; then \
		echo "Error: UV version not found in pyproject.toml" >&2; \
		exit 1; \
	fi; \
	echo "$$UV_VERSION"

env: check-uv
	$(call PRINT_TITLE,"Creating virtual environment")
	@if [ ! -d $(VIRTUAL_ENV) ]; then \
		echo "Creating Python virtual env in \`${VIRTUAL_ENV}\`"; \
		uv venv $(VIRTUAL_ENV) --python 3.11; \
	else \
		echo "Python virtual env already exists in \`${VIRTUAL_ENV}\`"; \
	fi

init: env
	$(call PRINT_TITLE,"Running `pipelex init` with overwrite")
	pipelex init --overwrite

install: env
	$(call PRINT_TITLE,"Installing dependencies")
	@. $(VIRTUAL_ENV)/bin/activate && \
	uv sync --all-extras && \
	pipelex init --overwrite && \
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

run-setup: env
	$(call PRINT_TITLE,"Running setup sequence")
	pipelex run-setup

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

runtests: env
	$(call PRINT_TITLE,"Unit testing for github actions")
	@echo "• Running unit tests (excluding inference, and gha_disabled)"
	$(LOCAL_PYTEST) --exitfirst --quiet -m "not inference and not gha_disabled" || [ $$? = 5 ]

run-all-tests: env
	$(call PRINT_TITLE,"Running all unit tests")
	@echo "• Running all unit tests"
	$(LOCAL_PYTEST) --exitfirst --quiet

run-manual-trigger-gha-tests: env
	$(call PRINT_TITLE,"Running GHA tests")
	@echo "• Running GHA unit tests for inference, llm, and not gha_disabled"
	$(LOCAL_PYTEST) --exitfirst --quiet -m "not gha_disabled and (inference or llm)" || [ $$? = 5 ]

run-gha_disabled-tests: env
	$(call PRINT_TITLE,"Running GHA disabled tests")
	@echo "• Running GHA disabled unit tests"
	$(LOCAL_PYTEST) --exitfirst --quiet -m "gha_disabled" || [ $$? = 5 ]

test: env
	$(call PRINT_TITLE,"Unit testing without prints but displaying logs via pytest for WARNING level and above")
	@echo "• Running unit tests"
	@if [ -n "$(TEST)" ]; then \
		$(LOCAL_PYTEST) -s -o log_cli=true -o log_level=WARNING -k "$(TEST)" $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
	else \
		$(LOCAL_PYTEST) -s -o log_cli=true -o log_level=WARNING $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
	fi

test-with-prints: env
	$(call PRINT_TITLE,"Unit testing with prints and our rich logs")
	@echo "• Running unit tests"
	@if [ -n "$(TEST)" ]; then \
		$(LOCAL_PYTEST) -s -k "$(TEST)" $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
	else \
		$(LOCAL_PYTEST) -s $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
	fi

t: test-with-prints
	@echo "> done: t = test-with-prints"

test-inference: env
	$(call PRINT_TITLE,"Unit testing")
	@if [ -n "$(TEST)" ]; then \
		$(LOCAL_PYTEST) --exitfirst -m "inference and not imgg" -s -k "$(TEST)" $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
	else \
		$(LOCAL_PYTEST) --exitfirst -m "inference and not imgg" -s $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
	fi

ti: test-inference
	@echo "> done: ti = test-inference"

test-ocr: env
	$(call PRINT_TITLE,"Unit testing ocr")
	@if [ -n "$(TEST)" ]; then \
		$(LOCAL_PYTEST) --exitfirst -m "ocr" -s -k "$(TEST)" $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
	else \
		$(LOCAL_PYTEST) --exitfirst -m "ocr" -s $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
	fi

to: test-ocr
	@echo "> done: to = test-ocr"

test-imgg: env
	$(call PRINT_TITLE,"Unit testing")
	@if [ -n "$(TEST)" ]; then \
		$(LOCAL_PYTEST) --exitfirst -m "imgg" -s -k "$(TEST)" $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
	else \
		$(LOCAL_PYTEST) --exitfirst -m "imgg" -s $(if $(filter 2,$(VERBOSE)),-vv,$(if $(filter 3,$(VERBOSE)),-vvv,-v)); \
	fi

tg: test-imgg
	@echo "> done: tg = test-imgg"

############################################################################################
############################               Linting              ############################
############################################################################################

format: env
	$(call PRINT_TITLE,"Formatting with ruff")
	uv run ruff format .

lint: env
	$(call PRINT_TITLE,"Linting with ruff")
	uv run ruff check . --fix

pyright: env
	$(call PRINT_TITLE,"Typechecking with pyright")
	uv run pyright --pythonpath $(LOCAL_PYTHON)  && \
	echo "Done typechecking with pyright — disregard warning about latest version, it's giving us false positives"

mypy: env
	$(call PRINT_TITLE,"Typechecking with mypy")
	uv run mypy


##########################################################################################
### MERGE CHECKS
##########################################################################################

merge-check-ruff-format: env
	$(call PRINT_TITLE,"Formatting with ruff")
	uv run ruff format --check -v .

merge-check-ruff-lint: env check-unused-imports
	$(call PRINT_TITLE,"Linting with ruff without fixing files")
	uv run ruff check -v .

merge-check-pyright: env
	$(call PRINT_TITLE,"Typechecking with pyright")
	uv run pyright -p pyproject.toml

merge-check-mypy: env
	$(call PRINT_TITLE,"Typechecking with mypy")
	uv run mypy --version && \
	uv run mypy --config-file pyproject.toml

##########################################################################################
### SHORTHANDS
##########################################################################################

check-unused-imports: env
	$(call PRINT_TITLE,"Checking for unused imports without fixing")
	uv run ruff check --select=F401 --no-fix .

c: init format lint pyright mypy
	@echo "> done: c = check"

cc: init cleanderived c
	@echo "> done: cc = init cleanderived init format lint pyright mypy"

check: cc check-unused-imports
	@echo "> done: check"

s: init run-setup
	@echo "> done: s = run-setup"

li: lock install
	@echo "> done: lock install"

check-TODOs: env
	$(call PRINT_TITLE,"Checking for TODOs")
	uv run ruff check --select=TD -v .

fix-unused-imports: env
	$(call PRINT_TITLE,"Fixing unused imports")
	uv run ruff check --select=F401 --fix -v .
