#################################################################################
#################################    HELPERS    #################################
#################################################################################

define HELP_DEPLOY_API
	$(GREEN)Deployment Commands:$(RESET)
	make deploy-docker-hub                  - Deploy the image to Docker Hub.
endef
export HELP_DEPLOY_API

###########################################################################
############################ Docker Hub Deploy ############################
###########################################################################

# Builds the public Pipelex API image and publishes it to Docker Hub as
# pipelex/pipelex-api:$(VERSION) and :latest. Triggered by CI on every push
# to main (see .github/workflows/deploy.yml). This repo only publishes to
# Docker Hub — anything beyond (private registries, ECR/ACR/GCR, ECS/k8s
# deploys) is the user's responsibility, typically in a separate infra repo.
.PHONY: deploy-docker-hub
deploy-docker-hub:
	@echo "\n########################### Docker Hub Build ##########################"
	@echo "Logging in to Docker Hub..."
	@echo "$(DOCKER_HUB_TOKEN)" | docker login --username pipelex --password-stdin

	@echo "Building Docker image for Docker Hub..."
	docker build --platform linux/amd64 -t pipelex-api:$(VERSION) .
	docker tag pipelex-api:$(VERSION) pipelex/pipelex-api:$(VERSION)
	docker tag pipelex-api:$(VERSION) pipelex/pipelex-api:latest

	@echo "Pushing to Docker Hub..."
	docker push pipelex/pipelex-api:$(VERSION)
	docker push pipelex/pipelex-api:latest

	@echo "✓ Built and pushed image pipelex-api:$(VERSION) and latest to Docker Hub"
	@echo "✓ Image available at: https://hub.docker.com/r/pipelex/pipelex-api"
