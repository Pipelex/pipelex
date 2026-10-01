#################################################################################
#################################    HELPERS    #################################
#################################################################################

define HELP_DEPLOY_API
	$(GREEN)Deployment Commands:$(RESET)
	make deploy-docker-hub                  - Build, smoke-test and push the image to Docker Hub (the release workflow runs it).
	make deploy-docker-hub-latest           - Point :latest at the already-published :VERSION image, without rebuilding it.
endef
export HELP_DEPLOY_API

###########################################################################
############################ Docker Hub Deploy ############################
###########################################################################

# Builds the public Pipelex API image and publishes it to Docker Hub as
# pipelex/pipelex-api:$(VERSION), and as :latest unless PUSH_LATEST=false, with
# the repository root as the build context (see the Dockerfile's header).
# $(VERSION) is the library's version, read from the root pyproject.toml, so the
# image tag names the pipelex it runs. The image is smoke-tested (`docker-smoke`)
# before anything is pushed, so a build that does not boot, or that reports
# another version, never reaches Docker Hub.
#
# The release workflow runs this target from the commit the release's tag names,
# once both distributions are on PyPI: `.github/workflows/publish-docker-hub.yml`,
# which `publish-pypi.yml` calls and which can also be dispatched on its own to
# retry a failed push. It runs this target only when Docker Hub does not serve
# the version yet, since a rebuild would be a different image under the same
# tag, and passes PUSH_LATEST=false unless the version is the newest stable
# release, so `latest` never moves to a pre-release or back to an older
# release. DOCKER_HUB_TOKEN comes from that workflow's secret, through the
# environment: the recipe reads it from the shell rather than expanding it into
# the command line. This repository only publishes to Docker Hub; anything
# beyond (private registries, ECR/ACR/GCR, ECS/k8s deploys) is the user's
# responsibility, typically in a separate infra repo.
PUSH_LATEST ?= true

.PHONY: deploy-docker-hub
deploy-docker-hub:
	@echo "\n########################### Docker Hub Build ##########################"
	@test -n "$$DOCKER_HUB_TOKEN" || { echo "ERROR: DOCKER_HUB_TOKEN is not set in the environment."; exit 1; }
	@case "$(PUSH_LATEST)" in true|false) ;; *) echo "ERROR: PUSH_LATEST must be true or false, got '$(PUSH_LATEST)'."; exit 1;; esac
	@echo "Logging in to Docker Hub..."
	@printf '%s' "$$DOCKER_HUB_TOKEN" | docker login --username pipelex --password-stdin

	@echo "Building Docker image for Docker Hub..."
	docker build --platform linux/amd64 -f $(CURDIR)/Dockerfile -t pipelex-api:$(VERSION) $(WORKSPACE_ROOT)
	@$(MAKE) --no-print-directory docker-smoke SMOKE_IMAGE=pipelex-api:$(VERSION)

	@echo "Pushing to Docker Hub..."
	docker tag pipelex-api:$(VERSION) pipelex/pipelex-api:$(VERSION)
	docker push pipelex/pipelex-api:$(VERSION)
	@if [ "$(PUSH_LATEST)" = "true" ]; then \
		docker tag pipelex-api:$(VERSION) pipelex/pipelex-api:latest && \
		docker push pipelex/pipelex-api:latest && \
		echo "✓ Built and pushed pipelex/pipelex-api:$(VERSION) and :latest to Docker Hub"; \
	else \
		echo "✓ Built and pushed pipelex/pipelex-api:$(VERSION) to Docker Hub; :latest left where it was"; \
	fi
	@echo "✓ Image available at: https://hub.docker.com/r/pipelex/pipelex-api"

# Points pipelex/pipelex-api:latest at the image Docker Hub already serves as
# pipelex/pipelex-api:$(VERSION), copying the manifest registry-side without
# building or pulling anything, so `latest` names exactly the published image.
# `--prefer-index=false` makes it a carbon copy: by default buildx wraps a
# single image manifest, which is what `docker push` publishes here, in a new
# index whose digest differs, and the release workflow's confirmation, which
# requires both tags to name one digest, would then never pass. The release
# workflow runs it on a retry that finds the version tag already pushed, the
# case `deploy-docker-hub` must not rebuild.
.PHONY: deploy-docker-hub-latest
deploy-docker-hub-latest:
	@test -n "$$DOCKER_HUB_TOKEN" || { echo "ERROR: DOCKER_HUB_TOKEN is not set in the environment."; exit 1; }
	@echo "Logging in to Docker Hub..."
	@printf '%s' "$$DOCKER_HUB_TOKEN" | docker login --username pipelex --password-stdin
	docker buildx imagetools create --prefer-index=false --tag pipelex/pipelex-api:latest pipelex/pipelex-api:$(VERSION)
	@echo "✓ pipelex/pipelex-api:latest now names the published pipelex/pipelex-api:$(VERSION)"
