#################################################################################
#################################    HELPERS    #################################
#################################################################################

# Print title for each section
PRINT_TITLE = @echo "\n\033[1m>>> $1\033[0m\n"

# Colorized variables
YELLOW = \033[33m
GREEN = \033[32m
RESET = \033[0m

# Unified help output
help:
	@echo "$(YELLOW)Available commands:$(RESET)"
	@echo ""
	@echo "$$HELP"
	@echo ""
	@echo "$$HELP_LOCAL"
	@echo ""
	@echo "$$HELP_DEPLOY_API"
	@echo ""
	@echo "$(YELLOW)Use 'make <command>' to run a specific command.$(RESET)"

###########################################################################
############################## Initialization #############################
###########################################################################

# Include the secrets of the .env file
ifneq (,$(wildcard .env))
    include .env
    export $(shell sed 's/=.*//' .env)
endif

$(eval VERSION=$(shell grep '^version' pyproject.toml | sed -E 's/version = "(.*)"/\1/'))

check-version-format:
	@echo "Checking version format: $(VERSION)"
	@if ! echo "$(VERSION)" | grep -Eq '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$$'; then \
		echo "Error: Version $(VERSION) is not in the correct format (x.y.z where x, y, z are non-negative integers)."; \
		exit 1; \
	else \
		echo "Version $(VERSION) is valid."; \
	fi


-include Makefiles/Makefile_basics.mk
-include Makefiles/Makefile.local.mk
-include Makefiles/Makefile.deploy.api.mk