#################################################################################
#################################    HELPERS    #################################
#################################################################################

LOCAL_IMAGE     := pipelex-api:local
HUB_IMAGE_NAME  := pipelex/pipelex-api
HUB_TAG         ?= latest
HUB_IMAGE       := $(HUB_IMAGE_NAME):$(HUB_TAG)
ENV_FILE        ?= .env
CONTAINER_NAME  ?= pipelex-api

define HELP_LOCAL
	$(GREEN)Run the API locally — two ways:$(RESET)

	$(YELLOW)Native (uvicorn, hot reload — fastest dev loop):$(RESET)
	make run$(RESET):           Run the API with uvicorn (requires `make install` first).
	make run-wip$(RESET) ($(GREEN)wip$(RESET)):     Run against a LOCAL pipelex checkout (editable overlay). Path: make run-wip PIPELEX_REPO=../_bridge

	$(YELLOW)Docker (closest to what's deployed):$(RESET)
	make docker-build$(RESET):    Build the API image from local source.
	make docker-run$(RESET):      Build + run the image on http://localhost:8081 (foreground, Ctrl+C to stop).
	make docker-run-hub$(RESET):  Pull + run the PUBLISHED Docker Hub image (no local build). Tag: make docker-run-hub HUB_TAG=0.5.0
	make docker-stop$(RESET):     Force-stop the Docker container.
	make docker-logs$(RESET):     Tail Docker container logs.

	$(YELLOW)Local Temporal dev server (when TEMPORAL is enabled in config):$(RESET)
	make temporal-server$(RESET) ($(GREEN)ts$(RESET)):           Start a local Temporal dev server (:7233, UI :8233) WITH search attributes registered.
	make temporal-server-bare$(RESET) ($(GREEN)ts-bare$(RESET)): Start it WITHOUT search attributes (reproduce the missing-attribute error).
	make temporal-stop$(RESET) ($(GREEN)tstop$(RESET)):          Stop the local Temporal dev server.

	$(YELLOW)Send an MTHDS bundle through the API (resolves like `pipelex run bundle`):$(RESET)
	make bundle-run$(RESET) BUNDLE=<dir|.mthds>:      POST the bundle to a running API and print the response (start `make run` first).
	make bundle-validate$(RESET) BUNDLE=<dir|.mthds>: Dry-run validate the bundle via /v1/validate — no pipe_code/inputs, no inference, no cost.
	make bundle-resolve$(RESET) BUNDLE=<dir|.mthds>:  Resolve the bundle to its normalized crate via /v1/resolve — no inference, no cost.
	make bundle-codegen$(RESET) BUNDLE=<dir|.mthds> TARGET=<t>: Project typed artifacts + codegen.lock via /v1/codegen (ts-zod|python-pydantic|python-structures).
	make bundle-curl$(RESET) BUNDLE=<dir|.mthds>:     Emit a ready-to-run curl command for the bundle.
	make bundle-postman$(RESET) BUNDLE=<dir|.mthds>:  Push request(s) into the live Pipelex FastAPI Postman collection.
	make bundle-dry$(RESET) BUNDLE=<dir|.mthds>:      Print the request body only — touch nothing.
	  Optional: ENDPOINT=execute|start|validate|resolve|codegen|build-inputs|build-output|build-runner|both
	  PIPE=<code>  INPUTS=<path>  NAME=<folder>  ALLOW_SIGNATURES=1  TARGET=<codegen target>  OUTPUT_FORMAT=schema|json|python
	  CALLBACK_URL=<url>  BASE_URL=<url>  TOKEN=<bearer>  ARGS=<extra>
	  (the async start endpoint needs CALLBACK_URL — set it here, or via CALLBACK_URL in .env)

endef
export HELP_LOCAL

.PHONY: docker-build docker-run docker-run-hub docker-stop docker-logs
.PHONY: check-pipelex-repo install-wip-pipelex run-wip wip
.PHONY: temporal-server ts temporal-server-bare ts-bare tsb temporal-stop tstop
.PHONY: check-bundle-arg bundle-run bundle-validate bundle-resolve bundle-codegen bundle-curl bundle-postman bundle-dry

#################################################################################
#################################    API    #################################
#################################################################################

# Build the generic pipelex-api image from local source.
docker-build:
	@echo "\n=== Build $(LOCAL_IMAGE) from local source ==="
	docker build --platform linux/amd64 -t $(LOCAL_IMAGE) .

# Run the API on http://localhost:8081, foreground. Reads all env from .env.
# Required: PIPELEX_GATEWAY_API_KEY (only if you use the default routing profile).
# Optional: AUTH_MODE, API_KEY, JWT_SECRET_KEY (see .env.example).
docker-run: docker-build
	@docker rm -f $(CONTAINER_NAME) 2>/dev/null || true
	@test -f $(ENV_FILE) || (echo "ERROR: $(ENV_FILE) not found. Copy .env.example to .env and fill it in." && exit 1)
	@echo "\n=== Run $(LOCAL_IMAGE) on http://localhost:8081  —  Ctrl+C to stop ==="
	docker run --rm --name $(CONTAINER_NAME) -p 8081:8081 \
		--env-file $(ENV_FILE) \
		$(LOCAL_IMAGE)

# Pull and run the PUBLISHED image from Docker Hub — no local checkout/build needed.
# Same env contract as docker-run (reads all env from .env).
# Required: PIPELEX_GATEWAY_API_KEY (only if you use the default routing profile).
# Optional: AUTH_MODE, API_KEY, JWT_SECRET_KEY (see .env.example).
# Override the published tag with HUB_TAG, e.g. make docker-run-hub HUB_TAG=0.5.0
docker-run-hub:
	@docker rm -f $(CONTAINER_NAME) 2>/dev/null || true
	@test -f $(ENV_FILE) || (echo "ERROR: $(ENV_FILE) not found. Copy .env.example to .env and fill it in." && exit 1)
	@echo "\n=== Pull $(HUB_IMAGE) from Docker Hub ==="
	docker pull $(HUB_IMAGE)
	@echo "\n=== Run $(HUB_IMAGE) on http://localhost:8081  —  Ctrl+C to stop ==="
	docker run --rm --name $(CONTAINER_NAME) -p 8081:8081 \
		--env-file $(ENV_FILE) \
		$(HUB_IMAGE)

docker-stop:
	@docker rm -f $(CONTAINER_NAME) 2>/dev/null && echo "Stopped $(CONTAINER_NAME)" || echo "$(CONTAINER_NAME) was not running"

docker-logs:
	docker logs -f $(CONTAINER_NAME)

#################################################################################
###########################   LOCAL PIPELEX (WIP)   #############################
#################################################################################

# Path to your local pipelex checkout — used by the -wip targets to run the API
# against UNRELEASED pipelex code (e.g. a worktree such as ../_bridge), overlaid
# on top of whatever `[tool.uv.sources]` currently resolves. This lets you switch
# which pipelex the API runs WITHOUT hand-editing pyproject.toml. Override the
# path per-invocation, e.g.:  make run-wip PIPELEX_REPO=../_bridge
PIPELEX_REPO ?= ../pipelex

check-pipelex-repo:
	@test -d "$(PIPELEX_REPO)/pipelex" || { echo "ERROR: '$(PIPELEX_REPO)/pipelex' not found. Point PIPELEX_REPO at your pipelex checkout, e.g. make run-wip PIPELEX_REPO=../_bridge"; exit 1; }

# Mirrors pipelex-worker's `install-wip-pipelex`: install your LOCAL pipelex
# working tree (editable, with the API's extras) over the synced version. Depends
# on `install` so the base deps (fastapi, uvicorn, ...) are present, then overlays
# editable pipelex. STICKY — the overlay stays active for a plain `make run` too,
# until you restore the synced version with `make install`. Once editable is in
# place, pipelex code edits are picked up on the next API restart (no reinstall).
install-wip-pipelex: check-pipelex-repo install
	@echo "• Overlaying LOCAL pipelex (editable) from $(PIPELEX_REPO) over the synced version"
	uv pip install --python $(VENV_PYTHON) -e "$(PIPELEX_REPO)[mistralai,anthropic,google,google-genai,bedrock,fal,temporal]"

# Run the API against your LOCAL pipelex working tree (editable install, then run).
# Restore the synced pipelex with `make install`.
run-wip: install-wip-pipelex
	@$(MAKE) run

wip: run-wip

#################################################################################
#################################   TEMPORAL   #################################
#################################################################################

# Pipelex attaches these five custom Keyword search attributes to every workflow
# start. A namespace missing them rejects StartWorkflow with "Namespace <ns> has
# no mapping defined for search attribute ...". `temporal-server` pre-registers
# them so /v1/execute and /v1/start work out of the box;
# `temporal-server-bare` omits them so you can reproduce the missing-attribute
# error (SearchAttributeRegistrationError). Keep in lockstep with
# [temporal.search_attributes].attributes in the pipelex config.
TEMPORAL_SEARCH_ATTRS := PipeCode PipelineRunId SessionId UserId DomainCode

# Start a local Temporal dev server WITH the search attributes registered. Only
# needed when the API runs with TEMPORAL enabled (selected_server pointed at the
# local server). Runs in the foreground — start it in its own terminal.
temporal-server:
	@if ! command -v temporal >/dev/null 2>&1; then \
		echo "ERROR: 'temporal' CLI not found. Install it with: brew install temporal"; \
		exit 1; \
	fi
	@echo "• Temporal Web UI at http://localhost:8233"
	@echo "• Temporal gRPC service at localhost:7233"
	@echo "• Registering search attributes: $(TEMPORAL_SEARCH_ATTRS)"
	@echo "• Press Ctrl+C to stop"
	temporal server start-dev $(foreach attr,$(TEMPORAL_SEARCH_ATTRS),--search-attribute $(attr)=Keyword)

ts: temporal-server

# Start the dev server WITHOUT the search attributes, to reproduce the
# missing-search-attribute error on /v1/execute and /v1/start.
temporal-server-bare:
	@if ! command -v temporal >/dev/null 2>&1; then \
		echo "ERROR: 'temporal' CLI not found. Install it with: brew install temporal"; \
		exit 1; \
	fi
	@echo "• Temporal Web UI at http://localhost:8233"
	@echo "• Temporal gRPC service at localhost:7233"
	@echo "• NO search attributes registered — workflow starts are rejected when [temporal.search_attributes].enabled = true (use this to test the error path)"
	@echo "• Press Ctrl+C to stop"
	temporal server start-dev

ts-bare: temporal-server-bare
tsb: temporal-server-bare

# Stop the local Temporal dev server. Only kills processes on :7233 whose
# command is the Temporal binary, so an unrelated service bound to that port
# is left alone.
temporal-stop:
	@PIDS=$$(lsof -tiTCP:7233 -sTCP:LISTEN 2>/dev/null); \
	if [ -z "$$PIDS" ]; then \
		echo "• No process found on port 7233"; \
	else \
		for PID in $$PIDS; do \
			CMD=$$(ps -p $$PID -o comm= 2>/dev/null); \
			case "$$CMD" in \
				*temporal*) kill $$PID && echo "• Killed Temporal server (PID $$PID)";; \
				*) echo "• Skipped PID $$PID on :7233 — not a Temporal process ($$CMD)";; \
			esac; \
		done; \
	fi

tstop: temporal-stop

#################################################################################
##########################   RUN A BUNDLE VIA THE API   #########################
#################################################################################

# Resolve an MTHDS bundle the same way `pipelex run bundle <path>` does and send
# it to the API as a request — run it directly, dry-run validate it, resolve it
# to its normalized crate, project typed codegen artifacts, emit curl, push a
# Postman query, or just print the body. Runs the skill's helper script with OUR
# venv python.
#
#   make bundle-run      BUNDLE=../pipelex-demos/mthds-wip/fashion_moodboard
#   make bundle-validate BUNDLE=../pipelex-demos/mthds-wip/fashion_moodboard
#   make bundle-resolve  BUNDLE=../pipelex-demos/mthds-wip/fashion_moodboard
#   make bundle-codegen  BUNDLE=../pipelex-demos/mthds-wip/fashion_moodboard TARGET=ts-zod
#   make bundle-curl     BUNDLE=../pipelex-demos/mthds-wip/fashion_moodboard
#   make bundle-postman  BUNDLE=../pipelex-demos/mthds-wip/fashion_moodboard
#   make bundle-dry      BUNDLE=../pipelex-demos/mthds-wip/fashion_moodboard
#
# Only execute/start trigger inference. bundle-validate (/v1/validate),
# bundle-resolve (/v1/resolve), and bundle-codegen (/v1/codegen) are free —
# parse/load/dry-run only — so they hardcode --run. The build routes
# (/v1/build/{inputs,output,runner}) ride the generic targets via ENDPOINT=,
# e.g. `make bundle-run ENDPOINT=build-inputs` or
# `make bundle-postman ENDPOINT=build-output OUTPUT_FORMAT=json`.
#
# Optional pass-throughs: ENDPOINT, PIPE, INPUTS, NAME, ALLOW_SIGNATURES,
# TARGET (codegen only — required), OUTPUT_FORMAT (build-output only),
# RENDER (validate only — e.g. RENDER=markdown reproduces a skill-driven
# validate, response carries rendered_markdown), CALLBACK_URL (all modes);
# BASE_URL, TOKEN (run/curl); ARGS for anything else.
# The async start endpoint requires CALLBACK_URL — pass it here, or set
# CALLBACK_URL in .env (make exports it to the script). bundle-postman needs
# POSTMAN_API_KEY in the environment (it lives in ~/.zshenv, so any zsh-launched
# make has it).
BUNDLE_SCRIPT := .claude/skills/postman-bundle/scripts/build_postman_query.py
BUNDLE_OPTS    = $(if $(ENDPOINT),--endpoint $(ENDPOINT)) $(if $(PIPE),--pipe $(PIPE)) $(if $(INPUTS),--inputs $(INPUTS)) $(if $(NAME),--name $(NAME)) $(if $(ALLOW_SIGNATURES),--allow-signatures) $(if $(TARGET),--target $(TARGET)) $(if $(OUTPUT_FORMAT),--output-format $(OUTPUT_FORMAT)) $(if $(RENDER),--render $(RENDER)) $(if $(CALLBACK_URL),--callback-url '$(CALLBACK_URL)') $(ARGS)
BUNDLE_RUN_OPTS = $(if $(BASE_URL),--base-url $(BASE_URL)) $(if $(TOKEN),--token $(TOKEN))

check-bundle-arg:
	@test -n "$(BUNDLE)" || { echo "ERROR: set BUNDLE=<bundle dir or .mthds file>, e.g. make bundle-run BUNDLE=../pipelex-demos/mthds-wip/fashion_moodboard"; exit 1; }

bundle-run: env check-bundle-arg
	$(call PRINT_TITLE,"Running bundle against the API")
	$(VENV_PYTHON) $(BUNDLE_SCRIPT) $(BUNDLE) --run $(BUNDLE_RUN_OPTS) $(BUNDLE_OPTS)

# Dry-run validate via /v1/validate — hardcodes --endpoint validate (so don't
# pass ENDPOINT here). NAME/ALLOW_SIGNATURES/RENDER/BASE_URL/TOKEN/ARGS still
# apply (RENDER=markdown reproduces a skill-driven validate); PIPE/INPUTS are
# intentionally omitted — the validate endpoint ignores them.
bundle-validate: env check-bundle-arg
	$(call PRINT_TITLE,"Validating bundle via the API - dry-run with no inference")
	$(VENV_PYTHON) $(BUNDLE_SCRIPT) $(BUNDLE) --run --endpoint validate $(if $(ALLOW_SIGNATURES),--allow-signatures) $(if $(RENDER),--render $(RENDER)) $(if $(NAME),--name $(NAME)) $(BUNDLE_RUN_OPTS) $(ARGS)

# Resolve the bundle's closure to its normalized library crate via /v1/resolve —
# no inference, no dry-run sweep, no cost. PIPE/INPUTS are intentionally
# omitted — the crate routes take neither.
bundle-resolve: env check-bundle-arg
	$(call PRINT_TITLE,"Resolving bundle to its normalized crate via the API")
	$(VENV_PYTHON) $(BUNDLE_SCRIPT) $(BUNDLE) --run --endpoint resolve $(if $(NAME),--name $(NAME)) $(BUNDLE_RUN_OPTS) $(ARGS)

# Project typed artifacts + codegen.lock via /v1/codegen — no inference, no
# cost. TARGET is required: ts-zod | python-pydantic | python-structures.
bundle-codegen: env check-bundle-arg
	@test -n "$(TARGET)" || { echo "ERROR: set TARGET=<ts-zod|python-pydantic|python-structures>, e.g. make bundle-codegen BUNDLE=... TARGET=ts-zod"; exit 1; }
	$(call PRINT_TITLE,"Generating typed artifacts via the API codegen route")
	$(VENV_PYTHON) $(BUNDLE_SCRIPT) $(BUNDLE) --run --endpoint codegen --target $(TARGET) $(if $(NAME),--name $(NAME)) $(BUNDLE_RUN_OPTS) $(ARGS)

bundle-curl: env check-bundle-arg
	$(call PRINT_TITLE,"Emitting curl for bundle")
	$(VENV_PYTHON) $(BUNDLE_SCRIPT) $(BUNDLE) --curl $(BUNDLE_RUN_OPTS) $(BUNDLE_OPTS)

bundle-postman: env check-bundle-arg
	$(call PRINT_TITLE,"Pushing Postman query for bundle")
	$(VENV_PYTHON) $(BUNDLE_SCRIPT) $(BUNDLE) $(BUNDLE_OPTS)

bundle-dry: env check-bundle-arg
	$(call PRINT_TITLE,"Bundle request body - dry run only")
	$(VENV_PYTHON) $(BUNDLE_SCRIPT) $(BUNDLE) --dry-run $(BUNDLE_OPTS)
